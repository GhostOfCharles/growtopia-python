import pygame
import sys
import json
import os
import math
import random
from types import SimpleNamespace
from src.effects import BlockEffects, PunchStretchEffect, draw_fist_icon
from src.physics import (overlaps_solid, sweep_axis, CharacterPhysics,
                         integrate_character, damage_character, knockback_character)
from src.animation import PlayerAnimation, PunchAnim
from src.assets import AssetManager
from src.background import BackgroundRenderer
from src.camera import FallingCamera
from src.hud import HUDRenderer
from src.audio import AudioManager, NULL_AUDIO
from src.zombie import Zombie, ZombieState, find_zombie_spawn
from src.combat import line_clear, segment_box_fraction

# ---------------------------------------------------------------
# Config
# ---------------------------------------------------------------
WIDTH, HEIGHT = 1600, 900
FPS = 60
TITLE = "Growtopia"
WORLDS_FILE = "worlds.json"
ACCOUNTS_FILE = "accounts.json"

# Grid geometry
TILE = 32
GRID_W = 100
SURFACE_ROW = 40
BEDROCK_DEPTH = 40
BEDROCK_ROW = SURFACE_ROW + BEDROCK_DEPTH
GRID_H = BEDROCK_ROW + 6
WORLD_W = GRID_W * TILE

# Tile types
AIR     = 0
DIRT    = 1
GRASS   = 2
STONE   = 3
BEDROCK = 4
LAVA    = 5

TILE_COLORS = {
    AIR:     None,
    DIRT:    (139, 90, 43),
    GRASS:   (86, 160, 60),
    STONE:   (110, 110, 120),
    BEDROCK: (45, 45, 55),
    LAVA:    (230, 90, 30),
}

TILE_COLLIDES = {
    AIR:     False,
    DIRT:    True,
    GRASS:   True,
    STONE:   True,
    BEDROCK: True,
    LAVA:    False,
}

TILE_NAMES = {
    DIRT:    "Dirt",
    GRASS:   "Grass",
    STONE:   "Stone",
    BEDROCK: "Bedrock",
    LAVA:    "Lava",
}

BLOCK_TEXTURE_FILES = {
    DIRT: "blocks/dirt.png",
    GRASS: "blocks/grass.png",
    STONE: "blocks/stone.png",
    BEDROCK: "blocks/bedrock.png",
    LAVA: "blocks/lava.png",
}

# Colors
BG_TOP      = (60, 140, 220)
BG_BOTTOM   = (30, 90, 160)
SKY         = (110, 180, 240)
BTN_COLOR   = (255, 200, 60)
BTN_HOVER   = (255, 225, 120)
BTN_TEXT    = (60, 40, 0)
TITLE_COLOR = (255, 255, 255)
TEXT_COLOR  = (255, 255, 255)
INPUT_BG    = (245, 245, 245)
INPUT_TEXT  = (30, 30, 30)
PANEL_BG    = (20, 40, 70)
PANEL_ALT   = (30, 55, 95)
PANEL_HOVER = (45, 80, 140)
ROW_BORDER  = (255, 200, 60)

# Player
PLAYER_W, PLAYER_H = 28, 56
HEAD_H = PLAYER_H // 2
HEAD_COLOR = (245, 245, 245)
BODY_COLOR = (60, 110, 220)
OUTLINE    = (20, 20, 30)
FLASH_COLOR = (255, 60, 60)

# Physics
SIMULATION_STEP_MS = 1000.0 / 60.0
MOVE_SPEED    = 3.0
SPRINT_SPEED_MULTIPLIER = 1.5
GRAVITY       = 0.7
JUMP_VELOCITY = -13.0
MAX_FALL      = 18.0
DASH_DISTANCE_TILES = 4.0
DASH_SPEED_MULTIPLIER = 3.0
DASH_SPEED = MOVE_SPEED * DASH_SPEED_MULTIPLIER
DASH_DURATION_MS = DASH_DISTANCE_TILES * TILE / DASH_SPEED * SIMULATION_STEP_MS
DASH_COOLDOWN_MS = 1000.0  # Recovery after the burst ends or is interrupted.
HEAVY_LANDING_THRESHOLD_TILES = 12.0
HEAVY_LANDING_RECOVERY_MS = 1000.0
HEAVY_LANDING_SOUND_LEAD_MS = 130.0
FALL_ZOOM_START_TILES = 6.0
FALL_ZOOM_STRENGTH = 1.10
RECOVERY_CONTROL_KEYS = (pygame.K_a, pygame.K_d, pygame.K_LEFT, pygame.K_RIGHT,
                         pygame.K_SPACE, pygame.K_w, pygame.K_UP, pygame.K_q,
                         pygame.K_LSHIFT, pygame.K_RSHIFT)
CHARACTER_PHYSICS = CharacterPhysics(TILE, PLAYER_W, PLAYER_H, SIMULATION_STEP_MS,
                                    GRAVITY, JUMP_VELOCITY, MAX_FALL, WORLD_W)

# Lava / hazard
LAVA_DPS             = 25.0
LAVA_INVULN_MS       = 320
LAVA_FLASH_MS        = 140
LAVA_KNOCKBACK_X     = 9.0
LAVA_KNOCKBACK_Y     = -8.0
LAVA_KNOCKBACK_LOCK  = 260
LAVA_KNOCKBACK_DAMP  = 0.15
BURN_SOUND_COOLDOWN_MS = 900
INVALID_PLACE_SOUND_COOLDOWN_MS = 350
BLOCK_HIT_SOUND_VOLUME = 0.65

# HP
MAX_HP           = 100.0
REGEN_PER_SEC    = 8.0
REGEN_DELAY_MS   = 2500

# Hotbar
HOTBAR_SLOTS = 8
HOTBAR_SLOT_SIZE = 64
HOTBAR_GAP = 8
HOTBAR_MARGIN_BOTTOM = 40
HOTBAR_BG = (18, 35, 62)
HOTBAR_BORDER = (8, 19, 36)
HOTBAR_SELECTED = (255, 200, 60)
HOTBAR_HOVER = (48, 76, 116)
HOTBAR_EMPTY_COLOR = (27, 43, 68)
HOTBAR_COUNT_COLOR = (255, 255, 255)
HOTBAR_COUNT_SHADOW = (0, 0, 0)

# Existing visual timing, also used for the new desktop hold-repeat convenience.
# Neither this duration nor the repeat interval is a measured reference value.
PUNCH_RANGE = 4.5
MAX_ZOMBIES = 50
PUNCH_DURATION = 180
PUNCH_RESTART_MIN_MS = 60     # don't restart the anim if it's still mid-swing
BLOCK_HIT_COOLDOWN_MS = 200  # at most five successful punches per second
ACTION_REPEAT_MS = max(PUNCH_DURATION, BLOCK_HIT_COOLDOWN_MS)
MAX_FRAME_MS = 250.0         # bounded catch-up after a stall; discard excess wall time

# Block breaking — durability is per block ID so future block types can be tuned
# without changing the damage and save representation.
DAMAGE_RESET_MS = 1500

BLOCK_DURABILITY = {
    GRASS: 4,
    DIRT:  4,
    STONE: 10,
    LAVA:  3,
    # BEDROCK missing → unbreakable
}
BREAK_HITS = BLOCK_DURABILITY  # compatibility name used by existing callers/tests
BLOCK_HIT_SOUND_VOLUME = 0.65
BLOCK_HIT_FINAL_VOLUME = 0.32

DROP_CHANCE = 0.33
DROP_SIZE = 18
DROP_BOB_SPEED = 0.005
DROP_BOB_HEIGHT = 2.5
DROP_POP_DURATION_MS = 240.0
DROP_POP_HEIGHT = 7.0
DROP_SPAWN_JITTER = 4.0
PICKUP_RADIUS = 40

# Lava drop → hardened stone (never gives lava itself)
LAVA_DROP_TILE = STONE

# Placement — instant, with cooldown
PLACE_RANGE = 5.5
PLACE_COOLDOWN = 200

# ---------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------
def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default

def _write_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass

def load_worlds():
    return _read_json(WORLDS_FILE, [])

def save_worlds(worlds):
    _write_json(WORLDS_FILE, worlds)

# ---------------------------------------------------------------
# Account persistence
# ---------------------------------------------------------------
DEFAULT_ACCOUNT = {
    "username": "Player",
    "inventory": [{"tile": None, "count": 0} for _ in range(HOTBAR_SLOTS)],
    "selected_slot": 0,
}

class Account:
    def __init__(self, data=None):
        data = data or {}
        self.username = data.get("username", DEFAULT_ACCOUNT["username"])
        inv = data.get("inventory")
        if not isinstance(inv, list) or len(inv) != HOTBAR_SLOTS:
            inv = [{"tile": None, "count": 0} for _ in range(HOTBAR_SLOTS)]
        clean = []
        for entry in inv:
            if not isinstance(entry, dict):
                clean.append({"tile": None, "count": 0})
                continue
            tile = entry.get("tile")
            count = entry.get("count", 0)
            if tile not in (DIRT, GRASS, STONE):
                tile, count = None, 0
            if tile is None:
                count = 0
            clean.append({"tile": tile, "count": int(count)})
        clean[0] = {"tile": None, "count": 0}
        self.inventory = clean
        self.selected_slot = int(data.get("selected_slot", 0))
        if not (0 <= self.selected_slot < HOTBAR_SLOTS):
            self.selected_slot = 0

    def to_dict(self):
        return {
            "username": self.username,
            "inventory": self.inventory,
            "selected_slot": self.selected_slot,
        }

def load_accounts():
    raw = _read_json(ACCOUNTS_FILE, {})
    if not isinstance(raw, dict):
        raw = {}
    return {name: Account(data) for name, data in raw.items()}

def save_accounts(accounts):
    _write_json(ACCOUNTS_FILE, {name: acc.to_dict() for name, acc in accounts.items()})

