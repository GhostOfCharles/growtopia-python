"""Deterministic local enemy AI. Character physics and art stay shared."""
from dataclasses import dataclass
from enum import Enum
import math
import random
from types import SimpleNamespace

import pygame

from src.animation import PlayerAnimation, PLAYER_ART_HEIGHT
from src.combat import line_clear
from src.physics import integrate_character, overlaps_solid, damage_character, knockback_character
from src.navigation import PlatformNavigator, NavigationSettings, PathStatus

ZOMBIE_ART_SCALE = 0.95


class ZombieState(str, Enum):
    IDLE = "idle"
    WANDER = "wander"
    CHASE = "chase"
    ATTACK = "attack"
    HURT = "hurt"
    DEAD = "dead"


class NavigationMode(str, Enum):
    APPROACH = "approach"
    PREPARE_JUMP = "prepare_jump"
    JUMP = "jump"
    LAND = "land"
    CONTINUE = "continue"
    STAGING = "staging"


@dataclass(frozen=True)
class ZombieSettings:
    max_hp: float = 100
    punch_damage: float = 10
    attack_damage: float = 12
    wander_speed: float = 1.0
    chase_speed: float = 2.0
    detection_tiles: float = 10
    disengage_tiles: float = 13
    home_tiles: float = 4
    melee_pixels: float = 42
    melee_hitbox_scale: float = 1.15
    swarm_reach_per_ally: float = 28.0
    swarm_max_extra_reach: float = 56.0
    attack_cooldown_ms: float = 1100
    active_attack_frame: int = 3  # zero-based: fourth of six frames
    hit_stun_ms: float = 180
    flash_ms: float = 140
    knockback_x: float = 3.0
    knockback_y: float = -3.5
    jump_cooldown_ms: float = 850
    jump_probe_ticks: int = 150
    chase_drop_tiles: float = 6
    unreachable_ms: float = 2500
    navigation_repath_ms: float = 500
    navigation_retry_ms: float = 1500
    pursuit_memory_ms: float = 3500
    navigation_expansion_limit: int = 220
    death_ms: float = 260
    spawn_idle_ms: float = 600


def lava_overlap(world, x, y, physics):
    return any(world.is_lava(c, r)
               for r in range(math.floor(y/physics.tile_size),
                              math.ceil((y+physics.height)/physics.tile_size))
               for c in range(math.floor(x/physics.tile_size),
                              math.ceil((x+physics.width)/physics.tile_size)))


