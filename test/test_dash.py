"""Horizontal dash timing, input edges, swept collisions and presentation."""

from collections import defaultdict
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame
import main as game
from src.animation import PlayerAnimation
from src.assets import AssetManager


def keys(*pressed):
    return defaultdict(bool, {key: True for key in pressed})


class DashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        tiles = [[game.AIR] * game.GRID_W for _ in range(game.GRID_H)]
        tiles[80] = [game.DIRT] * game.GRID_W
        self.world = game.World("Dash tests", tiles, [50, 80])
        self.player = game.Player(self.world, [50, 80])
        self.player.on_ground = True

    def step(self, *pressed, dt=game.SIMULATION_STEP_MS):
        return self.player.update(dt, keys(*pressed))

    def scene(self):
        font = pygame.font.Font(None, 24)
        app = SimpleNamespace(current_account=game.Account(), small_font=font,
                              screen=pygame.Surface((game.WIDTH, game.HEIGHT)),
                              hotbar_count_font=font, btn_font=font, label_font=font,
                              current_username="Dash", save_worlds=Mock(),
                              save_accounts=Mock())
        scene = game.GameScene(app, self.world)
        scene.player.on_ground = True
        return scene

    def test_direction_is_selected_on_press_and_locked(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                self.setUp()
                self.player.facing = direction
                initial_x = self.player.x
                self.step(pygame.K_q)
                self.assertEqual(self.player.dash_direction, direction)
                self.assertAlmostEqual(self.player.x - initial_x, direction * game.DASH_SPEED)
                self.step(pygame.K_q, pygame.K_a if direction == 1 else pygame.K_d)
                self.assertEqual(self.player.vx, direction * game.DASH_SPEED)
                self.assertEqual(self.player.facing, direction)

    def test_ground_dash_covers_four_tiles_at_original_fast_speed(self):
        for direction in (-1, 1):
            self.setUp()
            self.player.facing = direction
            start_x, start_y = self.player.x, self.player.y
            elapsed = 0.0
            self.step(pygame.K_q)
            self.assertAlmostEqual(self.player.x - start_x, direction * game.DASH_SPEED)
            elapsed += game.SIMULATION_STEP_MS
            while self.player.dashing:
                self.step(pygame.K_q)
                elapsed += game.SIMULATION_STEP_MS
            self.assertAlmostEqual(self.player.x - start_x, direction * 128)
            self.assertEqual(self.player.y, start_y)
            self.assertEqual(game.DASH_SPEED, 3 * game.MOVE_SPEED)
            self.assertLess(elapsed, 250.1)
            self.assertGreaterEqual(elapsed, game.DASH_DURATION_MS)
            self.assertLess(elapsed - game.DASH_DURATION_MS, game.SIMULATION_STEP_MS)
            self.step(pygame.K_q)
            self.assertAlmostEqual(self.player.x - start_x, direction * 128)

    def test_movement_input_overrides_facing_then_locks_until_completion(self):
        for direction, key in ((-1, pygame.K_a), (1, pygame.K_d)):
            self.setUp()
            self.player.facing = -direction
            self.step(pygame.K_q, key)
            self.assertEqual(self.player.dash_direction, direction)
            self.assertEqual(self.player.facing, direction)
            opposite = pygame.K_d if direction == -1 else pygame.K_a
            self.step(opposite)
            self.assertEqual(self.player.dash_direction, direction)
            self.assertEqual(self.player.facing, direction)

    def test_held_key_cannot_repeat_and_cooldown_rejects_new_press(self):
        self.step(pygame.K_q)
        while self.player.dashing:
            self.step(pygame.K_q)
        self.step()
        self.step(pygame.K_q)  # Fresh press during cooldown is rejected.
        self.assertFalse(self.player.dashing)
        for _ in range(65):
            self.step(pygame.K_q)
        self.assertFalse(self.player.dashing)
        self.assertEqual(self.player.dash_cooldown_ms, 0)
        self.step()
        self.step(pygame.K_q)
        self.assertTrue(self.player.dashing)

    def test_air_dash_suspends_vertical_motion_and_restores_previous_velocity(self):
        for vy in (-7.0, 5.0, game.MAX_FALL):
            self.setUp()
            self.player.y = 600.0
            self.player.on_ground = False
            self.player.vy = vy
            start_x = self.player.x
            self.step(pygame.K_q)
            self.assertEqual(self.player.y, 600.0)
            self.assertEqual(self.player.vy, 0.0)
            while self.player.dashing:
                dt = min(game.SIMULATION_STEP_MS, self.player.dash_remaining_ms)
                self.step(pygame.K_q, dt=dt)
                self.assertEqual(self.player.y, 600.0)
            self.assertAlmostEqual(self.player.x - start_x, 128.0)
            self.assertEqual(self.player.vy, max(0.0, vy))
            self.step()
            self.assertAlmostEqual(self.player.vy, min(game.MAX_FALL, max(0.0, vy) + game.GRAVITY))
            self.assertNotEqual(self.player.y, 600.0)

    def test_jump_held_during_dash_requires_release_before_jumping(self):
        self.assertFalse(self.step(pygame.K_q, pygame.K_SPACE))
        self.assertTrue(self.player.dashing)
        self.assertEqual(self.player.vy, 0)
        while self.player.dashing:
            self.step(pygame.K_SPACE, dt=min(game.SIMULATION_STEP_MS, self.player.dash_remaining_ms))
        self.assertEqual(self.player.vy, 0.0)
        old_y = self.player.y
        self.assertFalse(self.step(pygame.K_SPACE))
        self.assertEqual(self.player.y, old_y)
        self.step()
        self.assertTrue(self.step(pygame.K_SPACE))
        self.assertLess(self.player.y, old_y)

    def test_wall_and_world_boundary_interrupt_without_penetration(self):
        wall_col = 51
        for row in (78, 79):
            self.world.tiles[row][wall_col] = game.STONE
        self.player.x = wall_col * game.TILE - game.PLAYER_W - 2
        self.step(pygame.K_q)
        self.assertFalse(self.player.dashing)
        self.assertEqual(self.player.x + game.PLAYER_W, wall_col * game.TILE)
        self.assertFalse(self.player._collides(self.player.x, self.player.y))
        self.setUp()
        self.player.x = 1.0
        self.player.facing = -1
        self.step(pygame.K_q)
        self.assertFalse(self.player.dashing)
        self.assertEqual(self.player.x, 0.0)

    def test_damage_interrupts_and_normal_sprinting_returns(self):
        self.step(pygame.K_q)
        self.player.apply_damage(10)
        self.assertFalse(self.player.dashing)
        self.assertEqual(self.player.hp, game.MAX_HP - 10)
        self.step(pygame.K_a, pygame.K_LSHIFT)
        self.assertEqual(self.player.vx, -game.MOVE_SPEED * game.SPRINT_SPEED_MULTIPLIER)

    def test_dash_clip_loops_and_ends_without_lingering_or_punch_override(self):
        clips, durations = AssetManager().load_animation_config("characters/player/animation.json")
        animation = PlayerAnimation(durations, clips)
        self.assertEqual(len(clips["dashing"]["frames"]), 4)
        self.assertTrue(all(frame.get_size() == (28, 56)
                            for frame in clips["dashing"]["frames"]))
        animation.update(81, grounded=False, vx=3, vy=-22, dashing=True)
        self.assertEqual(animation.state, "dashing")
        self.assertEqual(animation.frame, 1)
        animation.update(320, grounded=False, vx=3, vy=-22, dashing=True)
        self.assertEqual(animation.frame, 1)
        for facing in (-1, 1):
            rendered = []
            for punch in (None, 0.5):
                surface = pygame.Surface((160, 140), pygame.SRCALPHA)
                animation.draw(surface, 66, 30, 28, 56, facing, game.HEAD_COLOR,
                               game.BODY_COLOR, game.OUTLINE, punch)
                bounds = surface.get_bounding_rect(min_alpha=16)
                self.assertTrue(60 <= bounds.height <= 65, bounds)
                self.assertEqual(bounds.bottom, 86)
                rendered.append(pygame.image.tobytes(surface, "RGBA"))
            self.assertEqual(*rendered)
        for grounded, vx, vy, sprinting, expected in (
                (False, 0, 0, False, "falling"),
                (True, 0, 0, False, "idle"),
                (True, 3, 0, False, "walking"),
                (True, 4.5, 0, True, "sprinting")):
            animation.update(0, grounded=grounded, vx=vx, vy=vy,
                             sprinting=sprinting, dashing=False)
            self.assertEqual(animation.state, expected)

    def test_short_q_tap_is_retained_but_paused_input_is_discarded(self):
        scene = self.scene()
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q))
        scene.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_q))
        scene._simulate_step(game.SIMULATION_STEP_MS, keys())
        self.assertTrue(scene.player.dashing)
        self.assertEqual(scene.player_animation.state, "dashing")
        while scene.player.dashing:
            scene._simulate_step(game.SIMULATION_STEP_MS, keys())
        self.assertFalse(scene.player.dashing)
        self.assertEqual(scene.player_animation.state, "idle")
        scene.player.respawn()
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q))
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        scene._simulate_step(game.SIMULATION_STEP_MS, keys())
        self.assertFalse(scene.player.dashing)

    def test_scene_distance_and_air_animation_are_consistent_across_render_rates(self):
        for hz in (30, 60, 120, 144):
            for airborne in (False, True):
                with self.subTest(hz=hz, airborne=airborne):
                    scene = self.scene()
                    if airborne:
                        scene.player.y -= 10 * game.TILE
                        scene.player.on_ground = False
                        scene.player.vy = -7.0
                    start_x, start_y = scene.player.x, scene.player.y
                    scene.player.request_dash(keys())
                    with patch.object(pygame.key, "get_pressed", return_value=keys()):
                        remaining = game.DASH_DURATION_MS + 50.0
                        while remaining > 1e-8:
                            dt = min(1000 / hz, remaining)
                            scene.update(dt)
                            if scene.player.dashing:
                                self.assertEqual(scene.player_animation.state, "dashing")
                                self.assertEqual(scene.player.y, start_y)
                            remaining -= dt
                    self.assertFalse(scene.player.dashing)
                    self.assertAlmostEqual(scene.player.x - start_x, 128.0)
                    self.assertEqual(scene.player_animation.state,
                                     "falling" if airborne else "idle")

    def test_shockwave_and_sound_share_one_successful_activation_event(self):
        for direction in (-1, 1):
            for airborne in (False, True):
                with self.subTest(direction=direction, airborne=airborne):
                    scene = self.scene()
                    scene.audio = Mock()
                    scene.player.facing = direction
                    if airborne:
                        scene.player.y -= 200
                        scene.player.on_ground = False
                        scene.player.vy = 5
                    x, y = scene.player.x, scene.player.y
                    self.assertTrue(scene.player.request_dash(keys()))
                    scene._simulate_step(game.SIMULATION_STEP_MS, keys(pygame.K_q))
                    self.assertEqual(len(scene.effects.shockwaves), 1)
                    wave = scene.effects.shockwaves[0]
                    self.assertAlmostEqual(wave.x, x + game.PLAYER_W / 2 -
                                           direction * game.PLAYER_W * .6)
                    self.assertAlmostEqual(wave.y, y + game.PLAYER_H * .55)
                    self.assertEqual(wave.direction, direction)
                    self.assertAlmostEqual(scene.player.x - x, direction * game.DASH_SPEED)
                    for _ in range(20):
                        scene._simulate_step(game.SIMULATION_STEP_MS, keys(pygame.K_q))
                    self.assertFalse(scene.player.request_dash(keys()))
                    scene._simulate_step(game.SIMULATION_STEP_MS, keys())
                    calls = [call for call in scene.audio.play.call_args_list
                             if call.args[0] == "dash"]
                    self.assertEqual(len(calls), 1)
                    self.assertEqual((wave.x, wave.y),
                                     (x + game.PLAYER_W / 2 - direction * game.PLAYER_W * .6,
                                      y + game.PLAYER_H * .55))


if __name__ == "__main__":
    unittest.main()