# ---------------------------------------------------------------
# World
# ---------------------------------------------------------------
class World:
    """
    Layout:
        0 .. SURFACE_ROW-1                sky
        SURFACE_ROW                       grass (spawn row)
        SURFACE_ROW+1 .. BEDROCK_ROW-1    dirt/stone with scattered lava pockets
        BEDROCK_ROW                       bedrock line
        BEDROCK_ROW+1 .. GRID_H-1         bedrock padding
    Anything below the grid is bedrock via `get()`.
    """
    # lava pocket tuning
    LAVA_POCKET_MIN_DEPTH   = 14      # no lava in the shallow dirt
    LAVA_POCKET_SEEDS       = 26      # how many pocket seeds per column-depth
    LAVA_POCKET_MIN_SIZE    = 3
    LAVA_POCKET_MAX_SIZE    = 9

    def __init__(self, name, tiles=None, spawn=None):
        self.name = name
        self.tiles = tiles if tiles is not None else self._generate_terrain()
        self.spawn = spawn if spawn else [GRID_W // 2, SURFACE_ROW]
        self.navigation_revision = 0  # runtime-only; excluded from saves
        self.navigation_changes = []
        self.navigation_change_floor = 0
        self.navigation_budget_enabled = False
        self.navigation_budget_remaining = 1

    def navigation_changed(self, column, row):
        self.navigation_revision += 1
        self.navigation_changes.append((self.navigation_revision, column, row))
        if len(self.navigation_changes) > 512:
            removed = self.navigation_changes.pop(0)
            self.navigation_change_floor = removed[0]

    def _generate_terrain(self):
        tiles = [[AIR] * GRID_W for _ in range(GRID_H)]

        # surface grass
        for c in range(GRID_W):
            tiles[SURFACE_ROW][c] = GRASS

        # underground — dirt near surface, leaning stone deeper
        for row in range(SURFACE_ROW + 1, BEDROCK_ROW):
            depth = row - SURFACE_ROW
            for c in range(GRID_W):
                tiles[row][c] = self._tile_for_depth(depth)

        # scattered lava pockets, only in the deeper stone layers
        self._scatter_lava(tiles)

        # bedrock line + padding
        for row in range(BEDROCK_ROW, GRID_H):
            for c in range(GRID_W):
                tiles[row][c] = BEDROCK

        return tiles

    def _tile_for_depth(self, depth):
        if depth <= 2:
            return DIRT
        if depth <= 8:
            return STONE if random.random() < 0.10 else DIRT
        if depth <= 20:
            return STONE if random.random() < 0.45 else DIRT
        return STONE if random.random() < 0.80 else DIRT

    def _scatter_lava(self, tiles):
        min_row = SURFACE_ROW + self.LAVA_POCKET_MIN_DEPTH
        max_row = BEDROCK_ROW - 2      # keep a solid buffer above bedrock
        if max_row <= min_row:
            return

        for _ in range(self.LAVA_POCKET_SEEDS):
            seed_c = random.randint(1, GRID_W - 2)
            seed_r = random.randint(min_row, max_row)

            size = random.randint(self.LAVA_POCKET_MIN_SIZE,
                                  self.LAVA_POCKET_MAX_SIZE)
            # grow a small blob using random walk from the seed
            c, r = seed_c, seed_r
            for _ in range(size):
                if 0 <= c < GRID_W and min_row <= r <= max_row:
                    # only convert solid stone/dirt — never punch through air
                    if tiles[r][c] in (DIRT, STONE):
                        tiles[r][c] = LAVA
                # step in a random cardinal direction, biased horizontally
                d = random.choice([(-1, 0), (1, 0), (-1, 0), (1, 0),
                                   (0, -1), (0, 1)])
                c += d[0]
                r += d[1]

    def get(self, c, r):
        if not (0 <= c < GRID_W):
            return BEDROCK
        if r < 0:
            return AIR
        if r >= GRID_H:
            return BEDROCK
        return self.tiles[r][c]

    def is_solid(self, c, r):
        return TILE_COLLIDES[self.get(c, r)]

    def is_lava(self, c, r):
        return self.get(c, r) == LAVA

    def height(self):
        return GRID_H

    def row_to_y(self, r):
        return SURFACE_ROW - r

    def y_to_row(self, y):
        return SURFACE_ROW - y

    def to_dict(self):
        return {"name": self.name, "tiles": self.tiles, "spawn": self.spawn}

    @classmethod
    def from_dict(cls, d):
        return cls(d["name"], d.get("tiles"), d.get("spawn"))

    @classmethod
    def from_any(cls, entry):
        if isinstance(entry, str):
            return cls(entry)
        return cls.from_dict(entry)

# ---------------------------------------------------------------
# Player
# ---------------------------------------------------------------
def _lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))

class Player:
    def __init__(self, world, spawn_tile):
        self.world = world
        col, row = spawn_tile
        self.spawn_x = float(col * TILE + (TILE - PLAYER_W) // 2)
        self.spawn_y = float(row * TILE - PLAYER_H)
        self.x = self.spawn_x
        self.y = self.spawn_y
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.facing = 1
        self.sprinting = False
        self.fall_distance = 0.0
        self._was_descending = False
        self.landing_fall_distance = 0.0
        self.dash_remaining_ms = 0.0
        self.dash_cooldown_ms = 0.0
        self.dash_direction = 1
        self._dash_resume_vy = 0.0
        self.dash_started_event = None
        self._dash_request = None
        self._q_held = False
        self._dash_jump_blocked = False
        self.landing_recovery_ms = 0.0
        self.heavy_landing_started = False
        self.heavy_landing_sound_played = False
        self._recovery_anchor = None
        self._recovery_blocked_keys = set()

        self.max_hp = MAX_HP
        self.hp = MAX_HP
        self.flash_ms = 0.0
        self.invuln_ms = 0.0
        self.knockback_ms = 0.0
        self.time_since_damage_ms = 0.0
        self.sprinting = False

    def _collides(self, x, y):
        return overlaps_solid(self.world, x, y, PLAYER_W, PLAYER_H, TILE)

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), PLAYER_W, PLAYER_H)

    def overlapping_lava_tiles(self):
        rect = self.rect()
        c0 = rect.left // TILE
        c1 = (rect.right - 1) // TILE
        r0 = rect.top // TILE
        r1 = (rect.bottom - 1) // TILE
        hits = []
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if self.world.is_lava(c, r):
                    hits.append((c, r))
        return hits

    def apply_damage(self, amount):
        if amount > 0:
            self._end_dash()
            self._dash_request = None
        damage_character(self, amount, LAVA_FLASH_MS)
        if self.hp <= 0:
            self.cancel_recovery()

    @property
    def recovering(self):
        return self.landing_recovery_ms > 1e-8

    def cancel_recovery(self):
        self.landing_recovery_ms = 0.0
        self.heavy_landing_started = False
        self.heavy_landing_sound_played = False
        self._recovery_anchor = None

    def _begin_recovery(self):
        self._end_dash()
        self._dash_request = None
        self.vx = self.vy = 0.0
        self.sprinting = False
        self.landing_recovery_ms = HEAVY_LANDING_RECOVERY_MS
        self.heavy_landing_started = True
        self._recovery_anchor = (self.x, self.y)

    @property
    def dashing(self):
        return self.dash_remaining_ms > 1e-8

    def request_dash(self, keys=None):
        """Latch direction at the key edge, including taps between fixed ticks."""
        self._q_held = True
        if self.recovering or self.dashing or self.dash_cooldown_ms > 1e-8 or self.hp <= 0:
            return False
        if self._dash_request is None:
            if keys is None:
                keys = pygame.key.get_pressed()
            left = bool(keys[pygame.K_a] or keys[pygame.K_LEFT])
            right = bool(keys[pygame.K_d] or keys[pygame.K_RIGHT])
            self._dash_request = (int(right) - int(left)) or self.facing
        return True

    def _end_dash(self):
        if self.dashing:
            self.dash_remaining_ms = 0.0
            self.dash_cooldown_ms = DASH_COOLDOWN_MS
            self.vx = 0.0
            self.vy = self._dash_resume_vy

    def cancel_dash_input(self):
        self._dash_request = None
        # A held key across pause/focus changes must be released first.
        self._q_held = True

    def apply_knockback(self, from_tile):
        self.cancel_recovery()
        c, r = from_tile
        knockback_character(self, c*TILE+TILE/2, PLAYER_W, LAVA_KNOCKBACK_X,
                            LAVA_KNOCKBACK_Y, LAVA_KNOCKBACK_LOCK, LAVA_INVULN_MS)

    def respawn(self):
        self.cancel_recovery()
        self._recovery_blocked_keys.clear()
        self.x = self.spawn_x
        self.y = self.spawn_y
        self.vx = 0.0
        self.vy = 0.0
        self.hp = self.max_hp
        self.flash_ms = 0.0
        self.invuln_ms = 0.0
        self.knockback_ms = 0.0
        self.time_since_damage_ms = 0.0
        self.on_ground = False
        self.fall_distance = 0.0
        self._was_descending = False
        self.landing_fall_distance = 0.0
        self.dash_remaining_ms = 0.0
        self.dash_cooldown_ms = 0.0
        self._dash_request = None
        self._dash_resume_vy = 0.0
        self.dash_started_event = None

    def update(self, dt, keys):
        # GameScene supplies fixed simulation steps, preserving the original
        # 60 Hz jump trajectory independently of the rendering frame rate.
        f = dt / SIMULATION_STEP_MS
        self.heavy_landing_started = False
        held = {key for key in RECOVERY_CONTROL_KEYS if keys[key]}
        self._recovery_blocked_keys.intersection_update(held)
        if self.recovering:
            self._recovery_blocked_keys.update(held)
            self._dash_request = None
        if self._recovery_blocked_keys:
            raw_keys = keys
            blocked = self._recovery_blocked_keys
            class RecoveryKeys:
                def __getitem__(self, key):
                    return False if key in blocked else raw_keys[key]
            keys = RecoveryKeys()
        self.dash_started_event = None
        self.dash_cooldown_ms = max(0.0, self.dash_cooldown_ms - dt)
        q_held = bool(keys[pygame.K_q])
        if q_held and not self._q_held:
            self.request_dash(keys)
        self._q_held = q_held
        dash_started = self._dash_request is not None
        if self._dash_request is not None:
            self.dash_direction = self._dash_request
            self.dash_remaining_ms = DASH_DURATION_MS
            self._dash_request = None
            self.dash_started_event = (self.x, self.y, self.dash_direction)

        if self.flash_ms > 0:
            self.flash_ms = max(0.0, self.flash_ms - dt)
        if self.invuln_ms > 0:
            self.invuln_ms = max(0.0, self.invuln_ms - dt)
        if self.knockback_ms > 0:
            self.knockback_ms = max(0.0, self.knockback_ms - dt)
        self.time_since_damage_ms += dt

        if (self.time_since_damage_ms >= REGEN_DELAY_MS
                and self.hp < self.max_hp):
            self.hp = min(self.max_hp, self.hp + REGEN_PER_SEC * (dt / 1000.0))

        if self.recovering:
            anchor_x, anchor_y = self._recovery_anchor
            supported = overlaps_solid(self.world, self.x, self.y + 1,
                                       PLAYER_W, PLAYER_H, TILE)
            if (supported and self.hp > 0 and self.knockback_ms <= 0 and
                    abs(self.x - anchor_x) < .01 and abs(self.y - anchor_y) < .01):
                self.vx = self.vy = 0.0
                self.sprinting = False
                self.landing_fall_distance = 0.0
                integrate_character(self, dt, CHARACTER_PHYSICS)
                self.landing_recovery_ms = max(0.0, self.landing_recovery_ms - dt)
                if not self.recovering:
                    self.cancel_recovery()
                return False
            self.cancel_recovery()

        input_vx = 0.0
        sprint_held = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            input_vx = -MOVE_SPEED
            self.facing = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            input_vx = MOVE_SPEED
            self.facing = 1
        self.sprinting = bool(input_vx and sprint_held)
        if self.sprinting:
            input_vx *= SPRINT_SPEED_MULTIPLIER

        if self.knockback_ms > 0:
            self.vx = self.vx + input_vx * LAVA_KNOCKBACK_DAMP * f
            self.vx *= (1.0 - 0.05 * f)
        else:
            self.vx = input_vx

        if self.dashing:
            self.vx = self.dash_direction * DASH_SPEED
            self.facing = self.dash_direction

        self.landing_fall_distance = 0.0
        was_grounded = self.on_ground
        jump_held = bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP])
        if not jump_held:
            self._dash_jump_blocked = False
        elif self.dashing:
            self._dash_jump_blocked = True
        jumped = (jump_held and self.on_ground and not self.dashing
                  and not self._dash_jump_blocked)
        if jumped:
            self.vy = JUMP_VELOCITY
            self.on_ground = False
            self.heavy_landing_sound_played = False
        if dash_started:
            self._dash_resume_vy = max(0.0, self.vy)

        old_y = self.y
        vertical_velocity = self.vy
        if self.dashing:
            dash_dt = min(dt, self.dash_remaining_ms)
            old_x = self.x
            integrate_character(self, dash_dt, CHARACTER_PHYSICS,
                                vertical_velocity=0.0)
            expected_dx = self.dash_direction * DASH_SPEED * dash_dt / SIMULATION_STEP_MS
            hit_horizontal_obstacle = abs((self.x - old_x) - expected_dx) > 1e-6
            remaining = self.dash_remaining_ms - dash_dt
            if hit_horizontal_obstacle or self.vx == 0.0 or remaining <= 1e-8:
                self._end_dash()
            else:
                self.dash_remaining_ms = remaining
            if dt > dash_dt:
                self.vx = input_vx
                integrate_character(self, dt - dash_dt, CHARACTER_PHYSICS)
                self.dash_cooldown_ms = max(
                    0.0, self.dash_cooldown_ms - (dt - dash_dt))
        else:
            integrate_character(self, dt, CHARACTER_PHYSICS)

        if was_grounded and not self.on_ground:
            # A fresh walk-off fall must be able to schedule its own impact.
            self.heavy_landing_sound_played = False

        # Track only actual downward displacement. An upward jump or knockback
        # starts a fresh descent, so its ascent is never counted as fall height.
        downward_distance = max(0.0, self.y - old_y)
        if jumped or vertical_velocity < 0.0:
            self.fall_distance = 0.0
            self._was_descending = False
        descending_step = (vertical_velocity > 0.0 or
                           (not jumped and self.vy > 0.0) or
                           (not jumped and downward_distance > 0.0))
        if descending_step:
            self.fall_distance += downward_distance
            self._was_descending = True

        if self.on_ground:
            if not was_grounded and self._was_descending:
                self.landing_fall_distance = self.fall_distance
            self.fall_distance = 0.0
            self._was_descending = False
            if (self.landing_fall_distance > HEAVY_LANDING_THRESHOLD_TILES * TILE
                    and self.hp > 0 and not self.overlapping_lava_tiles()):
                self._begin_recovery()
        return bool(jumped)

    def draw(self, surface, cam_x, cam_y, animation=None, punch_progress=None):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)

        flash_ratio = self.flash_ms / LAVA_FLASH_MS if LAVA_FLASH_MS > 0 else 0.0
        body_col = _lerp_color(BODY_COLOR, FLASH_COLOR, flash_ratio)
        head_col = _lerp_color(HEAD_COLOR, FLASH_COLOR, flash_ratio)

        renderer = animation if animation is not None else PlayerAnimation()
        renderer.draw(surface, sx, sy, PLAYER_W, PLAYER_H, self.facing,
                      head_col, body_col, OUTLINE, punch_progress, flash_ratio)