class Zombie:
    def __init__(self, world, x, y, physics, clips=None, durations=None, settings=None):
        self.world, self.physics = world, physics
        self.settings = settings or ZombieSettings()
        self.x, self.y = float(x), float(y)
        self.home_x, self.home_y = self.x, self.y
        self.vx = self.vy = 0.0
        self.on_ground = False
        self.facing = -1
        self.hp = self.max_hp = self.settings.max_hp
        self.flash_ms = self.invuln_ms = self.knockback_ms = 0.0
        self.time_since_damage_ms = self.health_visible_ms = 0.0
        self.state = ZombieState.IDLE
        self.state_ms = self.attack_elapsed_ms = self.attack_cooldown_ms = 0.0
        self.jump_cooldown_ms = self.blocked_ms = self.ignore_player_ms = 0.0
        self.attack_checked = self.death_emitted = False
        self._best_goal_distance = math.inf
        self._goal_anchor = None
        self.navigator = PlatformNavigator(physics, self.settings.chase_speed,
            NavigationSettings(max_expansions=self.settings.navigation_expansion_limit,
                               max_drop_tiles=self.settings.chase_drop_tiles))
        self._nav_path = []
        self._nav_status = PathStatus.UNREACHABLE
        self._nav_path_index = 0
        self._nav_repath_ms = 0.0
        self._nav_revision = -1
        self._nav_target = None
        self._nav_jump_started_index = -1
        self._nav_mode = NavigationMode.APPROACH
        self._nav_locked_direction = 0
        self._nav_active_edge = None
        self._nav_stall_ms = 0.0
        self._nav_last_waypoint = None
        self._nav_last_waypoint_distance = math.inf
        self._nav_failed_key = None
        self._nav_failure_wait_ms = 0.0
        self._fallback_drop_dir = 0
        self._last_seen_target = None
        self._pursuit_memory_ms = 0.0
        self._tracked_player_vx = 0.0
        self._tracked_player_vy = 0.0
        self._player_motion_samples = 0
        self._predicted_landing = None
        self._prediction_refresh_ms = 0.0
        self._prediction_last_vx = 0.0
        self.removed = False
        self._rng = random.Random(round(x)*73856093 ^ round(y)*19349663)
        self.wander_direction = self._rng.choice((-1, 1))
        self.idle_ms = self.settings.spawn_idle_ms
        # Keep zombie art slightly smaller than the player, with the same feet anchor.
        self.animation = PlayerAnimation(durations, clips,
            sprite_height=PLAYER_ART_HEIGHT * ZOMBIE_ART_SCALE)
        self.attack_durations = self.animation.frame_durations.get(
            "attack", (100, 100, 90, 90, 110, 130))

    @property
    def center(self):
        return self.x+self.physics.width/2, self.y+self.physics.height/2

    def rect(self):
        return pygame.FRect(self.x, self.y, self.physics.width, self.physics.height)

    def _transition(self, state):
        if self.state == state:
            return
        self.state, self.state_ms = state, 0.0
        if state == ZombieState.IDLE:
            self.idle_ms = self._rng.uniform(650, 1100)
        elif state == ZombieState.WANDER:
            # The spawn pause belongs to IDLE; search and sight re-entry do
            # not need another wake-up delay.
            self.idle_ms = 0.0
        elif state == ZombieState.HURT:
            # A hit cancels the current scratch sequence immediately.
            self.attack_elapsed_ms = 0.0
            self.attack_checked = True
        elif state == ZombieState.ATTACK:
            self.attack_elapsed_ms = 0.0
            self.attack_checked = False
            self.attack_cooldown_ms = self.settings.attack_cooldown_ms
        elif state == ZombieState.DEAD:
            self.vx = self.vy = 0.0
        elif state == ZombieState.CHASE:
            self._best_goal_distance = math.inf
            self._goal_anchor = None
            self.blocked_ms = 0
            self._nav_path = []
            self._nav_status = PathStatus.UNREACHABLE
            self._nav_path_index = 0
            self._nav_repath_ms = 0.0
            self._nav_target = None
            self._nav_stall_ms = 0.0
            self._nav_last_waypoint = None
            self._nav_last_waypoint_distance = math.inf
            self._nav_failed_key = None
            self._nav_failure_wait_ms = 0.0
            self._nav_mode = NavigationMode.APPROACH
            self._nav_locked_direction = 0
            self._nav_active_edge = None

    def take_damage(self, amount, source_x):
        if self.state == ZombieState.DEAD or self.invuln_ms > 1e-8 or amount <= 0:
            return False
        damage_character(self, amount, self.settings.flash_ms)
        self.health_visible_ms = 1600
        if self.hp <= 0:
            self._transition(ZombieState.DEAD)
        else:
            knockback_character(self, source_x, self.physics.width,
                self.settings.knockback_x, self.settings.knockback_y,
                self.settings.hit_stun_ms, self.settings.hit_stun_ms)
            self._transition(ZombieState.HURT)
        return True

    def disengage(self, ignore_ms=0):
        if self.state not in (ZombieState.DEAD, ZombieState.HURT):
            self._transition(ZombieState.WANDER)
            if self._last_seen_target is not None:
                self.wander_direction = (1 if self._last_seen_target[0] > self.center[0]
                                         else -1)
                self.facing = self.wander_direction
        self.ignore_player_ms = max(0.0, float(ignore_ms))
        self.blocked_ms = 0

    def _melee_connects(self, player, nearby_zombies=()):
        p = self.physics
        dx = player.x+p.width/2-self.center[0]
        vertical_pad = p.height*(self.settings.melee_hitbox_scale-1)*.5
        reach = self.settings.melee_pixels*self.settings.melee_hitbox_scale
        if abs(dx) > reach:
            allies_in_front = 0
            for ally in nearby_zombies:
                if ally is self or ally.removed or ally.state == ZombieState.DEAD:
                    continue
                ally_dx = ally.center[0]-self.center[0]
                if not 0 < ally_dx*dx < dx*dx:
                    continue
                if (ally.y < player.y+p.height and
                        ally.y+p.height > player.y):
                    allies_in_front += 1
            reach += min(self.settings.swarm_max_extra_reach,
                         allies_in_front*self.settings.swarm_reach_per_ally)
        return (abs(dx) <= reach and dx*self.facing >= -2
                and self.y+p.height+vertical_pad > player.y+6
                and player.y+p.height-6 > self.y-vertical_pad
                and line_clear(self.world, self.center,
                    (player.x+p.width/2, player.y+p.height/2), p.tile_size))

    def _safe_floor_ahead(self, direction):
        p = self.physics
        c = math.floor((self.center[0]+direction*(p.width/2+10))/p.tile_size)
        row = math.floor((self.y+p.height+1)/p.tile_size)
        for r in range(row, row+2):
            if self.world.is_lava(c, r):
                return False
            if self.world.is_solid(c, r):
                return True
        return False

    def _can_jump(self, direction, speed, elevated=False):
        """Predict a short real-physics arc; accept only a safe useful landing."""
        p = self.physics
        probe = SimpleNamespace(world=self.world, x=self.x, y=self.y,
                                vx=direction*speed, vy=p.jump_velocity, on_ground=False)
        # Chase probes can include a controlled drop to a lower route. This
        # lets zombies follow around tall ledges while still rejecting lava
        # and deep pits; movement itself always uses normal swept physics.
        for tick in range(self.settings.jump_probe_ticks):
            probe.vx = direction*speed
            integrate_character(probe, p.step_ms, p)
            if (lava_overlap(self.world, probe.x, probe.y, p) or
                    probe.y > self.y+self.settings.chase_drop_tiles*p.tile_size):
                return False
            if probe.on_ground and tick > 1:
                useful = ((probe.x-self.x)*direction >= p.tile_size*.8 or
                          elevated and probe.y < self.y-8)
                return useful and not self.world.is_lava(
                    math.floor((probe.x+p.width/2)/p.tile_size),
                    math.floor((probe.y+p.height+1)/p.tile_size))
        return False

    def _can_drop(self, direction, speed):
        """Allow following a safe lower route when a gap cannot be jumped."""
        p = self.physics
        probe = SimpleNamespace(world=self.world, x=self.x, y=self.y,
                                vx=direction*speed, vy=0.0, on_ground=True)
        for tick in range(self.settings.jump_probe_ticks):
            probe.vx = direction*speed
            integrate_character(probe, p.step_ms, p)
            if lava_overlap(self.world, probe.x, probe.y, p):
                return False
            if probe.y > self.y+self.settings.chase_drop_tiles*p.tile_size:
                return False
            if probe.on_ground and tick > 1:
                return (direction*(probe.x-self.x) >= p.tile_size*.8 and
                        not self.world.is_lava(
                            math.floor((probe.x+p.width/2)/p.tile_size),
                            math.floor((probe.y+p.height+1)/p.tile_size)))
        return False

    def _navigate(self, direction, speed, player=None):
        if not self.on_ground:
            return direction*speed, False
        p = self.physics
        obstructed = overlaps_solid(self.world, self.x+direction*12, self.y,
                                    p.width, p.height, p.tile_size)
        supported = self._safe_floor_ahead(direction)
        elevated = (player is not None and player.y < self.y-12 and
                    abs(player.x-self.x) < 4*p.tile_size)
        if (obstructed or not supported or elevated) and self.jump_cooldown_ms <= 1e-8:
            self.jump_cooldown_ms = self.settings.jump_cooldown_ms
            if self._can_jump(direction, speed, elevated):
                return direction*speed, True
            if not obstructed and not supported and player is not None and self._can_drop(direction, speed):
                return direction*speed, False
        if obstructed or not supported:
            return 0.0, False
        return direction*speed, False

    def _predict_landing(self, player):
        """Short ballistic estimate using the real swept physics and lava rules."""
        cache_key = (id(player), getattr(self.world, "navigation_revision", 0),
                     player.x, player.y, player.vx, player.vy, player.on_ground,
                     round(self._tracked_player_vx, 2))
        cached = getattr(self.world, "_zombie_landing_prediction", None)
        if cached is not None and cached[0] == cache_key:
            return cached[1]
        if player.on_ground or abs(player.vy) < .1:
            self.world._zombie_landing_prediction = (cache_key, None)
            return None
        p = self.physics
        probe = SimpleNamespace(world=self.world, x=player.x, y=player.y,
                                vx=(self._tracked_player_vx if self._player_motion_samples
                                    else player.vx),
                                vy=player.vy, on_ground=False)
        origin = (player.x+p.width/2, player.y+p.height/2)
        for _ in range(36):  # at most 300 ms: useful, but easy to correct
            integrate_character(probe, p.step_ms, p)
            if lava_overlap(self.world, probe.x, probe.y, p):
                self.world._zombie_landing_prediction = (cache_key, None)
                return None
            if probe.on_ground:
                landing = (probe.x+p.width/2, probe.y+p.height/2)
                if abs(landing[0]-origin[0]) <= p.tile_size*3:
                    self.world._zombie_landing_prediction = (cache_key, landing)
                    return landing
                self.world._zombie_landing_prediction = (cache_key, None)
                return None
        self.world._zombie_landing_prediction = (cache_key, None)
        return None

    def _follow_player_path(self, target, dt, approach_offset=0.0):
        """Follow a cached A* route; physics still performs every movement."""
        p = self.physics
        target = (target[0]+approach_offset, target[1])
        revision = getattr(self.world, "navigation_revision", 0)
        target_key = (math.floor(target[0]/p.tile_size),
                      math.floor(target[1]/p.tile_size))
        old_target_key = (None if self._nav_target is None else
                          (math.floor(self._nav_target[0]/p.tile_size),
                           math.floor(self._nav_target[1]/p.tile_size)))
        target_changed = target_key != old_target_key
        self._nav_repath_ms = max(0.0, self._nav_repath_ms-dt)
        self._nav_failure_wait_ms = max(0.0, self._nav_failure_wait_ms-dt)
        terrain_changed = revision != self._nav_revision
        route_empty = self._nav_path_index >= len(self._nav_path)
        should_repath = (target_changed or terrain_changed or
                         (route_empty and self._nav_status != PathStatus.COMPLETE and
                          self._nav_failure_wait_ms <= 0) or
                         (self._nav_repath_ms <= 0 and self._nav_status == PathStatus.COMPLETE))
        failed_key = (target_key, revision,
                      round(self.x/p.tile_size), round(self.y/p.tile_size))
        if (self._nav_status == PathStatus.UNREACHABLE and
                self._nav_failed_key == failed_key and not terrain_changed and
                not target_changed):
            should_repath = False
        budgeted = getattr(self.world, "navigation_budget_enabled", False)
        budget_available = (not budgeted or
                            getattr(self.world, "navigation_budget_remaining", 0) > 0)
        if self.on_ground and should_repath and budget_available:
            if budgeted:
                self.world.navigation_budget_remaining -= 1
            if target_changed or terrain_changed:
                self._nav_stall_ms = 0.0
            result = self.navigator.find_path(self.world, (self.x, self.y), target)
            remaining = max(0, len(self._nav_path)-self._nav_path_index)
            replace_route = (target_changed or terrain_changed or route_empty or
                             result.status != self._nav_status or
                             len(result.steps)+1 < remaining)
            if replace_route:
                self._nav_path = list(result.steps)
                self._nav_path_index = 0
                self._nav_jump_started_index = -1
                self._nav_stall_ms = 0.0
                self._nav_mode = NavigationMode.APPROACH
                self._nav_active_edge = None
                self._nav_locked_direction = 0
            self._nav_status = result.status
            self._nav_target = target
            self._nav_revision = revision
            self._nav_repath_ms = (self.settings.navigation_retry_ms
                if result.status != PathStatus.COMPLETE else self.settings.navigation_repath_ms)
            self._nav_failure_wait_ms = self._nav_repath_ms if result.status != PathStatus.COMPLETE else 0
            if result.status == PathStatus.PARTIAL and result.endpoint:
                endpoint_key = (target_key, revision,
                    round(result.endpoint[0]/p.tile_size),
                    round(result.endpoint[1]/p.tile_size))
                self._nav_failed_key = endpoint_key
            elif result.status == PathStatus.UNREACHABLE:
                self._nav_failed_key = failed_key
            else:
                self._nav_failed_key = None

        if self._nav_path_index >= len(self._nav_path):
            self._nav_mode = (NavigationMode.STAGING if
                              self._nav_status != PathStatus.COMPLETE
                              else NavigationMode.CONTINUE)
            self._nav_stall_ms += dt
            return 0.0, False

        step = self._nav_path[self._nav_path_index]
        target_x = step.x+p.width/2
        horizontal = target_x-self.center[0]
        if step.action == "jump":
            takeoff_x = (step.takeoff_x if step.takeoff_x is not None else step.x)+p.width/2
            takeoff_y = step.takeoff_y if step.takeoff_y is not None else self.y
            if self._nav_mode == NavigationMode.JUMP:
                if not self.on_ground:
                    direction = self._nav_locked_direction
                    self.facing = direction or self.facing
                    return direction*self.settings.chase_speed, False
                landed = (abs(self.center[0]-target_x) <= p.tile_size*.75 and
                          abs(self.y-step.y) <= 10)
                if not landed:
                    self.navigator.fail_transition(self._nav_active_edge)
                    self._nav_path = []
                    self._nav_path_index = 0
                    self._nav_status = PathStatus.COMPLETE
                    self._nav_repath_ms = 0
                    self._nav_mode = NavigationMode.APPROACH
                    self._nav_active_edge = None
                    return 0.0, False
                self._nav_mode = NavigationMode.LAND
                self._nav_active_edge = None
            if self._nav_mode in (NavigationMode.APPROACH, NavigationMode.CONTINUE):
                self._nav_mode = NavigationMode.APPROACH
                approach_dx = takeoff_x-self.center[0]
                if self.on_ground and abs(approach_dx) <= 8 and abs(self.y-takeoff_y) <= 5:
                    self._nav_mode = NavigationMode.PREPARE_JUMP
                else:
                    direction = 1 if approach_dx > 2 else -1 if approach_dx < -2 else 0
                    if direction:
                        self.facing = direction
                    return direction*self.settings.chase_speed, False
            if self._nav_mode == NavigationMode.PREPARE_JUMP:
                if not self.on_ground:
                    self._nav_mode = NavigationMode.JUMP
                    return self._nav_locked_direction*self.settings.chase_speed, False
                if self.jump_cooldown_ms > 1e-8:
                    return 0.0, False
                direction = 1 if horizontal > 0 else -1 if horizontal < 0 else self.facing
                self._nav_locked_direction = direction
                self._nav_active_edge = step.edge_id
                self._nav_mode = NavigationMode.JUMP
                self._nav_jump_started_index = self._nav_path_index
                self.jump_cooldown_ms = self.settings.jump_cooldown_ms
                self.facing = direction
                return direction*self.settings.chase_speed, True
        elif self._nav_mode == NavigationMode.JUMP:
            # A route correction never turns a jump already in progress.
            if not self.on_ground:
                return self._nav_locked_direction*self.settings.chase_speed, False
            self._nav_mode = NavigationMode.LAND
        # Reaching a standing waypoint requires both its horizontal alignment
        # and floor height; jump arcs do not advance the route while airborne.
        if (self.on_ground and abs(horizontal) <= 8 and abs(self.y-step.y) <= 4):
            self._nav_path_index += 1
            self._nav_jump_started_index = -1
            self._nav_stall_ms = 0.0
            self._nav_last_waypoint = None
            self._nav_last_waypoint_distance = math.inf
            self._nav_mode = NavigationMode.CONTINUE
            if self._nav_path_index >= len(self._nav_path):
                self._nav_repath_ms = 0
                return 0.0, False
            step = self._nav_path[self._nav_path_index]
            target_x = step.x+p.width/2
            horizontal = target_x-self.center[0]

        if not overlaps_solid(self.world, step.x, step.y, p.width, p.height, p.tile_size):
            pass
        else:
            self._nav_repath_ms = 0
            return 0.0, False

        direction = 1 if horizontal > 2 else -1 if horizontal < -2 else 0
        if direction:
            self.facing = direction
        jump = False

        waypoint_id = (self._nav_path_index, step.x, step.y)
        distance = math.hypot(horizontal, self.y-step.y)
        if waypoint_id != self._nav_last_waypoint:
            self._nav_last_waypoint = waypoint_id
            self._nav_last_waypoint_distance = distance
        elif distance < self._nav_last_waypoint_distance-1.5:
            self._nav_last_waypoint_distance = distance
            self._nav_stall_ms = 0.0
        else:
            self._nav_stall_ms += dt
        return direction*self.settings.chase_speed, jump

    def _safe_drop_toward(self, target):
        """Take a verified local drop toward the last known player position.

        This is a deliberately small escape hatch for bounded-search failures:
        it only commits when the existing swept-physics probe confirms a safe
        landing, then lets normal physics carry the zombie off the ledge.
        """
        if self._fallback_drop_dir:
            if not self.on_ground:
                return self._fallback_drop_dir*self.settings.chase_speed
            self._fallback_drop_dir = 0
        if not self.on_ground or target is None:
            return 0.0
        direction = 1 if target[0] > self.center[0] else -1
        source = (math.floor((self.center[0])/self.physics.tile_size),
                  round((self.y+self.physics.height)/self.physics.tile_size))
        landing = self.navigator.safe_drop_landing(self.world, source, direction)
        if landing is not None and landing[1] > source[1]:
            self._fallback_drop_dir = direction
            self.facing = direction
            return direction*self.settings.chase_speed
        return 0.0

    def update(self, dt, player, on_player_hit=None, approach_offset=0.0,
               nearby_zombies=()):
        self.state_ms += dt
        if self.state == ZombieState.DEAD:
            self.removed = self.state_ms >= self.settings.death_ms
            return
        for name in ("flash_ms", "invuln_ms", "knockback_ms", "health_visible_ms",
                     "attack_cooldown_ms", "jump_cooldown_ms", "ignore_player_ms"):
            setattr(self, name, max(0, getattr(self, name)-dt))
        p = self.physics
        self.navigator.update(dt)
        self._prediction_refresh_ms = max(0.0, self._prediction_refresh_ms-dt)
        # Smooth ordinary motion briefly, but snap direction reversals so the
        # zombie does not keep predicting the player's old lane.
        blend = min(1.0, dt/90.0)
        if self._player_motion_samples == 0 or self._tracked_player_vx*player.vx < 0:
            self._tracked_player_vx = player.vx
        else:
            self._tracked_player_vx += (player.vx-self._tracked_player_vx)*blend
        self._tracked_player_vy += (player.vy-self._tracked_player_vy)*blend
        self._player_motion_samples += 1
        if lava_overlap(self.world, self.x, self.y, p):
            damage_character(self, 25*dt/1000, self.settings.flash_ms)
            if self.hp <= 0:
                self._transition(ZombieState.DEAD)
                return
        dx = player.x+p.width/2-self.center[0]
        dy = player.y+p.height/2-self.center[1]
        distance = math.hypot(dx, dy)/p.tile_size
        alive = player.hp > 0 and self.ignore_player_ms <= 0
        visible = alive and distance <= self.settings.detection_tiles
        if visible:
            self._last_seen_target = (player.x+p.width/2, player.y+p.height/2)
            self._pursuit_memory_ms = self.settings.pursuit_memory_ms
        else:
            self._pursuit_memory_ms = max(0.0, self._pursuit_memory_ms-dt)
        aware = alive and (visible or self._pursuit_memory_ms > 0)
        pursuit_target = ((player.x+p.width/2, player.y+p.height/2) if visible
                          else self._last_seen_target)
        if visible:
            reversed_direction = self._tracked_player_vx*self._prediction_last_vx < 0
            if not player.on_ground and (self._prediction_refresh_ms <= 0 or reversed_direction):
                self._predicted_landing = self._predict_landing(player)
                self._prediction_refresh_ms = 100.0
                self._prediction_last_vx = self._tracked_player_vx
            elif player.on_ground:
                self._predicted_landing = None
                self._prediction_refresh_ms = 0.0
            predicted = self._predicted_landing
            if predicted is not None and abs(predicted[1]-pursuit_target[1]) > p.tile_size*.5:
                pursuit_target = predicted
        desired = 0.0
        jump = False
        if self.state == ZombieState.HURT:
            self.vx *= .95 ** (dt/p.step_ms)
            if self.knockback_ms <= 1e-8:
                self._transition(ZombieState.CHASE if aware
                                 else ZombieState.IDLE)
        elif self.state == ZombieState.ATTACK:
            previous = self.attack_elapsed_ms
            self.attack_elapsed_ms += dt
            active = sum(self.attack_durations[:self.settings.active_attack_frame])
            if not self.attack_checked and previous < active <= self.attack_elapsed_ms:
                self.attack_checked = True
                if (player.hp > 0 and
                        self._melee_connects(player, nearby_zombies) and on_player_hit):
                    on_player_hit(self, self.settings.attack_damage)
            if self.attack_elapsed_ms >= sum(self.attack_durations):
                self._transition(ZombieState.CHASE if aware else ZombieState.IDLE)
            self.vx = 0
        else:
            if self.state == ZombieState.CHASE and (not alive or
                    distance > self.settings.disengage_tiles):
                self.disengage()
            elif aware and distance <= self.settings.detection_tiles and self.state_ms >= self.idle_ms:
                self._transition(ZombieState.CHASE)
            if self.state == ZombieState.IDLE:
                if self.state_ms >= self.idle_ms:
                    self._transition(ZombieState.WANDER)
            if self.state == ZombieState.WANDER:
                if abs(self.x-self.home_x) >= self.settings.home_tiles*p.tile_size:
                    self.wander_direction = 1 if self.x < self.home_x else -1
                self.facing = self.wander_direction
                desired, jump = self._navigate(self.facing, self.settings.wander_speed)
                if not desired or self.state_ms > 2000:
                    self.wander_direction *= -1
                    self._transition(ZombieState.IDLE)
            elif self.state == ZombieState.CHASE:
                if abs(dx) > 2:
                    self.facing = 1 if dx > 0 else -1
                if self.on_ground and self._melee_connects(player, nearby_zombies):
                    if self.attack_cooldown_ms <= 1e-8:
                        self._transition(ZombieState.ATTACK)
                else:
                    if pursuit_target is not None:
                        # Spread a group while approaching, then remove the
                        # offset nearby so no zombie parks outside melee range.
                        near_offset = (approach_offset if distance > 3.0 else 0.0)
                        desired, jump = self._follow_player_path(
                            pursuit_target, dt, near_offset)
                        route_empty = self._nav_path_index >= len(self._nav_path)
                        if (not self._melee_connects(player, nearby_zombies) and route_empty and
                                self._nav_status == PathStatus.COMPLETE):
                            # A* goals are tile-sized; continue closing the
                            # final gap with the existing local safe movement
                            # controller rather than waiting at its endpoint.
                            direction = 1 if dx > 0 else -1 if dx < 0 else 0
                            desired, jump = self._navigate(
                                direction, self.settings.chase_speed, player)
                    if self._nav_status == PathStatus.UNREACHABLE:
                        # Follow the player's horizontal trail only when the
                        # real collision/physics probe confirms a safe drop.
                        # After landing, the changed start tile naturally
                        # enables a fresh platform-graph search.
                        desired = self._safe_drop_toward(pursuit_target)
                        jump = False
            self.vx = desired
        if jump and self.on_ground:
            self.vy, self.on_ground = p.jump_velocity, False
        integrate_character(self, dt, p)
        if (self.state == ZombieState.CHASE and self._nav_mode == NavigationMode.JUMP
                and self.on_ground and self._nav_path_index < len(self._nav_path)):
            landed_step = self._nav_path[self._nav_path_index]
            landed_ok = (abs(self.center[0]-(landed_step.x+p.width/2)) <= p.tile_size*.75
                         and abs(self.y-landed_step.y) <= 10)
            if landed_ok:
                self._nav_mode = NavigationMode.LAND
                self._nav_active_edge = None
            else:
                self.navigator.fail_transition(self._nav_active_edge)
                self._nav_path = []
                self._nav_path_index = 0
                self._nav_status = PathStatus.COMPLETE
                self._nav_repath_ms = 0
                self._nav_mode = NavigationMode.APPROACH
                self._nav_active_edge = None
        if (self.state == ZombieState.CHASE and
                not self._melee_connects(player, nearby_zombies)):
            if not self._nav_path and (abs(self.vx) > .1 or not self.on_ground):
                self._nav_stall_ms = 0.0
            self.blocked_ms = self._nav_stall_ms
            if self.blocked_ms >= self.settings.unreachable_ms:
                self.disengage()
        elif self.state != ZombieState.CHASE:
            self.blocked_ms = 0
        if (self.state == ZombieState.CHASE and self.on_ground and
                self._nav_path_index < len(self._nav_path) and
                self._nav_stall_ms >= 900):
            # Drop a route that has stopped producing physical progress once;
            # the bounded planner can find a detour or cache a staging point.
            self._nav_path = []
            self._nav_path_index = 0
            self._nav_status = PathStatus.COMPLETE
            self._nav_repath_ms = 0
            self._nav_stall_ms = 0
        self.animation.update(dt, grounded=self.on_ground, vx=self.vx, vy=self.vy)

    def draw(self, surface, cam_x, cam_y):
        if self.state == ZombieState.DEAD:
            return
        p = self.physics
        self.animation.draw(surface, self.x-cam_x, self.y-cam_y, p.width, p.height,
            self.facing, (145, 165, 95), (90, 65, 90), (20, 20, 30),
            flash_ratio=self.flash_ms/self.settings.flash_ms,
            full_body_state="attack" if self.state == ZombieState.ATTACK else None,
            full_body_elapsed_ms=self.attack_elapsed_ms)
        if self.health_visible_ms > 0:
            x = round(self.center[0]-cam_x-17)
            y = round(self.y+p.height-PLAYER_ART_HEIGHT-cam_y-8)
            pygame.draw.rect(surface, (15, 30, 50), (x, y, 34, 5))
            pygame.draw.rect(surface, (190, 205, 95), (x+1, y+1, round(32*self.hp/self.max_hp), 3))

    def draw_navigation_debug(self, surface, cam_x, cam_y, font):
        p = self.physics
        graph_data = self.navigator.graph_for_debug()
        if graph_data and graph_data[0] == id(self.world):
            graph = graph_data[1]
            view = pygame.FRect(cam_x-32, cam_y-32,
                                surface.get_width()+64, surface.get_height()+64)
            colors = {"walk": (85, 185, 235), "jump": (90, 225, 145),
                      "drop": (245, 185, 75)}
            for platform in graph.platforms:
                if not platform:
                    continue
                first, last = platform[0], platform[-1]
                x1, y1 = self.navigator._position(first)
                x2, _ = self.navigator._position(last)
                if view.colliderect(pygame.FRect(x1, y1+p.height, x2-x1+p.width, 2)):
                    pygame.draw.line(surface, (60, 170, 210),
                        (round(x1+p.width/2-cam_x), round(y1+p.height-cam_y)),
                        (round(x2+p.width/2-cam_x), round(y1+p.height-cam_y)), 2)
            for node, edges in graph.edges.items():
                x, y = self.navigator._position(node)
                if not view.collidepoint(x+p.width/2, y+p.height/2):
                    continue
                for edge in edges:
                    ex, ey = self.navigator._position(edge.destination)
                    pygame.draw.line(surface, colors[edge.action],
                        (round(x+p.width/2-cam_x), round(y+p.height/2-cam_y)),
                        (round(ex+p.width/2-cam_x), round(ey+p.height/2-cam_y)), 1)
            for source, destination, action in self.navigator.failed_transitions:
                sx, sy = self.navigator._position(source)
                dx, dy = self.navigator._position(destination)
                pygame.draw.line(surface, (245, 65, 75),
                    (round(sx+p.width/2-cam_x), round(sy+p.height/2-cam_y)),
                    (round(dx+p.width/2-cam_x), round(dy+p.height/2-cam_y)), 3)

        route = self._nav_path[self._nav_path_index:]
        points = [self.center] + [(step.x+p.width/2, step.y+p.height/2) for step in route]
        for start, end in zip(points, points[1:]):
            pygame.draw.line(surface, (255, 220, 80),
                (round(start[0]-cam_x), round(start[1]-cam_y)),
                (round(end[0]-cam_x), round(end[1]-cam_y)), 3)
        if route:
            step = route[0]
            point = (round(step.x+p.width/2-cam_x), round(step.y+p.height/2-cam_y))
            pygame.draw.circle(surface, (255, 240, 130), point, 6, 2)
            if step.action == "jump" and step.takeoff_x is not None:
                takeoff = (round(step.takeoff_x+p.width/2-cam_x),
                           round(step.takeoff_y+p.height-cam_y))
                pygame.draw.circle(surface, (90, 255, 145), takeoff, 7, 2)
        label = f"{self._nav_status.value} / {self._nav_mode.value}"
        surface.blit(font.render(label, True, (255, 245, 190)),
                     (round(self.center[0]-cam_x-50), round(self.y-cam_y-20)))


def find_zombie_spawn(world, player, entities, physics):
    """Nearby supported, lava-free positions. Never move a body to recover it."""
    p = physics
    home_c = math.floor((player.x+p.width/2)/p.tile_size)
    home_r = math.floor((player.y+p.height)/p.tile_size)
    max_offset = min(64, math.ceil(p.world_width/p.tile_size))
    for offset in range(4, max_offset+1):
        for direction in (1, -1):
            c = home_c+offset*direction
            if not 1 <= c < p.world_width/p.tile_size-1:
                continue
            for r in sorted(range(max(2, home_r-4), min(len(world.tiles), home_r+5)),
                            key=lambda row: abs(row-home_r)):
                if not world.is_solid(c, r) or world.is_lava(c, r):
                    continue
                x, y = c*p.tile_size+(p.tile_size-p.width)/2, r*p.tile_size-p.height
                rect = pygame.FRect(x, y, p.width, p.height)
                if (overlaps_solid(world, x, y, p.width, p.height, p.tile_size)
                        or lava_overlap(world, x, y, p) or rect.colliderect(player.rect())
                        or any(rect.colliderect(z.rect()) for z in entities if not z.removed)):
                    continue
                return x, y
    return None
