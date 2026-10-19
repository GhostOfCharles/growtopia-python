"""Heavy impact, recovery controls, cinematic camera and asset regressions."""

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
from src.camera import FallingCamera
from src.effects import BlockEffects


def keys(*pressed):
    return defaultdict(bool, {key: True for key in pressed})


class HeavyLandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        font = pygame.font.Font(None, 24)
        self.app = SimpleNamespace(current_account=game.Account(), small_font=font,
            hotbar_count_font=font, btn_font=font, label_font=font,
            screen=pygame.Surface((game.WIDTH, game.HEIGHT)), current_username="Landing",
            save_worlds=Mock(), save_accounts=Mock())
        tiles = [[game.AIR] * game.GRID_W for _ in range(game.GRID_H)]
        tiles[40] = [game.DIRT] * game.GRID_W
        self.scene = game.GameScene(self.app, game.World("Landing", tiles, [50, 40]))
        self.player = self.scene.player

    def step(self, *pressed):
        self.scene._simulate_step(game.SIMULATION_STEP_MS, keys(*pressed))

    def fall(self, tiles, vy=0):
        self.player.y -= tiles * game.TILE
        self.player.vy = vy
        self.player.on_ground = False
        apex = self.player.y
        for _ in range(200):
            self.step()
            apex = min(apex, self.player.y)
            if self.player.on_ground:
                return 40 * game.TILE - game.PLAYER_H - apex
        self.fail("Player did not land")

    def test_threshold_is_strict_and_shorter_landings_keep_ordinary_dust(self):
        for tiles in (4, 5, 10, 12, 12.01, 13):
            with self.subTest(tiles=tiles):
                self.setUp()
                with patch.object(self.scene.effects, "emit_heavy_landing",
                                  wraps=self.scene.effects.emit_heavy_landing) as heavy:
                    self.fall(tiles)
                    self.assertEqual(self.player.recovering, tiles > 12)
                    self.assertEqual(heavy.call_count, int(tiles > 12))
                    if tiles >= 5:
                        self.assertTrue(self.scene.effects.particles)

    def test_distance_is_from_apex_and_impact_origin_is_surface_once(self):
        with patch.object(self.scene.effects, "emit_heavy_landing",
                          wraps=self.scene.effects.emit_heavy_landing) as heavy:
            measured = self.fall(9, game.JUMP_VELOCITY)
            self.assertGreater(measured, 12 * game.TILE)
            self.assertAlmostEqual(self.player.landing_fall_distance, measured)
            self.assertEqual(heavy.call_count, 1)
            self.assertEqual(heavy.call_args.args[0],
                             (self.player.x + game.PLAYER_W / 2, 40 * game.TILE))
            for _ in range(65):
                self.step()
            self.assertEqual(heavy.call_count, 1)

    def test_impact_sound_plays_once_only_for_heavy_landing(self):
        self.scene.audio = Mock()
        self.fall(12)
        self.assertFalse(self.scene.audio.play.called)
        self.fall(13)
        self.assertEqual(self.scene.audio.play.call_count, 1)
        self.scene.audio.play.assert_called_once_with(
            "ground_impact", channel_key="movement")
        for _ in range(65):
            self.step()
        self.assertEqual(self.scene.audio.play.call_count, 1)

    def test_impact_sound_survives_damage_on_the_landing_tick(self):
        self.scene.audio = Mock()
        self.player.hp = 1

        def damage_immediately_after_physics(_dt):
            if self.player.heavy_landing_started:
                self.player.apply_damage(1)
                self.scene._check_player_death()

        self.scene._apply_lava_damage = damage_immediately_after_physics
        self.fall(13)
        impact_calls = [call for call in self.scene.audio.play.call_args_list
                        if call.args and call.args[0] == "ground_impact"]
        self.assertEqual(impact_calls, [
            unittest.mock.call("ground_impact", channel_key="movement")])

    def test_impact_sound_is_advanced_by_about_130_ms(self):
        self.scene.audio = Mock()
        self.player.y -= 16 * game.TILE
        self.player.vy = 0
        self.player.on_ground = False
        sound_time = landing_time = None
        for _ in range(200):
            self.step()
            if sound_time is None and self.scene.audio.play.called:
                sound_time = self.scene.time_ms
            if self.player.on_ground:
                landing_time = self.scene.time_ms
                break
        self.assertIsNotNone(sound_time)
        self.assertIsNotNone(landing_time)
        lead = landing_time - sound_time
        self.assertGreaterEqual(lead, game.HEAVY_LANDING_SOUND_LEAD_MS -
                                2 * game.SIMULATION_STEP_MS)
        self.assertLessEqual(lead, game.HEAVY_LANDING_SOUND_LEAD_MS +
                             2 * game.SIMULATION_STEP_MS)
        self.assertEqual(self.scene.audio.play.call_count, 1)

    def test_exact_second_locks_controls_and_requires_fresh_press(self):
        self.fall(13)
        origin = self.player.x, self.player.y
        for _ in range(59):
            self.step(pygame.K_d, pygame.K_SPACE, pygame.K_q, pygame.K_LSHIFT)
            self.assertTrue(self.player.recovering)
            self.assertEqual((self.player.x, self.player.y), origin)
            self.assertFalse(self.player.sprinting or self.player.dashing)
            self.assertFalse(self.player.request_dash(keys()))
            self.assertFalse(self.scene._try_break(51, 40))
            self.assertFalse(self.scene._try_place(51, 39))
            self.assertFalse(self.scene._act_at_pointer())
        self.step(pygame.K_d, pygame.K_SPACE, pygame.K_q)
        self.assertFalse(self.player.recovering)
        self.step(pygame.K_d, pygame.K_SPACE, pygame.K_q)
        self.assertEqual((self.player.x, self.player.y), origin)
        self.assertEqual(self.scene.player_animation.state, "idle")
        self.step()
        self.step(pygame.K_d, pygame.K_SPACE)
        self.assertGreater(self.player.x, origin[0])
        self.assertLess(self.player.y, origin[1])

    def test_support_removal_and_external_knockback_interrupt_recovery(self):
        self.fall(13)
        self.scene.world.tiles[40][50] = game.AIR
        self.step()
        self.assertFalse(self.player.recovering)
        self.assertFalse(self.player.on_ground)
        self.assertGreater(self.player.vy, 0)
        self.setUp()
        self.fall(13)
        self.player.apply_knockback((49, 40))
        self.assertFalse(self.player.recovering)
        self.step()
        self.assertLess(self.player.vy, 0)

    def test_lava_overlap_and_death_do_not_start_recovery(self):
        self.scene.world.tiles[39][50] = game.LAVA
        self.fall(13)
        self.assertFalse(self.player.recovering)
        self.setUp()
        self.player.hp = 0
        self.player.y -= 13 * game.TILE
        self.player.vy = game.MAX_FALL
        for _ in range(40):
            self.player.update(game.SIMULATION_STEP_MS, keys())
        self.assertFalse(self.player.recovering)

    def test_six_frames_play_once_over_recovery_and_render_complete_feet(self):
        self.fall(13)
        animation = self.scene.player_animation
        self.assertEqual(len(animation.sprite_clips["heavy_landing"]), 6)
        self.assertEqual(animation.state, "heavy_landing")
        self.assertEqual(animation.frame, 0)
        for index in range(6):
            animation.update(0, grounded=True, vx=9, vy=-13, dashing=True,
                             heavy_landing=True, recovery_elapsed_ms=index * 1000 / 6 + 1)
            self.assertEqual(animation.frame, index)
            for facing in (-1, 1):
                surface = pygame.Surface((160, 140), pygame.SRCALPHA)
                animation.draw(surface, 66, 30, 28, 56, facing,
                               game.HEAD_COLOR, game.BODY_COLOR, game.OUTLINE, .5)
                bounds = surface.get_bounding_rect()
                self.assertEqual(bounds.bottom, 86)
                self.assertGreater(bounds.top, 0)
                self.assertGreater(bounds.left, 0)
                self.assertLess(bounds.right, 160)
        animation.elapsed_ms = 1200
        self.assertEqual(animation.frame, 5)
        for _ in range(60):
            self.step()
        self.assertEqual(animation.state, "idle")

    def test_camera_zoom_restores_during_recovery_and_mouse_transform_matches(self):
        self.fall(14)
        self.assertGreater(self.scene.falling_camera.zoom, 1)
        prior = self.scene.falling_camera.zoom
        for _ in range(60):
            self.step()
            self.assertLessEqual(self.scene.falling_camera.zoom, prior + 1e-9)
            prior = self.scene.falling_camera.zoom
        self.assertEqual(self.scene.falling_camera.zoom, 1)
        self.scene.falling_camera.zoom = 1.1
        view = self.scene._zoom_view_rect()
        self.assertEqual(self.scene._screen_to_world(0, 0),
                         (self.scene.cam_x + view.x, self.scene.cam_y + view.y))
        before = self.player.x, self.player.y
        self.scene.draw(self.app.screen)
        self.assertEqual((self.player.x, self.player.y), before)

    def test_camera_short_falls_interruptions_and_death(self):
        camera = FallingCamera()
        camera.update(100, fall_distance=100, descending=True)
        self.assertEqual(camera.zoom, 1)
        camera.update(200, fall_distance=300, descending=True)
        self.assertGreater(camera.zoom, 1)
        prior = camera.zoom
        camera.update(100, fall_distance=0, descending=False)
        self.assertTrue(1 < camera.zoom < prior)
        camera.update(16, fall_distance=300, descending=True, alive=False)
        self.assertEqual(camera.zoom, 1)

    def test_dust_is_larger_ground_hugging_bounded_and_expires(self):
        effects = BlockEffects()
        effects.emit_heavy_landing((100, 300), "stone", 40)
        self.assertLessEqual(len(effects.particles), effects.HEAVY_DUST_MAX_COUNT)
        self.assertGreater(len(effects.particles), effects.LANDING_DUST_MAX_COUNT)
        self.assertTrue(all(p.y + p.size / 2 <= 300 for p in effects.particles))
        effects.update(300)
        self.assertLess(min(p.x for p in effects.particles), 100 - 2 * game.TILE)
        self.assertGreater(max(p.x for p in effects.particles), 100 + 2 * game.TILE)
        self.assertTrue(all(p.y + p.size / 2 <= 300 for p in effects.particles))
        effects.update(500)
        self.assertEqual(effects.particles, [])

    def test_camera_easing_is_frame_rate_independent(self):
        values = []
        for hz in (30, 60, 120, 144):
            camera = FallingCamera()
            remaining = 400.0
            while remaining > 1e-8:
                dt = min(1000 / hz, remaining)
                camera.update(dt, fall_distance=400, descending=True)
                remaining -= dt
            values.append(camera.zoom)
            camera.update(0, fall_distance=0, descending=False, impact=True, recovering=True)
            remaining = 1000.0
            while remaining > 1e-8:
                dt = min(1000 / hz, remaining)
                camera.update(dt, fall_distance=0, descending=False, recovering=True)
                remaining -= dt
            self.assertAlmostEqual(camera.zoom, 1)
        for value in values:
            self.assertAlmostEqual(value, values[0])

    def test_item_pickups_and_mouse_actions_are_blocked_during_recovery(self):
        self.fall(13)
        drop = game.DroppedItem(self.scene.world, game.DIRT, 50, 39)
        drop.x = self.player.x + (game.PLAYER_W - game.DROP_SIZE) / 2
        drop.y = self.player.y + (game.PLAYER_H - game.DROP_SIZE) / 2
        self.scene.drops.append(drop)
        self.scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                  button=1, pos=(1000, 500)))
        self.assertEqual(self.scene._held_buttons, set())
        self.assertFalse(self.scene.punch.active)
        self.step()
        self.assertFalse(drop.collected)
        self.assertIn(drop, self.scene.drops)


if __name__ == "__main__":
    unittest.main()
