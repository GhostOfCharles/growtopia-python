"""Focused tests for the procedural sky renderer."""

import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from src.background import BackgroundConfig, BackgroundRenderer


class BackgroundRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_gradient_is_vertical_and_cloud_layout_is_seeded(self):
        config = BackgroundConfig(seed=7, cloud_count=5)
        first = BackgroundRenderer((320, 180), config)
        second = BackgroundRenderer((320, 180), config)
        surface = pygame.Surface((320, 180))
        first.draw(surface)
        self.assertEqual(surface.get_at((0, 0))[:3], config.top_color)
        self.assertEqual(surface.get_at((0, 179))[:3], config.bottom_color)
        self.assertEqual(first.cloud_layout(), second.cloud_layout())

    def test_drift_is_time_based_and_camera_offset_is_parallax_scaled(self):
        config = BackgroundConfig(seed=3, cloud_count=1, min_cloud_speed=6,
                                  max_cloud_speed=6, min_parallax=.1,
                                  max_parallax=.1)
        at_30 = BackgroundRenderer((320, 180), config)
        at_120 = BackgroundRenderer((320, 180), config)
        for _ in range(30):
            at_30.update(1 / 30)
        for _ in range(120):
            at_120.update(1 / 120)
        self.assertAlmostEqual(at_30.cloud_layout()[0][0],
                               at_120.cloud_layout()[0][0], places=8)
        before = at_30.cloud_layout(camera_x=0)[0][0]
        after = at_30.cloud_layout(camera_x=100)[0][0]
        self.assertAlmostEqual(after - before, -10)

    def test_cloud_wraps_across_offscreen_buffer(self):
        renderer = BackgroundRenderer((320, 180), BackgroundConfig(
            seed=1, cloud_count=1, min_cloud_speed=10, max_cloud_speed=10))
        cloud = renderer.clouds[0]
        width = cloud["image"].get_width()
        cloud["x"] = 320 + width - 1
        renderer.update(.2)
        self.assertGreaterEqual(cloud["x"], -width)
        self.assertLess(cloud["x"], -width + 2)


if __name__ == "__main__":
    unittest.main()