# ---------------------------------------------------------------
# Dropped item
# ---------------------------------------------------------------
class DroppedItem:
    def __init__(self, world, tile_type, tile_col, tile_row):
        self.world = world
        self.tile_type = tile_type
        self.color = TILE_COLORS[tile_type]
        offset_rng = random.Random()
        self.x = (tile_col + 0.5) * TILE - DROP_SIZE / 2 + offset_rng.uniform(
            -DROP_SPAWN_JITTER, DROP_SPAWN_JITTER)
        self.y = (tile_row + 0.5) * TILE - DROP_SIZE / 2 + offset_rng.uniform(
            -DROP_SPAWN_JITTER, DROP_SPAWN_JITTER)
        self.collected = False
        self.age_ms = 0.0
        self.bob_offset = 0.0

    def update(self, dt, player):
        self.age_ms += dt
        pop_phase = min(1.0, self.age_ms / DROP_POP_DURATION_MS)
        pop_offset = (-DROP_POP_HEIGHT * math.sin(math.pi * pop_phase)
                      if pop_phase < 1.0 else 0.0)
        self.bob_offset = pop_offset + DROP_BOB_HEIGHT * math.sin(
            self.age_ms * DROP_BOB_SPEED)

        px = player.x + PLAYER_W / 2
        py = player.y + PLAYER_H / 2
        ix = self.x + DROP_SIZE / 2
        iy = self.y + DROP_SIZE / 2 + self.bob_offset
        if (not getattr(player, "recovering", False) and
                (px - ix) ** 2 + (py - iy) ** 2 <= PICKUP_RADIUS ** 2):
            self.collected = True

    def draw(self, surface, cam_x, cam_y, textures=None):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y + self.bob_offset)
        border_rect = pygame.Rect(sx - 2, sy - 2, DROP_SIZE + 4, DROP_SIZE + 4)
        pygame.draw.rect(surface, (0, 0, 0), border_rect, border_radius=4)
        body_rect = pygame.Rect(sx, sy, DROP_SIZE, DROP_SIZE)
        texture = (textures or {}).get(self.tile_type)
        if texture is not None:
            surface.blit(texture, body_rect)
        else:
            pygame.draw.rect(surface, self.color, body_rect, border_radius=3)
            hi = (min(255, self.color[0] + 40),
                  min(255, self.color[1] + 40),
                  min(255, self.color[2] + 40))
            pygame.draw.rect(surface, hi, (sx + 2, sy + 2, DROP_SIZE - 4, 3))

# ---------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------
class Button:
    def __init__(self, rect, text, font, on_click):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.on_click = on_click
        self.hovered = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.on_click()

    def draw(self, surface):
        color = BTN_HOVER if self.hovered else BTN_COLOR
        pygame.draw.rect(surface, (0, 0, 0, 100), self.rect.move(0, 6), border_radius=16)
        pygame.draw.rect(surface, color, self.rect, border_radius=16)
        pygame.draw.rect(surface, (0, 0, 0), self.rect, width=3, border_radius=16)
        text_surf = self.font.render(self.text, True, BTN_TEXT)
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))


