"""Focused tests for the animated punch stretch sprite."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame
from src.assets import AssetManager
from src.effects import BlockEffects, PunchStretchEffect


class PunchStretchEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_project_sheet_has_four_transparent_frames(self):
        root = Path(__file__).resolve().parents[1] / "assets"
        manager = AssetManager(root)
        effect = PunchStretchEffect(manager)
        self.assertEqual(len(effect.frames), 4)
        self.assertTrue(all(frame.get_width() > frame.get_height() for frame in effect.frames))
        self.assertTrue(all(frame.get_flags() & pygame.SRCALPHA for frame in effect.frames))

    def test_frame_progress_and_horizontal_mirroring_keep_wrist_at_origin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sheet = pygame.Surface((32, 8), pygame.SRCALPHA)
            sheet.fill((0, 0, 0, 0))
            colors = ((255, 0, 0, 255), (0, 255, 0, 255),
                      (0, 0, 255, 255), (255, 255, 0, 255))
            for index, color in enumerate(colors):
                pygame.draw.rect(sheet, color, (index * 8 + 1, 3, 6, 2))
            sheet_path = Path(temp_dir) / "effect.png"
            pygame.image.save(sheet, str(sheet_path))
            effect = PunchStretchEffect(AssetManager(temp_dir), "effect.png",
                                        frame_size=(8, 8), frame_count=4, height=4)
            for index, (progress, color) in enumerate(zip((0.1, 0.3, 0.6, 0.9), colors)):
                right_surface = pygame.Surface((100, 50), pygame.SRCALPHA)
                right_rect = effect.draw(right_surface, (20, 20), (50, 20), progress)
                self.assertEqual(right_rect.left, 20)
                self.assertEqual(right_surface.get_at((35, 19)), color)

            left_surface = pygame.Surface((100, 50), pygame.SRCALPHA)
            left_rect = effect.draw(left_surface, (60, 20), (30, 20), 0.1)
            self.assertEqual(left_rect.right, 60)
            self.assertEqual(left_surface.get_at((45, 19)), colors[0])


class LandingDustTests(unittest.TestCase):
    def test_threshold_palette_burst_and_lifetime(self):
        effects = BlockEffects()
        self.assertFalse(effects.emit_landing((100, 200), "stone", 4.99))
        self.assertEqual(effects.particles, [])

        self.assertTrue(effects.emit_landing((100, 200), "stone", 5.0))
        self.assertEqual(len(effects.particles), effects.LANDING_DUST_BASE_COUNT)
        self.assertTrue(any(p.vx < 0 for p in effects.particles))
        self.assertTrue(any(p.vx > 0 for p in effects.particles))
        self.assertTrue(all(230.0 <= p.lifetime_ms <= 360.0
                            for p in effects.particles))
        self.assertTrue(all(p.color in effects.LANDING_DUST_PALETTES["stone"]
                            for p in effects.particles))

    def test_landing_effect_threshold_is_configurable(self):
        effects = BlockEffects(landing_threshold_tiles=3.0)
        self.assertFalse(effects.emit_landing((0, 0), "dirt", 2.99))
        self.assertTrue(effects.emit_landing((0, 0), "dirt", 3.0))


class DashShockwaveTests(unittest.TestCase):
    def test_expansion_fade_mirroring_and_cached_frames(self):
        effects = BlockEffects()
        effects.emit_dash((100, 100), 1)
        frames = effects._dash_frames
        first, middle, last = frames[1][0], frames[1][8], frames[1][-1]
        self.assertGreater(middle.get_bounding_rect().height, first.get_bounding_rect().height)
        self.assertEqual(last.get_bounding_rect().size, (0, 0))
        self.assertLess(pygame.surfarray.array_alpha(middle).max(),
                        pygame.surfarray.array_alpha(first).max())
        for right, left in zip(frames[1], frames[-1]):
            self.assertEqual(pygame.image.tobytes(pygame.transform.flip(right, True, False), "RGBA"),
                             pygame.image.tobytes(left, "RGBA"))
        effects.emit_dash((120, 100), -1)
        self.assertIs(effects._dash_frames, frames)

    def test_world_anchor_camera_movement_and_cleanup(self):
        effects = BlockEffects()
        effects.emit_dash((100, 100), 1)
        effects.update(100)
        wave = effects.shockwaves[0]
        self.assertEqual((wave.x, wave.y), (100, 100))
        first = pygame.Surface((200, 200), pygame.SRCALPHA)
        second = pygame.Surface((200, 200), pygame.SRCALPHA)
        effects.draw(first, 0, 0)
        effects.draw(second, 20, 10)
        self.assertEqual(first.get_bounding_rect().move(-20, -10), second.get_bounding_rect())
        effects.update(effects.DASH_WAVE_LIFETIME_MS - 100)
        self.assertEqual(effects.shockwaves, [])


if __name__ == "__main__":
    unittest.main()
