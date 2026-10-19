"""Headless enemy animation, local navigation and melee regressions."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import math
import unittest
from dataclasses import replace
from unittest.mock import Mock
from unittest.mock import patch
from types import SimpleNamespace
from collections import defaultdict
import pygame
import main as game
from src.animation import PLAYER_ART_HEIGHT
from src.assets import AssetManager
from src.zombie import (Zombie, ZombieState, ZombieSettings, NavigationMode,
                        ZOMBIE_ART_SCALE, find_zombie_spawn)
from src.navigation import PlatformNavigator, NavigationSettings, PathStatus


class ZombieTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.assets = AssetManager(Path(__file__).resolve().parents[1]/"assets")
        cls.clips, cls.durations = cls.assets.load_animation_config("characters/zombie/animation.json")

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        tiles = [[game.AIR]*game.GRID_W for _ in range(game.GRID_H)]
        tiles[40] = [game.DIRT]*game.GRID_W
        self.world = game.World("Enemy test", tiles, [50, 40])
        self.player = game.Player(self.world, [50, 40])
        self.player.on_ground = True
        self.zombie = self.make_zombie()

    def make_zombie(self, col=54, **settings):
        zombie = Zombie(self.world, col*32+2, 40*32-56, game.CHARACTER_PHYSICS,
            self.clips, self.durations, replace(ZombieSettings(), **settings))
        zombie.on_ground = True
        return zombie

    def advance(self, zombie, milliseconds, callback=None):
        for _ in range(round(milliseconds/game.SIMULATION_STEP_MS)):
            zombie.update(game.SIMULATION_STEP_MS, self.player, callback)

    def test_runtime_sheets_have_expected_counts_alpha_and_canvas(self):
        for state, count in {"idle":1,"walking":4,"jumping":1,"falling":1,"attack":6}.items():
            frames = self.clips[state]["frames"]
            self.assertEqual(len(frames), count)
            for frame in frames:
                self.assertEqual(frame.get_size(), (28,56))
                self.assertTrue(frame.get_flags() & pygame.SRCALPHA)
                self.assertEqual(frame.get_at((0,0)).a, 0)
                self.assertEqual(frame.get_bounding_rect().bottom, 56)

    def test_zombie_art_matches_player_height_and_bottom_anchor(self):
        z = self.zombie
        self.assertEqual(z.animation.sprite_height, PLAYER_ART_HEIGHT * ZOMBIE_ART_SCALE)
        surface = pygame.Surface((100, 120), pygame.SRCALPHA)
        z.animation.draw(surface, 36, 20, 28, 56, 1, (145, 165, 95),
                         (90, 65, 90), (20, 20, 30))
        bounds = surface.get_bounding_rect()
        self.assertLessEqual(bounds.height, PLAYER_ART_HEIGHT)
        self.assertGreater(bounds.height, 56)
        self.assertEqual(bounds.bottom, 76)

    def test_exact_ten_punches_kill_and_death_cleans_up_once(self):
        z = self.zombie
        for index in range(10):
            self.assertTrue(z.take_damage(z.settings.punch_damage, z.x-50))
            self.assertEqual(z.hp, 100-10*(index+1))
            if index < 9:
                self.assertFalse(z.take_damage(10, z.x-50))
                self.advance(z, 200)
        self.assertEqual(z.state, ZombieState.DEAD)
        self.assertFalse(z.take_damage(10, z.x-50))
        before = (z.x,z.y)
        self.advance(z, 300)
        self.assertTrue(z.removed)
        self.assertEqual((z.x,z.y), before)

    def test_hurt_flash_knockback_and_airborne_animation(self):
        z=self.zombie
        self.assertTrue(z.take_damage(10,z.x-50))
        self.assertEqual(z.state,ZombieState.HURT)
        self.assertGreater(z.flash_ms,0)
        self.assertGreater(z.vx,0)
        self.assertLess(z.vy,0)
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertEqual(z.animation.state,"jumping")
        self.assertGreater(z.vx,0)  # AI cannot overwrite the push during stun
        self.advance(z,180)
        self.assertNotEqual(z.state,ZombieState.HURT)

    def test_detection_hysteresis_and_disengagement(self):
        z=self.zombie
        self.advance(z,650)
        self.assertEqual(z.state,ZombieState.CHASE)
        self.player.x=z.x+9*32
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertEqual(z.state,ZombieState.CHASE)
        self.player.x=z.x+14*32
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertEqual(z.state,ZombieState.WANDER)
        self.assertEqual(z.ignore_player_ms,0)
        self.assertGreater(z.vx,0)
        # Sight re-entry immediately restores pursuit without another idle.
        self.player.x=z.x+5*32
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertEqual(z.state,ZombieState.CHASE)

    def test_scratch_applies_once_on_fourth_frame_and_respects_cooldown(self):
        z=self.make_zombie(51,spawn_idle_ms=0)
        self.player.x=z.x-35
        callback=Mock(return_value=True)
        z.update(game.SIMULATION_STEP_MS,self.player,callback)
        self.assertEqual(z.state,ZombieState.ATTACK)
        self.advance(z,250,callback)
        callback.assert_not_called()
        self.advance(z,100,callback)
        callback.assert_called_once_with(z,z.settings.attack_damage)
        self.advance(z,400,callback)
        self.assertEqual(callback.call_count,1)
        self.advance(z,900,callback)
        self.assertEqual(callback.call_count,2)

    def test_zombie_melee_hitbox_grows_15_percent_and_still_checks_line_of_sight(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        z.facing=1
        self.player.y=z.y
        self.player.x=z.center[0]+48-game.PLAYER_W/2
        self.assertTrue(z._melee_connects(self.player))
        self.player.x=z.center[0]+49-game.PLAYER_W/2
        self.assertFalse(z._melee_connects(self.player))
        wall_col=math.floor((z.center[0]+24)/game.TILE)
        self.world.tiles[39][wall_col]=game.STONE
        self.player.x=z.center[0]+40-game.PLAYER_W/2
        self.assertFalse(z._melee_connects(self.player))

    def test_zombie_behind_ally_can_join_melee_swarm(self):
        rear=self.make_zombie(54,spawn_idle_ms=0)
        front=self.make_zombie(55,spawn_idle_ms=0)
        rear.x=1700
        front.x=1730
        rear.y=front.y=self.player.y
        self.player.x=rear.center[0]+70-game.PLAYER_W/2
        rear.facing=front.facing=1
        self.assertFalse(rear._melee_connects(self.player))
        self.assertTrue(rear._melee_connects(self.player,[front]))
        rear.state=ZombieState.CHASE
        callback=Mock(return_value=True)
        rear.update(game.SIMULATION_STEP_MS,self.player,callback,
                    nearby_zombies=[rear,front])
        self.assertEqual(rear.state,ZombieState.ATTACK)
        for _ in range(24):
            rear.update(game.SIMULATION_STEP_MS,self.player,callback,
                        nearby_zombies=[rear,front])
        callback.assert_called_once_with(rear,rear.settings.attack_damage)

    def test_moving_out_of_range_or_hurt_interrupts_attack(self):
        z=self.make_zombie(51,spawn_idle_ms=0)
        self.player.x=z.x-35
        callback=Mock()
        z.update(game.SIMULATION_STEP_MS,self.player,callback)
        z.take_damage(10,self.player.x)
        self.advance(z,150,callback)
        callback.assert_not_called()
        other=self.make_zombie(51,spawn_idle_ms=0)
        other.update(game.SIMULATION_STEP_MS,self.player,callback)
        self.player.x-=200
        self.advance(other,400,callback)
        callback.assert_not_called()

    def test_punch_knockback_is_reduced_and_interrupts_scratch(self):
        z=self.make_zombie(51,spawn_idle_ms=0)
        self.player.x=z.x-35
        callback=Mock()
        z.update(game.SIMULATION_STEP_MS,self.player,callback)
        self.assertEqual(z.state,ZombieState.ATTACK)
        self.assertTrue(z.take_damage(10,self.player.x))
        self.assertEqual(z.state,ZombieState.HURT)
        self.assertEqual(z.vx,3.0)
        self.assertEqual(z.vy,-3.5)
        self.advance(z,400,callback)
        callback.assert_not_called()

    def test_local_jump_predicts_obstacle_and_rejects_tall_wall_lava_and_pit(self):
        z=self.zombie
        c=int((z.x+28)/32)+1
        self.world.tiles[39][c]=game.STONE
        self.assertTrue(z._can_jump(1,z.settings.chase_speed))
        for row in range(34,40): self.world.tiles[row][c]=game.STONE
        self.assertFalse(z._can_jump(1,z.settings.chase_speed))
        for row in range(34,40): self.world.tiles[row][c]=game.AIR
        for col in range(c,c+6):
            self.world.tiles[40][col]=game.LAVA
        self.assertFalse(z._can_jump(1,z.settings.chase_speed))

    def test_shared_collision_prevents_knockback_tunneling(self):
        z=self.zombie
        wall=int((z.x+28)/32)+1
        for row in range(32,40): self.world.tiles[row][wall]=game.STONE
        z.take_damage(10,z.x-20)
        self.advance(z,200)
        self.assertLessEqual(z.x+28,wall*32)

    def test_chase_physically_jumps_to_reachable_platform(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        for c in range(55,58): self.world.tiles[38][c]=game.STONE
        self.player.x=56*32+2
        self.player.y=38*32-56
        seen_jump=False
        for _ in range(45):
            z.update(game.SIMULATION_STEP_MS,self.player)
            seen_jump |= z.vy < 0
        self.assertTrue(seen_jump)
        self.assertLessEqual(z.y,38*32-56+.01)
        self.assertGreaterEqual(z.x+28,55*32)

    def test_impossible_wall_disengages_without_endless_jumps(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        self.player.x=57*32
        for row in range(30,40): self.world.tiles[row][55]=game.STONE
        self.advance(z,3000)
        self.assertEqual(z.ignore_player_ms,0)
        self.assertIn(z.state,(ZombieState.CHASE,ZombieState.WANDER))
        self.assertLessEqual(z.x+28,55*32)

    def test_chase_crosses_small_gap_without_falling_into_pit(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        self.world.tiles[40][55]=game.AIR
        self.player.x=58*32+2
        start_y=z.y
        for _ in range(50):
            z.update(game.SIMULATION_STEP_MS,self.player)
            self.assertLessEqual(z.y,start_y+32)
        self.assertGreater(z.x,56*32)

    def test_chase_follows_player_off_ledge_to_safe_lower_route(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        # Upper ledge ends several tiles before a safe lower floor, like the
        # split platforms in the gameplay view. A direct horizontal route is
        # impossible, but a physically simulated drop is safe and reachable.
        for c in range(50,59): self.world.tiles[35][c]=game.STONE
        for c in range(50,60): self.world.tiles[40][c]=game.AIR
        for c in range(60,70): self.world.tiles[40][c]=game.STONE
        z.x=54*32+2; z.y=35*32-56; z.home_x=z.x; z.home_y=z.y
        z.on_ground=True
        self.player.x=61*32+2; self.player.y=40*32-56
        self.assertTrue(z._can_jump(1,z.settings.chase_speed))
        for _ in range(240):
            z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertIn(z.state,(ZombieState.CHASE,ZombieState.ATTACK))
        self.assertGreater(z.x,59*32)
        self.assertFalse(any(game.overlaps_solid(self.world,z.x,z.y,28,56,32)
                             for _ in (0,)))

    def test_chase_routes_away_then_jumps_around_overhang(self):
        z=self.make_zombie(50,spawn_idle_ms=0)
        for row in range(34,40):
            for col in range(48,62): self.world.tiles[row][col]=game.AIR
        for col in range(51,58): self.world.tiles[37][col]=game.STONE
        z.x=50*32+2; z.y=40*32-56; z.home_x=z.x; z.on_ground=True
        self.player.x=54*32+2; self.player.y=37*32-56
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertTrue(z._nav_path)
        self.assertLess(z._nav_path[0].x,z.x)  # path first goes away from player
        self.assertIn("jump",[step.action for step in z._nav_path])
        for _ in range(130): z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertIn(z.state,(ZombieState.CHASE,ZombieState.ATTACK))
        self.assertLess(z.y,40*32-56)
        self.assertFalse(game.overlaps_solid(self.world,z.x,z.y,28,56,32))

    def test_chase_follows_a_route_with_multiple_platform_jumps(self):
        z=self.make_zombie(50,spawn_idle_ms=0)
        for row in range(32,40):
            for col in range(48,64): self.world.tiles[row][col]=game.AIR
        for col in range(53,56): self.world.tiles[38][col]=game.STONE
        for col in range(56,60): self.world.tiles[36][col]=game.STONE
        z.x=50*32+2; z.y=40*32-56; z.home_x=z.x; z.on_ground=True
        self.player.x=57*32+2; self.player.y=36*32-56
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertTrue(z._nav_path)
        self.assertGreaterEqual(sum(step.action == "jump" for step in z._nav_path),2)
        for _ in range(240): z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertIn(z.state,(ZombieState.CHASE,ZombieState.ATTACK))
        self.assertLess(z.y,40*32-56)

    def test_navigator_distinguishes_complete_partial_and_unreachable(self):
        z=self.zombie
        nav=PlatformNavigator(game.CHARACTER_PHYSICS,z.settings.chase_speed)
        complete=nav.find_path(self.world,(z.x,z.y),(58*32+16,40*32-28))
        self.assertEqual(complete.status,PathStatus.COMPLETE)
        self.assertTrue(complete.steps)
        for c in range(58,61): self.world.tiles[38][c]=game.STONE
        limited=PlatformNavigator(game.CHARACTER_PHYSICS,z.settings.chase_speed,
            NavigationSettings(max_expansions=1)).find_path(
                self.world,(z.x,z.y),(59*32+16,38*32-28))
        self.assertEqual(limited.status,PathStatus.PARTIAL)
        missing=nav.find_path(self.world,(z.x,z.y-80),(58*32+16,40*32-28))
        self.assertEqual(missing.status,PathStatus.UNREACHABLE)

    def test_navigation_graph_groups_platforms_and_caches_by_affected_region(self):
        z=self.zombie
        nav=PlatformNavigator(game.CHARACTER_PHYSICS,z.settings.chase_speed)
        nav.find_path(self.world,(z.x,z.y),(58*32+16,40*32-28))
        first=nav.graph_for_debug()[1]
        self.assertTrue(any(len(platform)>4 for platform in first.platforms))
        nav.find_path(self.world,(z.x,z.y),(58*32+16,40*32-28))
        self.assertIs(nav.graph_for_debug()[1],first)
        peer=PlatformNavigator(game.CHARACTER_PHYSICS,z.settings.chase_speed)
        peer.find_path(self.world,(z.x,z.y),(58*32+16,40*32-28))
        self.assertIs(peer.graph_for_debug()[1],first)
        # Edits are recorded by cell; changing this graph region rebuilds it.
        self.world.tiles[39][55]=game.STONE
        self.world.navigation_changed(55,39)
        nav.find_path(self.world,(z.x,z.y),(58*32+16,40*32-28))
        self.assertIsNot(nav.graph_for_debug()[1],first)

    def test_failed_jump_is_temporarily_removed_from_route_search(self):
        z=self.zombie
        for c in range(55,59): self.world.tiles[38][c]=game.STONE
        nav=PlatformNavigator(game.CHARACTER_PHYSICS,z.settings.chase_speed)
        first=nav.find_path(self.world,(z.x,z.y),(57*32+16,38*32-28))
        jump=next(step for step in first.steps if step.action=="jump")
        nav.fail_transition(jump.edge_id)
        retry=nav.find_path(self.world,(z.x,z.y),(57*32+16,38*32-28))
        self.assertTrue(all(step.edge_id != jump.edge_id for step in retry.steps))
        nav.update(nav.settings.jump_failure_cooldown_ms+1)
        restored=nav.find_path(self.world,(z.x,z.y),(57*32+16,38*32-28))
        self.assertEqual(restored.status,PathStatus.COMPLETE)

    def test_jump_controller_commits_through_landing(self):
        z=self.make_zombie(54,spawn_idle_ms=0,melee_pixels=0)
        for c in range(55,63): self.world.tiles[38][c]=game.STONE
        self.player.x=56*32+2
        self.player.y=38*32-56
        advanced=False
        for _ in range(70):
            z.update(game.SIMULATION_STEP_MS,self.player,approach_offset=96)
            advanced |= z._nav_path_index >= 1
        self.assertTrue(advanced)
        self.assertIn(z._nav_mode,(NavigationMode.CONTINUE,NavigationMode.LAND,
                                   NavigationMode.APPROACH,NavigationMode.PREPARE_JUMP))
        self.assertFalse(game.overlaps_solid(self.world,z.x,z.y,28,56,32))

    def test_zombie_drops_from_single_tile_perch_to_ground_route(self):
        z=self.make_zombie(57,spawn_idle_ms=0)
        self.world.tiles[38][57]=game.DIRT
        z.y=38*32-56
        z.home_y=z.y
        z.on_ground=True
        self.player.x=50*32+2
        self.player.y=40*32-56
        for _ in range(45): z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertGreater(z.x+28,50*32)
        self.assertEqual(z._nav_status,PathStatus.COMPLETE)
        self.assertFalse(game.overlaps_solid(self.world,z.x,z.y,28,56,32))

    def test_bounded_search_fallback_chooses_safe_drop_from_perch(self):
        z=self.zombie
        self.world.tiles[38][57]=game.DIRT
        nav=PlatformNavigator(game.CHARACTER_PHYSICS,z.settings.chase_speed,
                               NavigationSettings(max_expansions=1))
        result=nav.find_path(self.world,(57*32+2,38*32-56),(50*32+16,40*32-28))
        self.assertEqual(result.status,PathStatus.PARTIAL)
        self.assertTrue(result.steps)
        self.assertEqual(result.steps[-1].action,"drop")
        self.assertGreater(result.steps[-1].y,38*32-56)

    def test_unreachable_zombie_follows_player_trail_via_safe_drop(self):
        z=self.make_zombie(57,spawn_idle_ms=0)
        self.world.tiles[38][57]=game.DIRT
        z.y=38*32-56
        z.on_ground=True
        destination=(50*32,40*32-28)
        movement=z._safe_drop_toward(destination)
        self.assertLess(movement,0)
        self.assertEqual(z._fallback_drop_dir,-1)
        # A committed drop continues through ordinary physics while airborne.
        z.on_ground=False
        self.assertEqual(z._safe_drop_toward(destination),-z.settings.chase_speed)

    def test_partial_staging_position_allows_a_fresh_search(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        target=(self.player.x+14,self.player.y+28)
        z._nav_status=PathStatus.PARTIAL
        z._nav_target=target
        z._nav_revision=self.world.navigation_revision
        z._nav_failed_key=((math.floor(target[0]/32),math.floor(target[1]/32)),
                           self.world.navigation_revision,
                           round(z.x/32),round(z.y/32))
        z._nav_failure_wait_ms=0
        original=z.navigator.find_path
        z.navigator.find_path=Mock(wraps=original)
        z._follow_player_path(target,game.SIMULATION_STEP_MS)
        z.navigator.find_path.assert_called_once()

    def test_chase_speed_and_airborne_landing_prediction(self):
        z=self.zombie
        self.assertEqual(z.settings.chase_speed,3.0)
        self.player.x=55*32
        self.player.y=40*32-100
        self.player.vx=2.0
        self.player.vy=4.0
        self.player.on_ground=False
        landing=z._predict_landing(self.player)
        self.assertIsNotNone(landing)
        self.assertGreater(landing[0],self.player.x+14)
        self.assertGreater(landing[1],self.player.y)

    def test_brief_loss_of_detection_uses_last_seen_position(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertEqual(z.state,ZombieState.CHASE)
        z._nav_path=[SimpleNamespace(x=z.x+64,y=z.y,action="walk")]
        z._nav_path_index=0
        self.player.x=z.x+11*32
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertEqual(z.state,ZombieState.CHASE)
        self.assertGreater(z._pursuit_memory_ms,0)

    def test_zombies_choose_distinct_approach_positions(self):
        left=self.make_zombie(54,spawn_idle_ms=0)
        right=self.make_zombie(54,spawn_idle_ms=0)
        left.update(game.SIMULATION_STEP_MS,self.player,approach_offset=-28)
        right.update(game.SIMULATION_STEP_MS,self.player,approach_offset=28)
        self.assertIsNotNone(left._nav_target)
        self.assertIsNotNone(right._nav_target)
        self.assertEqual(abs(left._nav_target[0]-right._nav_target[0]),56)

    def test_close_chase_fades_approach_offset(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        self.player.x=z.x+70
        z._nav_status=PathStatus.COMPLETE
        z._follow_player_path=Mock(return_value=(z.settings.chase_speed,False))
        z.update(game.SIMULATION_STEP_MS,self.player,approach_offset=24)
        self.assertEqual(z._follow_player_path.call_args.args[2],0.0)

    def test_complete_route_keeps_closing_until_melee_range(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        self.player.x=z.x+65
        z.state=ZombieState.CHASE
        z._nav_status=PathStatus.COMPLETE
        z._nav_path=[]
        z._nav_path_index=0
        z._nav_repath_ms=500
        self.world.navigation_budget_enabled=True
        self.world.navigation_budget_remaining=0
        z.update(game.SIMULATION_STEP_MS,self.player,approach_offset=0)
        self.assertGreater(z.vx,0)
        self.assertEqual(z.state,ZombieState.CHASE)

    def test_navigation_replans_immediately_after_terrain_revision(self):
        z=self.make_zombie(54,spawn_idle_ms=0)
        self.player.x=z.x-90
        z.jump_cooldown_ms=10000
        z.update(game.SIMULATION_STEP_MS,self.player)
        old_revision=z._nav_revision
        self.world.tiles[39][52]=game.STONE
        self.world.navigation_revision+=1
        z.update(game.SIMULATION_STEP_MS,self.player)
        self.assertGreater(z._nav_revision,old_revision)
        self.assertEqual(z._nav_repath_ms,z.settings.navigation_repath_ms)

    def test_wander_stays_near_home_without_target(self):
        z=self.zombie
        self.player.x=80*32
        for _ in range(600):
            z.update(game.SIMULATION_STEP_MS,self.player)
            self.assertLessEqual(abs(z.x-z.home_x),z.settings.home_tiles*32+2)
        self.assertNotEqual(z.state,ZombieState.CHASE)

    def test_spawn_is_safe_and_multiple_instances_are_independent(self):
        entities=[]
        for _ in range(3):
            position=find_zombie_spawn(self.world,self.player,entities,game.CHARACTER_PHYSICS)
            self.assertIsNotNone(position)
            z=Zombie(self.world,*position,game.CHARACTER_PHYSICS,self.clips,self.durations)
            self.assertFalse(z.rect().colliderect(self.player.rect()))
            self.assertTrue(all(not z.rect().colliderect(other.rect()) for other in entities))
            entities.append(z)
        entities[0].take_damage(10,self.player.x)
        self.assertEqual([z.hp for z in entities],[90,100,100])


class ZombieSceneTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        font=pygame.font.Font(None,24)
        self.app=SimpleNamespace(current_account=game.Account(),small_font=font,
            hotbar_count_font=font,label_font=font,btn_font=font,current_username="Test",
            save_worlds=Mock(),save_accounts=Mock(),audio=Mock(),
            screen=pygame.Surface((game.WIDTH,game.HEIGHT)))
        tiles=[[game.AIR]*game.GRID_W for _ in range(game.GRID_H)]
        tiles[40]=[game.DIRT]*game.GRID_W
        self.scene=game.GameScene(self.app,game.World("NPC test",tiles,[50,40]))
        self.scene.player.on_ground=True

    def add_zombie(self,col=52):
        scene=self.scene
        z=Zombie(scene.world,col*32+2,40*32-56,game.CHARACTER_PHYSICS,
                 scene.zombie_clips,scene.zombie_durations)
        z.on_ground=True
        scene.zombies.append(z)
        return z

    def test_soft_collisions_separate_player_and_zombies_gently(self):
        scene=self.scene
        left=self.add_zombie(50)
        right=self.add_zombie(50)
        scene.player.x=left.x
        scene.player.y=left.y
        start=[scene.player.x,left.x,right.x]
        scene._separate_actors_softly()
        self.assertGreater(max(scene.player.x,left.x,right.x)-
                           min(scene.player.x,left.x,right.x),0)
        for actor, before in zip((scene.player,left,right),start):
            self.assertLessEqual(abs(actor.x-before),3.0)
            self.assertFalse(game.overlaps_solid(scene.world,actor.x,actor.y,
                game.PLAYER_W,game.PLAYER_H,game.TILE))

    def test_punch_prioritizes_hurtbox_and_shares_cooldown_with_blocks(self):
        scene=self.scene
        z=self.add_zombie()
        scene.world.tiles[39][54]=game.STONE
        scene.pointer_pos=(54*32+16-scene.cam_x,z.center[1]-scene.cam_y)
        self.assertTrue(scene._act_at_pointer())
        self.assertEqual(z.hp,90)
        self.assertEqual(scene.player.facing,1)
        self.assertFalse(scene._act_at_pointer())
        self.assertEqual(z.hp,90)
        self.assertEqual(scene.world.tiles[39][54],game.STONE)
        self.assertEqual(scene.damage,{})
        self.assertFalse(scene._try_break(52,40))

    def test_entity_punch_is_blocked_by_solid_wall(self):
        scene=self.scene
        z=self.add_zombie(53)
        for row in (38,39): scene.world.tiles[row][51]=game.STONE
        scene.pointer_pos=(z.center[0]-scene.cam_x,z.center[1]-scene.cam_y)
        self.assertFalse(scene._act_at_pointer())
        self.assertEqual(z.hp,100)
        self.assertEqual(scene.damage,{})

    def test_placement_cannot_embed_enemy_and_fifty_zombies_update(self):
        scene=self.scene
        self.add_zombie()
        scene.hotbar.add_item(game.DIRT,2)
        scene.hotbar.select(1)
        self.assertFalse(scene._try_place(52,39))
        self.assertEqual(scene.hotbar.selected_item()["count"],2)
        for _ in range(game.MAX_ZOMBIES+5): scene.spawn_zombie()
        self.assertEqual(len(scene.zombies),game.MAX_ZOMBIES)
        self.assertIsNone(scene.spawn_zombie())
        for _ in range(5):
            scene._simulate_step(game.SIMULATION_STEP_MS,defaultdict(bool))
        self.assertEqual(len(scene.zombies),game.MAX_ZOMBIES)

    def test_scratch_uses_player_flash_invulnerability_knockback_and_death(self):
        scene=self.scene
        z=self.add_zombie()
        self.assertTrue(scene._receive_enemy_attack(z,12))
        self.assertEqual(scene.player.hp,88)
        self.assertGreater(scene.player.flash_ms,0)
        self.assertLess(scene.player.vx,0)
        self.assertLess(scene.player.vy,0)
        self.assertFalse(scene._receive_enemy_attack(z,12))
        scene.player.hp=1
        scene.player.invuln_ms=0
        self.assertTrue(scene._receive_enemy_attack(z,12))
        self.assertEqual(scene.player.hp,100)
        self.assertGreater(z.ignore_player_ms,0)  # explicit respawn grace, not a juke
        self.assertEqual([c.args[0] for c in self.app.audio.play.call_args_list].count("death"),1)

    def test_f6_spawns_safely_pause_blocks_spawn_and_dead_cleanup_emits_once(self):
        scene=self.scene
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F6))
        self.assertEqual(len(scene.zombies),1)
        scene.paused=True
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F6))
        self.assertEqual(len(scene.zombies),1)
        scene.paused=False
        z=scene.zombies[0]
        z.take_damage(100,scene.player.x)
        scene.effects.emit=Mock()
        for _ in range(20): scene._simulate_step(game.SIMULATION_STEP_MS,defaultdict(bool))
        self.assertEqual(scene.zombies,[])
        scene.effects.emit.assert_called_once()
        self.app.save_worlds.assert_not_called()

    def test_f4_toggles_navigation_overlay_without_pausing(self):
        self.assertFalse(self.scene.navigation_debug_visible)
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F4))
        self.assertTrue(self.scene.navigation_debug_visible)
        self.assertFalse(self.scene.paused)
        zombie=self.add_zombie()
        zombie.update(game.SIMULATION_STEP_MS,self.scene.player)
        zombie.draw_navigation_debug(self.app.screen,0,0,self.app.small_font)

    def test_enemy_timing_matches_across_render_rates(self):
        results=[]
        for hz in (30,60,120,144):
            self.setUp()
            self.add_zombie(54)
            remaining=2000
            with patch.object(pygame.key,"get_pressed",return_value=defaultdict(bool)):
                while remaining>1e-7:
                    dt=min(1000/hz,remaining)
                    self.scene.update(dt)
                    remaining-=dt
            z=self.scene.zombies[0]
            results.append((z.x,z.y,z.hp,z.state,self.scene.player.hp))
        for result in results[1:]: self.assertEqual(result,results[0])


if __name__ == "__main__": unittest.main()