class TextBox:
    def __init__(self, rect, font, max_len=24):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.text = ""
        self.focused = False
        self.max_len = max_len
        self.cursor_visible = True
        self.cursor_timer = 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focused = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.focused:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                return "submit"
            elif event.unicode and event.unicode.isprintable() and len(self.text) < self.max_len:
                if event.unicode.isalnum() or event.unicode == " ":
                    self.text += event.unicode
        return None

    def update(self, dt):
        self.cursor_timer += dt
        if self.cursor_timer >= 500:
            self.cursor_timer = 0
            self.cursor_visible = not self.cursor_visible

    def draw(self, surface):
        pygame.draw.rect(surface, (0, 0, 0), self.rect.move(0, 4), border_radius=10)
        pygame.draw.rect(surface, INPUT_BG, self.rect, border_radius=10)
        border_color = (255, 200, 60) if self.focused else (0, 0, 0)
        pygame.draw.rect(surface, border_color, self.rect, width=3, border_radius=10)
        text_surf = self.font.render(self.text, True, INPUT_TEXT)
        surface.blit(text_surf, (self.rect.x + 16, self.rect.centery - text_surf.get_height() // 2))
        if self.focused and self.cursor_visible:
            cx = self.rect.x + 16 + text_surf.get_width() + 2
            pygame.draw.line(surface, INPUT_TEXT,
                             (cx, self.rect.y + 14),
                             (cx, self.rect.bottom - 14), 3)


class WorldList:
    def __init__(self, rect, font, on_select):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.on_select = on_select
        self.row_h = 60
        self.scroll = 0
        self.hover_index = -1
        self.items = []

    def set_items(self, items):
        self.items = items
        max_scroll = max(0, len(self.items) * self.row_h - self.rect.height)
        self.scroll = min(self.scroll, max_scroll)

    def _row_rect(self, i):
        y = self.rect.y + i * self.row_h - self.scroll
        return pygame.Rect(self.rect.x, y, self.rect.width, self.row_h)

    def _index_at(self, pos):
        if not self.rect.collidepoint(pos):
            return -1
        for i in range(len(self.items)):
            if self._row_rect(i).collidepoint(pos):
                return i
        return -1

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover_index = self._index_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            idx = self._index_at(event.pos)
            if idx >= 0:
                self.on_select(self.items[idx])
        elif event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if self.rect.collidepoint((mx, my)):
                max_scroll = max(0, len(self.items) * self.row_h - self.rect.height)
                self.scroll = max(0, min(max_scroll, self.scroll - event.y * 40))

    def draw(self, surface):
        pygame.draw.rect(surface, PANEL_BG, self.rect, border_radius=12)
        pygame.draw.rect(surface, (0, 0, 0), self.rect, width=3, border_radius=12)

        if not self.items:
            empty = self.font.render("No worlds yet — create one!", True, (180, 200, 230))
            surface.blit(empty, empty.get_rect(center=self.rect.center))
            return

        prev_clip = surface.get_clip()
        surface.set_clip(self.rect)

        for i, name in enumerate(self.items):
            row = self._row_rect(i)
            if row.bottom < self.rect.y or row.y > self.rect.bottom:
                continue
            base = PANEL_ALT if i % 2 == 0 else PANEL_BG
            if i == self.hover_index:
                base = PANEL_HOVER
            pygame.draw.rect(surface, base, row)
            pygame.draw.line(surface, (0, 0, 0),
                             (row.x, row.bottom - 1), (row.right, row.bottom - 1), 1)
            label = self.font.render(name, True, TEXT_COLOR)
            surface.blit(label, (row.x + 24, row.centery - label.get_height() // 2))
            arrow = self.font.render(">", True, ROW_BORDER)
            surface.blit(arrow, (row.right - 40, row.centery - arrow.get_height() // 2))

        surface.set_clip(prev_clip)

        total = len(self.items) * self.row_h
        if total > self.rect.height:
            bar_h = max(40, int(self.rect.height * self.rect.height / total))
            max_scroll = total - self.rect.height
            t = self.scroll / max_scroll if max_scroll else 0
            bar_y = self.rect.y + int((self.rect.height - bar_h) * t)
            bar = pygame.Rect(self.rect.right - 12, bar_y, 6, bar_h)
            pygame.draw.rect(surface, ROW_BORDER, bar, border_radius=3)


class Hotbar:
    def __init__(self, screen_w, screen_h, font, count_font, account):
        self.font = font
        self.count_font = count_font
        self.account = account
        self.hover = -1

        self.set_layout(HUDRenderer((screen_w, screen_h)).layout.hotbar_slots)

    def set_layout(self, slot_rects):
        self.slots = [pygame.Rect(rect) for rect in slot_rects]

    @property
    def items(self):
        return self.account.inventory

    @property
    def selected(self):
        return self.account.selected_slot

    def select(self, index):
        if 0 <= index < HOTBAR_SLOTS:
            self.account.selected_slot = index

    def selected_item(self):
        return self.account.inventory[self.account.selected_slot]

    def is_placement_mode(self):
        return self.selected_item()["tile"] is not None

    def _ensure_fist_slot_available(self):
        inv = self.account.inventory
        if inv[0]["tile"] is not None:
            for i in range(1, HOTBAR_SLOTS):
                if inv[i]["tile"] is None:
                    inv[0], inv[i] = inv[i], inv[0]
                    return
            inv[0] = {"tile": None, "count": 0}

    def add_item(self, tile_type, amount=1):
        if tile_type in (BEDROCK, LAVA):
            return
        inv = self.account.inventory
        for item in inv:
            if item["tile"] == tile_type:
                item["count"] += amount
                return
        for i in range(1, HOTBAR_SLOTS):
            if inv[i]["tile"] is None:
                inv[i]["tile"] = tile_type
                inv[i]["count"] = amount
                return

    def consume_selected(self):
        inv = self.account.inventory
        item = inv[self.account.selected_slot]
        if item["tile"] is None or item["count"] <= 0:
            return False
        item["count"] -= 1
        if item["count"] <= 0:
            item["tile"] = None
            item["count"] = 0
            self._ensure_fist_slot_available()
            if self.account.selected_slot != 0 and inv[self.account.selected_slot]["tile"] is None:
                self.account.selected_slot = 0
        return True

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = -1
            for i, rect in enumerate(self.slots):
                if rect.collidepoint(event.pos):
                    self.hover = i
                    break
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self.slots):
                if rect.collidepoint(event.pos):
                    self.select(i)
                    break
        elif event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key <= pygame.K_8:
                self.select(event.key - pygame.K_1)
        elif event.type == pygame.MOUSEWHEEL:
            self.select((self.account.selected_slot - event.y) % HOTBAR_SLOTS)

    def draw(self, surface, block_icons=None):
        inv = self.account.inventory
        selected = self.account.selected_slot
        for i, rect in enumerate(self.slots):
            item = inv[i]
            bg = HOTBAR_HOVER if i == self.hover else HOTBAR_BG
            pygame.draw.rect(surface, bg, rect, border_radius=8)
            pygame.draw.rect(surface, HOTBAR_BORDER, rect, width=3, border_radius=8)

            pad = 10
            swatch = rect.inflate(-pad * 2, -pad * 2)
            if item["tile"] is not None and item["count"] > 0:
                color = TILE_COLORS[item["tile"]]
                icon = (block_icons or {}).get(item["tile"])
                if icon is not None:
                    surface.blit(icon, swatch)
                else:
                    pygame.draw.rect(surface, color, swatch, border_radius=6)
                pygame.draw.rect(surface, HOTBAR_BORDER, swatch, width=2, border_radius=6)
                if icon is None:
                    hi = (min(255, color[0] + 40),
                          min(255, color[1] + 40),
                          min(255, color[2] + 40))
                    pygame.draw.rect(surface, hi, (swatch.x + 2, swatch.y + 2,
                                                   swatch.w - 4, 3))
                count_surf = self.count_font.render(str(item["count"]), True,
                                                    HOTBAR_COUNT_COLOR)
                shadow = self.count_font.render(str(item["count"]), True,
                                                HOTBAR_COUNT_SHADOW)
                cx = rect.right - count_surf.get_width() - 6
                cy = rect.bottom - count_surf.get_height() - 2
                surface.blit(shadow, (cx + 1, cy + 1))
                surface.blit(count_surf, (cx, cy))
            else:
                pygame.draw.rect(surface, HOTBAR_EMPTY_COLOR, swatch, border_radius=6)
                pygame.draw.rect(surface, HOTBAR_BORDER, swatch, width=2, border_radius=6)
                if i == 0:
                    draw_fist_icon(surface, swatch.center, 30, (230, 240, 255))

            if i == selected:
                pygame.draw.rect(surface, HOTBAR_SELECTED, rect, width=4, border_radius=8)

            num = self.font.render(str(i + 1), True, (230, 240, 255))
            surface.blit(num, (rect.x + 6, rect.y + 2))

    def current_label(self):
        item = self.selected_item()
        if item["tile"] is None:
            return "Fist"
        return TILE_NAMES.get(item["tile"], "Block")

# ---------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------
class Scene:
    def __init__(self, game):
        self.game = game

    def handle_event(self, event): ...
    def update(self, dt): ...
    def draw(self, surface): ...

class MenuScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        btn_w, btn_h = 360, 90
        cx = WIDTH // 2

        self.name_input = TextBox((cx - 300, 380, 600, 70), game.input_font, max_len=16)
        self.name_input.text = game.current_username or ""

        self.buttons = [
            Button((cx - btn_w // 2, 500, btn_w, btn_h), "PLAY",
                   game.btn_font, self.on_play),
            Button((cx - btn_w // 2, 620, btn_w, btn_h), "EXIT",
                   game.btn_font, self.on_exit),
        ]
        self.message = ""

    def on_play(self):
        name = self.name_input.text.strip()
        if not name:
            self.message = "Enter a username first."
            return
        self.game.set_username(name)
        self.game.change_scene(CreateWorldScene(self.game))

    def on_exit(self):
        self.game.save_accounts()
        self.game.running = False

    def handle_event(self, event):
        self.name_input.handle_event(event)
        for b in self.buttons:
            b.handle_event(event)

    def update(self, dt):
        self.name_input.update(dt)

    def draw(self, surface):
        surface.blit(self.game.bg, (0, 0))
        title_surf = self.game.title_font.render(TITLE, True, TITLE_COLOR)
        title_rect = title_surf.get_rect(center=(WIDTH // 2, 200))
        shadow = self.game.title_font.render(TITLE, True, (0, 0, 0))
        surface.blit(shadow, title_rect.move(4, 4))
        surface.blit(title_surf, title_rect)

        label = self.game.label_font.render("Username:", True, TITLE_COLOR)
        surface.blit(label, label.get_rect(center=(WIDTH // 2, 340)))
        self.name_input.draw(surface)

        if self.message:
            msg = self.game.small_font.render(self.message, True, (255, 140, 140))
            surface.blit(msg, msg.get_rect(center=(WIDTH // 2, 470)))

        for b in self.buttons:
            b.draw(surface)

class CreateWorldScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.message = ""
        self.message_color = (255, 120, 120)

        left_x, left_w = 80, 620
        self.input = TextBox((left_x + 40, 340, left_w - 80, 80),
                             game.input_font, max_len=24)
        self.btn_enter = Button((left_x + 40, 460, left_w - 80, 80),
                                "ENTER", game.btn_font, self.on_enter)

        right_x = 780
        right_w = WIDTH - right_x - 80
        self.world_list = WorldList(
            (right_x, 220, right_w, HEIGHT - 380),
            game.list_font,
            on_select=self.on_select_world,
        )
        self.back_btn = Button((80, HEIGHT - 130, 260, 80),
                               "BACK", game.btn_font, self.on_back)
        self.refresh_list()

    def refresh_list(self):
        self.world_list.set_items([w.name for w in self.game.worlds])

    def on_back(self):
        self.game.change_scene(MenuScene(self.game))

    def on_enter(self):
        name = self.input.text.strip()
        if not name:
            self.message = "Please enter a world name."
            return
        if any(w.name == name for w in self.game.worlds):
            self.message = f"World '{name}' already exists."
            return

        world = World(name)
        self.game.worlds.append(world)
        self.game.save_worlds()
        self.game.change_scene(GameScene(self.game, world))

    def on_select_world(self, name):
        world = next(w for w in self.game.worlds if w.name == name)
        self.game.change_scene(GameScene(self.game, world))

    def handle_event(self, event):
        if self.input.handle_event(event) == "submit":
            self.on_enter()
        self.world_list.handle_event(event)
        self.btn_enter.handle_event(event)
        self.back_btn.handle_event(event)

    def update(self, dt):
        self.input.update(dt)

    def draw(self, surface):
        surface.blit(self.game.bg, (0, 0))
        header = self.game.subtitle_font.render("Worlds", True, TITLE_COLOR)
        surface.blit(header, header.get_rect(center=(WIDTH // 2, 100)))

        who = self.game.small_font.render(
            f"Logged in as: {self.game.current_username}", True, (220, 235, 255))
        surface.blit(who, (80, 90))

        left_panel = pygame.Rect(60, 180, 660, HEIGHT - 340)
        pygame.draw.rect(surface, PANEL_BG, left_panel, border_radius=12)
        pygame.draw.rect(surface, (0, 0, 0), left_panel, width=3, border_radius=12)

        title = self.game.label_font.render("Create a new world", True, TITLE_COLOR)
        surface.blit(title, (left_panel.x + 40, left_panel.y + 40))
        hint = self.game.small_font.render(
            "Letters, numbers and spaces (max 24).", True, (180, 200, 230))
        surface.blit(hint, (left_panel.x + 40, left_panel.y + 90))
        label = self.game.label_font.render("World name:", True, TITLE_COLOR)
        surface.blit(label, (left_panel.x + 40, left_panel.y + 140))

        self.input.draw(surface)
        self.btn_enter.draw(surface)

        if self.message:
            msg = self.game.small_font.render(self.message, True, self.message_color)
            surface.blit(msg, (left_panel.x + 40, left_panel.y + 560))

        right_header = self.game.label_font.render(
            f"Your worlds ({len(self.game.worlds)})", True, TITLE_COLOR)
        surface.blit(right_header, (780, 180))
        self.world_list.draw(surface)
        self.back_btn.draw(surface)

class GameScene(Scene):
    def __init__(self, game, world):
        super().__init__(game)
        self.audio = getattr(game, "audio", NULL_AUDIO)
        self.world = world
        self.world.navigation_budget_enabled = True
        self.player = Player(world, tuple(world.spawn))
        self.background = BackgroundRenderer((WIDTH, HEIGHT))
        self.falling_camera = FallingCamera(FALL_ZOOM_START_TILES * TILE,
                                            FALL_ZOOM_STRENGTH, HEAVY_LANDING_RECOVERY_MS)
        self._zoom_layer = None

        self.cam_x = self.player.x + PLAYER_W / 2 - WIDTH / 2
        self.cam_y = self.player.y + PLAYER_H / 2 - HEIGHT / 2
        self._clamp_camera()

        self.hotbar = Hotbar(WIDTH, HEIGHT, game.small_font,
                             game.hotbar_count_font, game.current_account)
        self.hud = HUDRenderer((WIDTH, HEIGHT))
        self.hotbar.set_layout(self.hud.layout.hotbar_slots)
        self.paused = False
        self.pause_page = "main"
        self.debug_visible = False
        self.navigation_debug_visible = False
        self.asset_manager = AssetManager(os.path.join(os.path.dirname(__file__), "assets"))
        self.block_textures = {}
        self.block_icons = {}
        self.block_drop_textures = {}
        self._terrain_variant_cache = {}
        for tile_type, path in BLOCK_TEXTURE_FILES.items():
            try:
                self.block_textures[tile_type] = self.asset_manager.scaled(
                    path, (TILE, TILE))
                self.block_icons[tile_type] = self.asset_manager.scaled(path, (44, 44))
                self.block_drop_textures[tile_type] = self.asset_manager.scaled(
                    path, (DROP_SIZE, DROP_SIZE))
            except (FileNotFoundError, pygame.error):
                # Missing or invalid art keeps the original colored fallback.
                continue
        try:
            self.punch_effect = PunchStretchEffect(self.asset_manager)
        except FileNotFoundError:
            self.punch_effect = None
        player_config = os.path.join("characters", "player", "animation.json")
        try:
            sprite_clips, animation_durations = self.asset_manager.load_animation_config(player_config)
        except FileNotFoundError:
            sprite_clips, animation_durations = {}, None
        self.player_animation = PlayerAnimation(animation_durations, sprite_clips)
        try:
            self.zombie_clips, self.zombie_durations = self.asset_manager.load_animation_config(
                "characters/zombie/animation.json")
        except FileNotFoundError:
            self.zombie_clips, self.zombie_durations = {}, None
        self.zombies = []
        self.punch = PunchAnim(PUNCH_DURATION)
        self.place_cooldown = 0.0
        self.damage = {}
        self.drops = []
        self.time_ms = 0.0
        self._next_block_hit_ms = 0.0
        self.effects = BlockEffects()
        self.simulation_accumulator_ms = 0.0
        self.pointer_pos = pygame.mouse.get_pos()
        self._held_buttons = set()
        self._held_signature = None
        self._repeat_remaining = 0.0
        self._pending_jump = False
        self._focused = True
        self._skip_next_update = False


    def _clamp_camera(self):
        self.cam_x = max(0, min(WORLD_W - WIDTH, self.cam_x))
        self.cam_y = max(0, self.cam_y)
        max_cam_y = GRID_H * TILE - HEIGHT
        if max_cam_y < 0:
            max_cam_y = 0
        self.cam_y = min(self.cam_y, max_cam_y)

    def on_exit(self):
        self._cancel_held_action()
        self.zombies.clear()
        self.game.save_worlds()
        self.game.save_accounts()
        self.game.change_scene(MenuScene(self.game))

    # --- helpers ---
    def _zoom_view_rect(self, size=(WIDTH, HEIGHT)):
        width, height = size
        zoom = self.falling_camera.zoom
        view_w, view_h = max(1, round(width / zoom)), max(1, round(height / zoom))
        focus_x = self.player.x + PLAYER_W / 2 - self.cam_x
        focus_y = self.player.y + PLAYER_H / 2 - self.cam_y
        x = max(0, min(width - view_w, round(focus_x * (1 - view_w / width))))
        y = max(0, min(height - view_h, round(focus_y * (1 - view_h / height))))
        return pygame.Rect(x, y, view_w, view_h)

    def _screen_to_world(self, mx, my):
        view = self._zoom_view_rect()
        return (self.cam_x + view.x + mx * view.width / WIDTH,
                self.cam_y + view.y + my * view.height / HEIGHT)

    def _screen_to_tile(self, mx, my):
        wx, wy = self._screen_to_world(mx, my)
        return int(wx // TILE), int(wy // TILE)

    def _tile_center_distance(self, c, r):
        px = self.player.x + PLAYER_W / 2
        py = self.player.y + PLAYER_H / 2
        tile_cx = c * TILE + TILE / 2
        tile_cy = r * TILE + TILE / 2
        dx = (tile_cx - px) / TILE
        dy = (tile_cy - py) / TILE
        return (dx * dx + dy * dy) ** 0.5

    def _punch_anim_toward(self, c, r):
        self._punch_toward_point((c*TILE+TILE/2, r*TILE+TILE/2))

    def _punch_toward_point(self, target_world):
        target_x = target_world[0]
        player_center_x = self.player.x + PLAYER_W / 2
        if target_x > player_center_x:
            self.player.facing = 1
        elif target_x < player_center_x:
            self.player.facing = -1

        # only restart the animation if it isn't currently in a swing
        if self.punch.active and self.punch.t < PUNCH_RESTART_MIN_MS:
            return
        origin_world = (
            self.player.x + PLAYER_W / 2,
            self.player.y + PLAYER_H / 2,
        )
        self.punch.start(origin_world, target_world)

    def spawn_zombie(self):
        if len(self.zombies) >= MAX_ZOMBIES:
            return None
        position = find_zombie_spawn(self.world, self.player, self.zombies, CHARACTER_PHYSICS)
        if position is None:
            return None
        zombie = Zombie(self.world, *position, CHARACTER_PHYSICS,
                        self.zombie_clips, self.zombie_durations)
        self.zombies.append(zombie)
        return zombie

    def _try_punch_zombie(self, target):
        if self.player.recovering:
            return False
        """None means no entity target; False blocks fallback damage behind one."""
        origin = (self.player.x+PLAYER_W/2, self.player.y+PLAYER_H/2)
        dx, dy = target[0]-origin[0], target[1]-origin[1]
        distance = math.hypot(dx, dy)
        scale = min(1, PUNCH_RANGE*TILE/distance) if distance else 1
        endpoint = origin[0]+dx*scale, origin[1]+dy*scale
        facing = 1 if dx > 0 else -1 if dx < 0 else self.player.facing
        candidates = []
        for zombie in self.zombies:
            if zombie.state == ZombieState.DEAD or (zombie.center[0]-origin[0])*facing < -2:
                continue
            fraction = segment_box_fraction(origin, endpoint, zombie.rect())
            if fraction is not None:
                candidates.append((fraction, zombie))
        if not candidates:
            return None
        fraction, zombie = min(candidates, key=lambda item: item[0])
        contact = (origin[0]+(endpoint[0]-origin[0])*fraction,
                   origin[1]+(endpoint[1]-origin[1])*fraction)
        self._punch_toward_point(zombie.center)
        if (self.time_ms+1e-8 < self._next_block_hit_ms or
                not line_clear(self.world, origin, contact, TILE)):
            return False
        if not zombie.take_damage(zombie.settings.punch_damage, origin[0]):
            return False
        self._next_block_hit_ms = self.time_ms+BLOCK_HIT_COOLDOWN_MS
        self.effects.emit(contact, (130, 150, 90), "hit")
        self.audio.play("block_hit_soft", channel_key="block_hit", volume=.5)
        return True

    def _selection_signature(self):
        return self.hotbar.selected, self.hotbar.selected_item()["tile"]

    def _cancel_held_action(self):
        self._held_buttons.clear()
        self._held_signature = None
        self._repeat_remaining = 0.0

    def _action_over_ui(self, pos):
        if not pygame.Rect(0, 0, self.hud.layout.width, self.hud.layout.height).collidepoint(pos):
            return True
        hotbar_panel = self.hotbar.slots[0].union(self.hotbar.slots[-1]).inflate(24, 16)
        hotbar_panel.height += 36
        hotbar_panel.top -= 36
        return (any(rect.collidepoint(pos) for rect in self.hud.layout.protected_rects) or
                hotbar_panel.collidepoint(pos) or
                (self.paused and self.hud.layout.pause_panel.collidepoint(pos)))

    def _sync_hud_layout(self):
        screen_size = self.game.screen.get_size()
        layout = self.hud.resize(screen_size)
        self.hotbar.set_layout(layout.hotbar_slots)

    def _handle_pause_action(self, position):
        action = self.hud.pause_action_at(position, self.pause_page)
        if action == "resume":
            self.paused = False
            self.pause_page = "main"
        elif action in ("settings", "controls"):
            self.pause_page = action
        elif action == "back":
            self.pause_page = "main"
        elif action == "scale_down":
            layout = self.hud.set_scale(self.hud.scale - .1)
            self.hotbar.set_layout(layout.hotbar_slots)
        elif action == "scale_up":
            layout = self.hud.set_scale(self.hud.scale + .1)
            self.hotbar.set_layout(layout.hotbar_slots)
        elif action == "save_exit":
            self.on_exit()

    def _act_at_pointer(self):
        if self.player.recovering:
            return False
        c, r = self._screen_to_tile(*self.pointer_pos)
        if self.hotbar.is_placement_mode():
            return self._try_place(c, r)
        entity_hit = self._try_punch_zombie(self._screen_to_world(*self.pointer_pos))
        if entity_hit is not None:
            return entity_hit
        return self._try_break(c, r)

    def _would_overlap_player(self, c, r):
        # Match the float collision bounds, including subpixel overlaps.
        return (self.player.x < (c + 1) * TILE and
                self.player.x + PLAYER_W > c * TILE and
                self.player.y < (r + 1) * TILE and
                self.player.y + PLAYER_H > r * TILE)

    # --- lava damage ---
    def _apply_lava_damage(self, dt):
        lava_hits = self.player.overlapping_lava_tiles()
        if not lava_hits:
            return

        hp_before = self.player.hp
        self.player.apply_damage(LAVA_DPS * (dt / 1000.0))
        if self.player.hp < hp_before:
            self.audio.play("burn", cooldown_ms=BURN_SOUND_COOLDOWN_MS)

        if self.player.invuln_ms <= 0:
            closest = min(
                lava_hits,
                key=lambda cr: (cr[0] * TILE - self.player.x) ** 2 +
                               (cr[1] * TILE - self.player.y) ** 2
            )
            self.player.apply_knockback(closest)

        self._check_player_death()

    def _heavy_landing_imminent(self, keys):
        """Predict a qualifying solid landing within the sound lead window."""
        player = self.player
        if (player.on_ground or player.dashing or player.recovering or
                player.hp <= 0 or player.vy <= 0 or player.knockback_ms > 0 or
                player.heavy_landing_sound_played):
            return False

        input_vx = 0.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            input_vx = -MOVE_SPEED
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            input_vx = MOVE_SPEED
        if input_vx and (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]):
            input_vx *= SPRINT_SPEED_MULTIPLIER

        probe = SimpleNamespace(world=self.world, x=player.x, y=player.y,
                                vx=input_vx, vy=player.vy, on_ground=False)
        elapsed = 0.0
        # Prediction runs before this tick's physics integration; account for
        # that integration plus one fixed-step sampling interval so audible
        # playback leads the eventual collision by the configured amount.
        prediction_window = (HEAVY_LANDING_SOUND_LEAD_MS +
                             2 * SIMULATION_STEP_MS)
        while elapsed < prediction_window:
            step = min(SIMULATION_STEP_MS,
                       prediction_window - elapsed)
            integrate_character(probe, step, CHARACTER_PHYSICS)
            elapsed += step
            if not probe.on_ground:
                continue

            projected_fall = player.fall_distance + max(0.0, probe.y - player.y)
            if projected_fall <= HEAVY_LANDING_THRESHOLD_TILES * TILE:
                return False
            # Lava remains a non-landing hazard and must not schedule the thud.
            c0 = math.floor(probe.x / TILE)
            c1 = math.floor((probe.x + PLAYER_W - 1e-5) / TILE)
            r0 = math.floor(probe.y / TILE)
            r1 = math.floor((probe.y + PLAYER_H - 1e-5) / TILE)
            return not any(self.world.is_lava(col, row)
                           for col in range(c0, c1 + 1)
                           for row in range(r0, r1 + 1))
        return False

    def _check_player_death(self):
        if self.player.hp > 0:
            return
        self.audio.play("death")
        self._cancel_held_action()
        self._pending_jump = False
        for zombie in self.zombies:
            # Give the player a brief respawn window without restoring the
            # ordinary chase disengagement blind period.
            zombie.disengage(ignore_ms=3000)
        self.player.respawn()
        self.falling_camera.reset()
        self.cam_x = self.player.x+PLAYER_W/2-WIDTH/2
        self.cam_y = self.player.y+PLAYER_H/2-HEIGHT/2
        self._clamp_camera()

    def _receive_enemy_attack(self, zombie, amount):
        if self.player.hp <= 0 or self.player.invuln_ms > 1e-8:
            return False
        self.player.apply_damage(amount)
        self.player.cancel_recovery()
        knockback_character(self.player, zombie.center[0], PLAYER_W,
                            LAVA_KNOCKBACK_X*.6, -6, LAVA_KNOCKBACK_LOCK, LAVA_INVULN_MS)
        self.effects.emit((self.player.x+PLAYER_W/2, self.player.y+PLAYER_H/2),
                          HEAD_COLOR, "hit")
        self._check_player_death()
        return True

    # --- breaking (manual clicks stay immediate; holding repeats on a timer) ---
    def _try_break(self, c, r):
        if self.player.recovering:
            return False
        if not (0 <= c < GRID_W and 0 <= r < GRID_H):
            return False
        tile = self.world.tiles[r][c]
        if self._tile_center_distance(c, r) > PUNCH_RANGE:
            return False

        self._punch_anim_toward(c, r)
        if tile in (AIR, BEDROCK):
            return False
        if self.time_ms + 1e-8 < self._next_block_hit_ms:
            return False

        entry = self.damage.setdefault((c, r), {"hits": 0, "timer": DAMAGE_RESET_MS})
        entry["hits"] += 1
        entry["timer"] = DAMAGE_RESET_MS
        needed = BREAK_HITS.get(tile, 2)
        broken = entry["hits"] >= needed
        self._next_block_hit_ms = self.time_ms + BLOCK_HIT_COOLDOWN_MS
        self.audio.play("block_hit_hard" if tile == STONE else "block_hit_soft",
                        channel_key="block_hit",
                        volume=(BLOCK_HIT_FINAL_VOLUME if broken
                                else BLOCK_HIT_SOUND_VOLUME))

        center = (c * TILE + TILE / 2, r * TILE + TILE / 2)
        self.effects.emit(center, TILE_COLORS[tile], "break" if broken else "hit")
        if broken:
            # lava drop goes to stone; other tiles drop themselves
            drop_tile = LAVA_DROP_TILE if tile == LAVA else tile
            self.world.tiles[r][c] = AIR
            self.world.navigation_changed(c, r)
            del self.damage[(c, r)]
            self.audio.play("block_hard" if tile == STONE else "block_soft")
            self.game.save_worlds()
            if random.random() < DROP_CHANCE:
                self.drops.append(DroppedItem(self.world, drop_tile, c, r))
        return True

    # --- placing (instant, with 200ms cooldown) ---
    def _try_place(self, c, r):
        if self.player.recovering:
            return False
        if self.place_cooldown > 1e-8:
            return False
        item = self.hotbar.selected_item()
        if item["tile"] is None or item["count"] <= 0:
            return False

        def rejected():
            self.audio.play("cant_place",
                            cooldown_ms=INVALID_PLACE_SOUND_COOLDOWN_MS)
            return False

        if not (0 <= c < GRID_W and 0 <= r < GRID_H):
            return rejected()
        if self.world.tiles[r][c] != AIR:
            return rejected()
        if self._tile_center_distance(c, r) > PLACE_RANGE:
            return rejected()
        if self._would_overlap_player(c, r):
            return rejected()
        if any(z.state != ZombieState.DEAD and
               z.rect().colliderect(pygame.FRect(c*TILE, r*TILE, TILE, TILE))
               for z in self.zombies):
            return rejected()

        # commit immediately
        tile_type = item["tile"]
        self.world.tiles[r][c] = tile_type
        self.world.navigation_changed(c, r)
        self.hotbar.consume_selected()
        self.place_cooldown = PLACE_COOLDOWN
        self._punch_anim_toward(c, r)
        center = (c * TILE + TILE / 2, r * TILE + TILE / 2)
        self.effects.emit(center, TILE_COLORS[tile_type], "place")
        self.audio.play("block_placed")
        self.game.save_worlds()
        self.game.save_accounts()
        return True

    # --- events ---
    def handle_event(self, event):
        self._sync_hud_layout()
        if event.type == pygame.WINDOWFOCUSLOST or (
                event.type == pygame.ACTIVEEVENT and event.state & 2 and not event.gain):
            self._focused = False
            self._cancel_held_action()
            self._pending_jump = False
            self.player.cancel_dash_input()
            self.simulation_accumulator_ms = 0.0
            return
        if event.type == pygame.WINDOWFOCUSGAINED or (
                event.type == pygame.ACTIVEEVENT and event.state & 2 and event.gain):
            self._focused = True
            self._skip_next_update = True
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F3:
            self.debug_visible = not self.debug_visible
            return
        if (event.type == pygame.KEYDOWN and event.key == pygame.K_F4 and
                not getattr(event, "repeat", False)):
            self.navigation_debug_visible = not self.navigation_debug_visible
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.paused = not self.paused
            self.pause_page = "main"
            self._cancel_held_action()
            self._pending_jump = False
            self.player.cancel_dash_input()
            self.simulation_accumulator_ms = 0.0
            return

        if not self._focused:
            return
        if self.paused:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_pause_action(event.pos)
            return
        if event.type == pygame.KEYUP and event.key in RECOVERY_CONTROL_KEYS:
            self.player._recovery_blocked_keys.discard(event.key)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F6:
            if not getattr(event, "repeat", False):
                self.spawn_zombie()
            return
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and
                self.hud.layout.pause_button.collidepoint(event.pos)):
            self.paused = True
            self.pause_page = "main"
            self._cancel_held_action()
            self._pending_jump = False
            self.player.cancel_dash_input()
            self.simulation_accumulator_ms = 0.0
            return
        if self.player.recovering:
            self._cancel_held_action()
            self._pending_jump = False
            if event.type == pygame.KEYDOWN and event.key in RECOVERY_CONTROL_KEYS:
                self.player._recovery_blocked_keys.add(event.key)
            return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_w, pygame.K_UP, pygame.K_SPACE):
            # Retain a short tap if down/up both arrive before the next fixed tick.
            self._pending_jump = True
        if (event.type == pygame.KEYDOWN and event.key == pygame.K_q and
                not getattr(event, "repeat", False) and not self.player._q_held):
            self.player.request_dash()
        if event.type == pygame.KEYUP and event.key == pygame.K_q:
            self.player._q_held = False
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.pointer_pos = event.pos
        if event.type == pygame.MOUSEBUTTONUP and event.button in (1, 3):
            self._held_buttons.discard(event.button)
            if not self._held_buttons:
                self._cancel_held_action()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            if self._action_over_ui(event.pos):
                self._cancel_held_action()
            else:
                self._held_buttons.add(event.button)
                self._held_signature = self._selection_signature()
                self._repeat_remaining = (PLACE_COOLDOWN if self.hotbar.is_placement_mode()
                                          else ACTION_REPEAT_MS)
                self._act_at_pointer()
                if self._held_signature != self._selection_signature():
                    self._cancel_held_action()

        previous_slot = self.hotbar.selected
        previous_selection = self._selection_signature()
        self.hotbar.handle_event(event)
        if self.hotbar.selected != previous_slot:
            self.audio.play("hotbar_select")
        if previous_selection != self._selection_signature():
            self._cancel_held_action()

    def update(self, dt):
        if not self._focused or self.paused:
            return
        if self._skip_next_update:
            self._skip_next_update = False
            return
        self.simulation_accumulator_ms += max(0.0, min(float(dt), MAX_FRAME_MS))
        keys = pygame.key.get_pressed()
        while self.simulation_accumulator_ms + 1e-8 >= SIMULATION_STEP_MS:
            if self._pending_jump:
                # This proxy also supports pygame's sparse high-valued key codes.
                class JumpKeys:
                    def __getitem__(self, key):
                        return key == pygame.K_SPACE or keys[key]
                self._simulate_step(SIMULATION_STEP_MS, JumpKeys())
                self._pending_jump = False
            else:
                self._simulate_step(SIMULATION_STEP_MS, keys)
            self.simulation_accumulator_ms = max(
                0.0, self.simulation_accumulator_ms - SIMULATION_STEP_MS)

    def _simulate_step(self, dt, keys):
        self.time_ms += dt
        self.audio.update(dt)
        self.background.update(dt / 1000.0)
        if self._heavy_landing_imminent(keys):
            self.player.heavy_landing_sound_played = True
            self.audio.play("ground_impact", channel_key="movement")
        if self.player.update(dt, keys):
            self.audio.play("jump", channel_key="movement")
        # This is a one-step physics event, emitted on the qualifying landing
        # tick alongside the recovery animation and impact effects. Play it
        # before hazard damage can cancel recovery or reset the player.
        if (self.player.heavy_landing_started and
                not self.player.heavy_landing_sound_played):
            self.player.heavy_landing_sound_played = True
            self.audio.play("ground_impact", channel_key="movement")
        if self.player.dash_started_event is not None:
            x, y, direction = self.player.dash_started_event
            self.effects.emit_dash((x + PLAYER_W / 2 - direction * PLAYER_W * .6,
                                    y + PLAYER_H * .55), direction)
            self.audio.play("dash", channel_key="movement", cooldown_ms=100)

        self._apply_lava_damage(dt)

        # The player reports a one-step landing event after the shared swept
        # collision solver confirms contact with a solid surface.
        fall_distance = self.player.landing_fall_distance
        if fall_distance >= BlockEffects.LANDING_DUST_THRESHOLD_TILES * TILE:
            surface_y = self.player.y + PLAYER_H
            surface_row = math.floor((surface_y + 1e-5) / TILE)
            first_col = math.floor(self.player.x / TILE)
            last_col = math.floor((self.player.x + PLAYER_W - 1e-5) / TILE)
            support_tiles = [
                (col, self.world.get(col, surface_row))
                for col in range(first_col, last_col + 1)
                if self.world.is_solid(col, surface_row)
            ]
            if support_tiles:
                # Pick the support tile nearest the feet center when the player
                # straddles a seam, keeping the dust palette tied to the landing.
                _, tile_type = min(
                    support_tiles,
                    key=lambda item: abs((item[0] + 0.5) * TILE -
                                         (self.player.x + PLAYER_W / 2)))
                material = {
                    DIRT: "dirt", GRASS: "grass", STONE: "stone",
                    BEDROCK: "bedrock",
                }.get(tile_type, "dirt")
                if self.player.heavy_landing_started:
                    self.effects.emit_heavy_landing(
                        (self.player.x + PLAYER_W / 2, surface_y), material,
                        fall_distance / TILE)
                    self._cancel_held_action()
                    self._pending_jump = False
                    self.punch.active = False
                else:
                    self.effects.emit_landing(
                        (self.player.x + PLAYER_W / 2, surface_y), material,
                        fall_distance / TILE)

        view_left  = self.cam_x
        view_right = self.cam_x + WIDTH
        self.player.x = max(view_left, min(view_right - PLAYER_W, self.player.x))

        target_x = self.player.x + PLAYER_W / 2 - WIDTH / 2
        target_y = self.player.y + PLAYER_H / 2 - HEIGHT / 2
        # Preserve the original follow curve at a fixed simulation rate.
        self.cam_x += (target_x - self.cam_x) * 0.15
        self.cam_y += (target_y - self.cam_y) * 0.15
        self._clamp_camera()

        view_left  = self.cam_x
        view_right = self.cam_x + WIDTH
        self.player.x = max(view_left, min(view_right - PLAYER_W, self.player.x))

        self.falling_camera.update(
            dt, fall_distance=self.player.fall_distance,
            descending=not self.player.on_ground and self.player.vy > 0 and not self.player.dashing,
            impact=self.player.heavy_landing_started, recovering=self.player.recovering,
            alive=self.player.hp > 0)

        # Bound synchronous A* work if several zombies request routes together.
        self.world.navigation_budget_remaining = 1
        approach_offsets = (0, -20, 20, -24, 24, -12, 12, 8)
        for index, zombie in enumerate(self.zombies):
            # The small bounded entity list stays physical even offscreen;
            # suspending an airborne enemy would visibly freeze it at the edge.
            zombie.update(dt, self.player, self._receive_enemy_attack,
                          approach_offsets[index % len(approach_offsets)],
                          nearby_zombies=self.zombies)
            if zombie.state == ZombieState.DEAD and not zombie.death_emitted:
                self.effects.emit(zombie.center, (130, 150, 90), "break")
                zombie.death_emitted = True
        self.zombies = [z for z in self.zombies if not z.removed]
        self._separate_actors_softly()

        self.punch.update(dt)
        self.effects.update(dt)
        self.place_cooldown = max(0.0, self.place_cooldown - dt)

        if self._held_buttons:
            if self._held_signature != self._selection_signature():
                self._cancel_held_action()
            else:
                self._repeat_remaining -= dt
                if self._repeat_remaining <= 1e-8:
                    if not self._action_over_ui(self.pointer_pos):
                        self._act_at_pointer()
                    self._repeat_remaining += (PLACE_COOLDOWN if self.hotbar.is_placement_mode()
                                               else ACTION_REPEAT_MS)
                    if self._held_signature != self._selection_signature():
                        self._cancel_held_action()

        expired = []
        for key, entry in self.damage.items():
            entry["timer"] -= dt
            if entry["timer"] <= 1e-8:
                expired.append(key)
        for key in expired:
            del self.damage[key]

        remaining = []
        for drop in self.drops:
            drop.update(dt, self.player)
            if drop.collected:
                # Keep the jump/fall soundscape clear; pickup feedback is
                # audible when collected on the ground, but not mid-air.
                if self.player.on_ground:
                    self.audio.play("item_drop", channel_key="movement", pitch="high")
                self.hotbar.add_item(drop.tile_type)
                self.game.save_accounts()
            else:
                remaining.append(drop)
        self.drops = remaining

        self.player_animation.update(dt, grounded=self.player.on_ground,
                                     vx=self.player.vx, vy=self.player.vy,
                                     sprinting=self.player.sprinting,
                                     dashing=self.player.dashing,
                                     heavy_landing=self.player.recovering,
                                     recovery_elapsed_ms=HEAVY_LANDING_RECOVERY_MS - self.player.landing_recovery_ms)

    def _separate_actors_softly(self):
        """Gently resolve horizontal overlap without bypassing tile collision."""
        actors = [self.player] + [z for z in self.zombies
                                  if z.state != ZombieState.DEAD and not z.removed]
        actors.sort(key=lambda actor: actor.x+CHARACTER_PHYSICS.width/2)
        moved = {id(actor): 0.0 for actor in actors}
        max_shift = 3.0

        def can_shift(actor, amount):
            new_x = actor.x+amount
            return (0 <= new_x <= WORLD_W-CHARACTER_PHYSICS.width and
                    not overlaps_solid(self.world, new_x, actor.y,
                        CHARACTER_PHYSICS.width, CHARACTER_PHYSICS.height, TILE))

        for index, left in enumerate(actors):
            left_center = left.x+CHARACTER_PHYSICS.width/2
            for right in actors[index+1:]:
                right_center = right.x+CHARACTER_PHYSICS.width/2
                dx = right_center-left_center
                if dx >= CHARACTER_PHYSICS.width:
                    break
                if (left.y >= right.y+CHARACTER_PHYSICS.height or
                        right.y >= left.y+CHARACTER_PHYSICS.height):
                    continue
                overlap = CHARACTER_PHYSICS.width-dx
                correction = min(2.0, overlap*.25)
                left_room = max(0.0, max_shift-abs(moved[id(left)]))
                right_room = max(0.0, max_shift-abs(moved[id(right)]))
                left_shift = min(correction, left_room)
                right_shift = min(correction, right_room)
                if left_shift and not can_shift(left, -left_shift):
                    left_shift = 0.0
                if right_shift and not can_shift(right, right_shift):
                    right_shift = 0.0
                # If a wall pins one actor, let the free actor absorb the
                # remaining gentle correction, bounded to three pixels/step.
                if not left_shift and right_shift:
                    extra = min(overlap-right_shift, right_room-right_shift)
                    if extra and can_shift(right, right_shift+extra):
                        right_shift += extra
                elif not right_shift and left_shift:
                    extra = min(overlap-left_shift, left_room-left_shift)
                    if extra and can_shift(left, -(left_shift+extra)):
                        left_shift += extra
                left.x -= left_shift
                right.x += right_shift
                moved[id(left)] += left_shift
                moved[id(right)] += right_shift
                left_center -= left_shift
                right_center += right_shift

    # --- drawing ---
    def _draw_cracks(self, surface, c, r, cam_x_i, cam_y_i):
        entry = self.damage.get((c, r))
        if not entry:
            return
        tile = self.world.tiles[r][c]
        needed = BREAK_HITS.get(tile, 2)
        ratio = min(1.0, entry["hits"] / needed)
        if ratio <= 0:
            return

        sx = c * TILE - cam_x_i
        sy = r * TILE - cam_y_i

        if entry.get("crack_surface_hits") != entry["hits"]:
            overlay = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, int(90 * ratio)))
            rng = random.Random((c * 73856093) ^ (r * 19349663))
            num_cracks = int(1 + ratio * 3)
            for _ in range(num_cracks):
                start = (rng.randint(4, TILE - 4), rng.randint(4, TILE - 4))
                end = (rng.randint(4, TILE - 4), rng.randint(4, TILE - 4))
                pygame.draw.line(overlay, (20, 20, 20), start, end, 2)
            if ratio >= 0.99:
                pygame.draw.rect(overlay, (255, 240, 120),
                                 pygame.Rect(0, 0, TILE, TILE), width=2)
            entry["crack_surface"] = overlay
            entry["crack_surface_hits"] = entry["hits"]

        surface.blit(entry["crack_surface"], (sx, sy))

    def _draw_fist(self, surface):
        if not self.punch.active:
            return
        origin = (self.player.x + PLAYER_W / 2,
                  self.player.y + PLAYER_H / 2)
        fx, fy = self.punch.current_pos(origin)
        ox, oy = origin[0] - self.cam_x, origin[1] - self.cam_y
        fx, fy = fx - self.cam_x, fy - self.cam_y
        if self.punch_effect is not None:
            self.punch_effect.draw(surface, (ox, oy), (fx, fy), self.punch.progress())
        else:
            draw_fist_icon(surface, (fx, fy), 18, HEAD_COLOR)

    def _terrain_texture_for(self, c, r, tile):
        """Return a cached variant with baked edges hidden beside other tiles."""
        texture = self.block_textures.get(tile)
        if texture is None:
            return None
        # Bits: left, right, top, bottom. Keep the source outline only on
        # exposed edges that border air.
        neighbors = (self.world.get(c - 1, r), self.world.get(c + 1, r),
                     self.world.get(c, r - 1), self.world.get(c, r + 1))
        mask = sum(bit for bit, neighbor in zip((1, 2, 4, 8), neighbors)
                   if neighbor != AIR)
        if not mask:
            return texture
        key = tile, mask
        cached = self._terrain_variant_cache.get(key)
        if cached is not None:
            return cached

        variant = texture.copy()
        size = texture.get_width()
        last = size - 1
        if mask & 1:
            variant.blit(texture, (0, 0), (1, 0, 1, size))
        if mask & 2:
            variant.blit(texture, (last, 0), (last - 1, 0, 1, size))
        if mask & 4:
            variant.blit(texture, (0, 0), (0, 1, size, 1))
        if mask & 8:
            variant.blit(texture, (0, last), (0, last - 1, size, 1))

        # Restore corners from the interior when both adjoining sides are shared.
        for x_bit, y_bit, dest, source in (
                (1, 4, (0, 0), (1, 1)), (2, 4, (last, 0), (last - 1, 1)),
                (1, 8, (0, last), (1, last - 1)),
                (2, 8, (last, last), (last - 1, last - 1))):
            if mask & x_bit and mask & y_bit:
                variant.blit(texture, dest, (*source, 1, 1))
        self._terrain_variant_cache[key] = variant
        return variant

    def _draw_placement_preview(self, surface):
        if self.player.recovering:
            return
        if not self.hotbar.is_placement_mode():
            return
        item = self.hotbar.selected_item()
        if item["tile"] is None or item["count"] <= 0:
            return
        mx, my = self.pointer_pos
        if self._action_over_ui((mx, my)):
            return
        c, r = self._screen_to_tile(mx, my)
        if not (0 <= c < GRID_W and 0 <= r < GRID_H):
            return
        if self.world.tiles[r][c] != AIR:
            return

        in_range = self._tile_center_distance(c, r) <= PLACE_RANGE
        blocked = self._would_overlap_player(c, r)
        ok = in_range and not blocked

        sx = c * TILE - int(self.cam_x)
        sy = r * TILE - int(self.cam_y)

        texture = self.block_textures.get(item["tile"])
        if texture is not None:
            surface.blit(texture, (sx, sy))
        ghost = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        color = TILE_COLORS[item["tile"]]
        alpha = 140 if ok else 70
        ghost.fill((*color, alpha))
        surface.blit(ghost, (sx, sy))
        border = (255, 255, 255) if ok else (220, 60, 60)
        pygame.draw.rect(surface, border, pygame.Rect(sx, sy, TILE, TILE), width=2)

    def draw(self, surface):
        self.background.draw(surface, self.cam_x, self.cam_y)

        cam_x_i = int(self.cam_x)
        cam_y_i = int(self.cam_y)

        start_c = max(0, cam_x_i // TILE)
        end_c   = min(GRID_W, (cam_x_i + WIDTH) // TILE + 2)
        start_r = max(0, cam_y_i // TILE)
        end_r   = min(GRID_H, (cam_y_i + HEIGHT) // TILE + 2)

        shimmer = 0.5 + 0.5 * math.sin(self.time_ms * 0.004)

        for r in range(start_r, end_r):
            row = self.world.tiles[r]
            for c in range(start_c, end_c):
                tile = row[c]
                if tile == AIR:
                    continue
                sx = c * TILE - cam_x_i
                sy = r * TILE - cam_y_i
                rect = pygame.Rect(sx, sy, TILE, TILE)

                texture = self._terrain_texture_for(c, r, tile)
                if texture is not None:
                    surface.blit(texture, (sx, sy))
                elif tile == LAVA:
                    base = TILE_COLORS[LAVA]
                    r0 = int(base[0] * (0.85 + 0.15 * shimmer))
                    g0 = int(base[1] * (0.75 + 0.25 * shimmer))
                    b0 = int(base[2] * (0.85 + 0.15 * shimmer))
                    pygame.draw.rect(surface, (r0, g0, b0), rect)
                else:
                    color = TILE_COLORS[tile]
                    pygame.draw.rect(surface, color, rect)
                    darker = (max(0, color[0] - 40),
                              max(0, color[1] - 40),
                              max(0, color[2] - 40))
                    pygame.draw.rect(surface, darker, rect, width=1)

                if tile == LAVA:
                    glow = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
                    glow.fill((255, 200, 80, int(60 + 80 * shimmer)))
                    surface.blit(glow, (sx, sy))
                    if texture is None:
                        pygame.draw.rect(surface, (120, 40, 10), rect, width=1)

        grid_bottom_screen = GRID_H * TILE - cam_y_i
        if grid_bottom_screen < HEIGHT:
            pygame.draw.rect(surface, TILE_COLORS[BEDROCK],
                             pygame.Rect(0, grid_bottom_screen, WIDTH,
                                         HEIGHT - grid_bottom_screen))

        for drop in self.drops:
            drop.draw(surface, cam_x_i, cam_y_i, self.block_drop_textures)

        for zombie in self.zombies:
            if zombie.rect().colliderect(pygame.FRect(cam_x_i-64, cam_y_i-80, WIDTH+128, HEIGHT+160)):
                zombie.draw(surface, cam_x_i, cam_y_i)
        if self.navigation_debug_visible:
            for zombie in self.zombies:
                zombie.draw_navigation_debug(surface, cam_x_i, cam_y_i,
                                             self.game.small_font)

        for (dc, dr) in list(self.damage.keys()):
            if start_c - 1 <= dc <= end_c + 1 and start_r - 1 <= dr <= end_r + 1:
                self._draw_cracks(surface, dc, dr, cam_x_i, cam_y_i)

        self.player.draw(surface, cam_x_i, cam_y_i, self.player_animation,
                         self.punch.progress() if self.punch.active else None)
        self._draw_fist(surface)
        self.effects.draw(surface, cam_x_i, cam_y_i)
        self._draw_placement_preview(surface)

        if self.falling_camera.zoom > 1.0001:
            if self._zoom_layer is None or self._zoom_layer.get_size() != surface.get_size():
                self._zoom_layer = pygame.Surface(surface.get_size())
            view = self._zoom_view_rect(surface.get_size())
            pygame.transform.scale(surface.subsurface(view), surface.get_size(), self._zoom_layer)
            surface.blit(self._zoom_layer, (0, 0))

        self.hud.resize(surface.get_size())
        self.hotbar.set_layout(self.hud.layout.hotbar_slots)
        self.hud.draw_top(surface, self.game.current_username, self.world.name,
                          self.player.hp, self.player.max_hp,
                          self.game.small_font, self.game.small_font)
        self.hotbar.draw(surface, self.block_icons)
        self.hud.draw_context(surface, self.hotbar.current_label(), self.game.small_font)
        if self.debug_visible:
            feet_row = int((self.player.y + PLAYER_H) // TILE)
            debug_lines = (f"X: {self.player.x / TILE:.1f} tiles",
                           f"Y: {self.world.row_to_y(feet_row)}",
                           f"VX: {self.player.vx:.2f}  VY: {self.player.vy:.2f}")
            self.hud.draw_debug(surface, debug_lines, self.game.small_font)
        if self.paused:
            self.hud.draw_pause(surface, self.pause_page, self.game.small_font,
                                self.game.label_font, self.game.small_font, self.hud.scale)

# ---------------------------------------------------------------
# Root
# ---------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        self.audio = AudioManager(os.path.join(os.path.dirname(__file__),
                                               "assets", "sounds"))
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.title_font    = pygame.font.SysFont("arialrounded", 120, bold=True)
        self.subtitle_font = pygame.font.SysFont("arialrounded", 64, bold=True)
        self.btn_font      = pygame.font.SysFont("arialrounded", 44, bold=True)
        self.input_font    = pygame.font.SysFont("arialrounded", 40)
        self.list_font     = pygame.font.SysFont("arialrounded", 32)
        self.label_font    = pygame.font.SysFont("arialrounded", 32)
        self.small_font    = pygame.font.SysFont("arialrounded", 24)
        self.hotbar_count_font = pygame.font.SysFont("arialrounded", 20, bold=True)

        self.bg = self._make_gradient(BG_TOP, BG_BOTTOM)

        self.worlds = [World.from_any(e) for e in load_worlds()]
        self.accounts = load_accounts()

        self.current_username = ""
        self.current_account = None

        self.scene = MenuScene(self)

    def _make_gradient(self, top, bottom):
        surf = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            t = y / HEIGHT
            r = int(top[0] * (1 - t) + bottom[0] * t)
            g = int(top[1] * (1 - t) + bottom[1] * t)
            b = int(top[2] * (1 - t) + bottom[2] * t)
            pygame.draw.line(surf, (r, g, b), (0, y), (WIDTH, y))
        return surf

    def set_username(self, name):
        self.current_username = name
        acc = self.accounts.get(name)
        if acc is None:
            acc = Account({"username": name})
            self.accounts[name] = acc
        self.current_account = acc
        self.save_accounts()

    def save_worlds(self):
        save_worlds([w.to_dict() for w in self.worlds])

    def save_accounts(self):
        if self.accounts:
            save_accounts(self.accounts)

    def change_scene(self, new_scene):
        old_scene = self.scene
        if isinstance(new_scene, GameScene):
            if not isinstance(old_scene, GameScene) or old_scene.world is not new_scene.world:
                self.audio.play("enter_world")
        elif isinstance(old_scene, GameScene) and isinstance(new_scene, MenuScene):
            self.audio.play("leave_world")
        self.scene = new_scene

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.save_accounts()
                    self.running = False
                self.scene.handle_event(event)

            self.scene.update(dt)
            self.scene.draw(self.screen)
            pygame.display.flip()

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    Game().run()
