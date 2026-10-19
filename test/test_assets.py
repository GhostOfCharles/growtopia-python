"""Focused checks for cached sprite loading and animation integration."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame
from src.animation import PlayerAnimation
from src.assets import AssetManager
from tools.validate_assets import validate


class AssetPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = AssetManager(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, name, surface):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(surface, str(path))
        return path

    def test_png_cache_and_nearest_neighbor_scaled_cache(self):
        image = pygame.Surface((2, 2), pygame.SRCALPHA)
        image.fill((0, 0, 0, 0))
        image.set_at((0, 0), (255, 0, 0, 255))
        path = self.save("pixel.png", image)
        with patch("pygame.image.load", wraps=pygame.image.load) as load:
            first = self.manager.load_png("pixel.png")
            second = self.manager.load_png(path)
            self.assertIs(first, second)
            large = self.manager.scaled("pixel.png", (4, 4))
            self.assertIs(large, self.manager.scaled(path, (4, 4)))
            self.assertEqual(load.call_count, 1)
        self.assertEqual(large.get_at((0, 0)), (255, 0, 0, 255))
        self.assertEqual(large.get_at((3, 3)).a, 0)

    def test_sheet_slicing_and_individual_frames(self):
        sheet = pygame.Surface((4, 2), pygame.SRCALPHA)
        sheet.fill((0, 0, 0, 0))
        sheet.fill((255, 0, 0, 255), (0, 0, 2, 2))
        sheet.fill((0, 255, 0, 255), (2, 0, 2, 2))
        self.save("walk.png", sheet)
        frames = self.manager.load_frames("walk.png", frame_size=(2, 2), count=2)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].get_at((0, 0))[:3], (255, 0, 0))
        self.assertEqual(frames[1].get_at((0, 0))[:3], (0, 255, 0))
        self.save("idle0.png", frames[0])
        self.save("idle1.png", frames[1])
        individual = self.manager.load_frames(["idle0.png", "idle1.png"])
        self.assertEqual(len(individual), 2)
        with self.assertRaises(ValueError):
            self.manager.load_frames("walk.png", frame_size=(3, 2))

    def test_animation_json_and_procedural_fallback_for_missing_sheets(self):
        config = {"animations": {
            "idle": {"sheet": "absent.png", "frame_size": [28, 56],
                     "count": 2, "durations_ms": [200, 300]},
        }}
        (self.root / "animation.json").write_text(json.dumps(config), encoding="utf-8")
        clips, durations = self.manager.load_animation_config("animation.json")
        animation = PlayerAnimation(durations, clips)
        self.assertEqual(animation.frame_durations["idle"], (200, 300))
        self.assertNotIn("idle", animation.sprite_clips)
        animation.update(0, grounded=True, vx=0, vy=0)
        target = pygame.Surface((60, 70), pygame.SRCALPHA)
        animation.draw(target, 16, 5, 28, 56, 1, (255, 0, 0), (0, 0, 255), (0, 0, 0))
        self.assertGreater(target.get_bounding_rect().width, 0)

    def test_punch_pose_replaces_locomotion_sprite_without_leaving_it_visible(self):
        base = pygame.Surface((28, 56), pygame.SRCALPHA)
        base.fill((0, 0, 0, 0))
        base.fill((20, 80, 200, 255), (8, 8, 12, 48))
        punch = pygame.Surface((28, 56), pygame.SRCALPHA)
        punch.fill((0, 0, 0, 0))
        punch.fill((255, 220, 0, 255), (17, 25, 10, 8))
        punch.set_at((0, 0), (255, 220, 0, 255))
        punch.set_at((27, 55), (255, 220, 0, 255))
        animation = PlayerAnimation(sprite_clips={
            "idle": {"frames": (base,), "durations_ms": (100,)},
            "punch": {"frames": (punch,)},
        })
        target = pygame.Surface((80, 80), pygame.SRCALPHA)
        animation.draw(target, 20, 10, 28, 56, 1, None, None, None, 0.5)
        self.assertEqual(target.get_at((38, 36))[:3], (255, 220, 0))
        self.assertEqual(target.get_at((32, 37)).a, 0)
        animation.update(100, grounded=True, vx=0, vy=0)
        self.assertEqual(animation.frame, 0)

    def test_validator_checks_frame_consistency_and_alpha(self):
        self.save("characters/player/animations/idle0.png",
                  pygame.Surface((2, 2), pygame.SRCALPHA))
        self.save("characters/player/animations/idle1.png",
                  pygame.Surface((3, 2), pygame.SRCALPHA))
        config = {"animations": {"idle": {
            "frames": ["characters/player/animations/idle0.png",
                       "characters/player/animations/idle1.png"],
            "durations_ms": [200, 200],
        }}}
        config_path = self.root / "characters/player/animation.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config), encoding="utf-8")
        with redirect_stdout(StringIO()):
            self.assertEqual(validate(self.root), 1)
        self.save("characters/player/animations/idle1.png",
                  pygame.Surface((2, 2), pygame.SRCALPHA))
        with redirect_stdout(StringIO()):
            self.assertEqual(validate(self.root), 0)

    def test_validator_accepts_opaque_block_textures(self):
        self.save("blocks/stone.png", pygame.Surface((32, 32)))
        with redirect_stdout(StringIO()):
            self.assertEqual(validate(self.root), 0)

    def test_project_idle_sprite_is_loaded_on_the_existing_canvas(self):
        project_root = Path(__file__).resolve().parents[1]
        manager = AssetManager(project_root / "assets")
        clips, durations = manager.load_animation_config("characters/player/animation.json")
        animation = PlayerAnimation(durations, clips)
        idle = animation.sprite_clips["idle"][0]
        self.assertEqual(idle.get_size(), (28, 56))
        self.assertTrue(idle.get_flags() & pygame.SRCALPHA)
        self.assertEqual(animation.frame_durations["idle"], (1200,))
        target = pygame.Surface((100, 100), pygame.SRCALPHA)
        animation.draw(target, 36, 10, 28, 56, 1, None, None, None)
        sprite_bounds = target.get_bounding_rect()
        self.assertEqual(sprite_bounds.midbottom, (50, 66))
        self.assertGreaterEqual(sprite_bounds.height, 58)
        self.assertLessEqual(sprite_bounds.height, 64)

    def test_project_walking_sheet_uses_four_anchored_frames(self):
        project_root = Path(__file__).resolve().parents[1]
        manager = AssetManager(project_root / "assets")
        clips, durations = manager.load_animation_config("characters/player/animation.json")
        animation = PlayerAnimation(durations, clips)
        frames = animation.sprite_clips["walking"]
        self.assertEqual(len(frames), 4)
        self.assertTrue(all(frame.get_size() == (28, 56) for frame in frames))
        self.assertEqual(animation.frame_durations["walking"], (90, 90, 90, 90))
        self.assertGreater(len({pygame.image.tobytes(frame, "RGBA") for frame in frames}), 1)
        for index in range(4):
            animation.update(0 if index == 0 else 90, grounded=True, vx=4, vy=0)
            target = pygame.Surface((100, 100), pygame.SRCALPHA)
            animation.draw(target, 36, 10, 28, 56, 1, None, None, None)
            bounds = target.get_bounding_rect()
            self.assertEqual(bounds.midbottom, (50, 66))
            self.assertGreaterEqual(bounds.height, 58)
            self.assertLessEqual(bounds.height, 64)

    def test_project_jumping_pose_uses_one_bottom_anchored_frame(self):
        project_root = Path(__file__).resolve().parents[1]
        manager = AssetManager(project_root / "assets")
        clips, durations = manager.load_animation_config("characters/player/animation.json")
        animation = PlayerAnimation(durations, clips)
        self.assertEqual(len(animation.sprite_clips["jumping"]), 1)
        self.assertEqual(animation.frame_durations["jumping"], (100,))
        animation.update(50, grounded=False, vx=0, vy=-1)
        target = pygame.Surface((100, 100), pygame.SRCALPHA)
        animation.draw(target, 36, 10, 28, 56, 1, None, None, None)
        bounds = target.get_bounding_rect()
        self.assertEqual(bounds.midbottom, (50, 66))
        self.assertGreaterEqual(bounds.height, 58)
        self.assertLessEqual(bounds.height, 64)

    def test_project_falling_pose_uses_one_bottom_anchored_frame(self):
        project_root = Path(__file__).resolve().parents[1]
        manager = AssetManager(project_root / "assets")
        clips, durations = manager.load_animation_config("characters/player/animation.json")
        animation = PlayerAnimation(durations, clips)
        self.assertEqual(len(animation.sprite_clips["falling"]), 1)
        self.assertEqual(animation.frame_durations["falling"], (120,))
        animation.update(50, grounded=False, vx=0, vy=1)
        target = pygame.Surface((100, 100), pygame.SRCALPHA)
        animation.draw(target, 36, 10, 28, 56, 1, None, None, None)
        bounds = target.get_bounding_rect()
        self.assertEqual(bounds.midbottom, (50, 66))
        self.assertGreaterEqual(bounds.height, 58)
        self.assertLessEqual(bounds.height, 64)

    def test_project_punch_sheet_loads_updated_three_frame_sprite_sheet(self):
        project_root = Path(__file__).resolve().parents[1]
        manager = AssetManager(project_root / "assets")
        clips, durations = manager.load_animation_config("characters/player/animation.json")
        animation = PlayerAnimation(durations, clips)
        frames = animation.sprite_clips["punch"]
        self.assertEqual(len(frames), 3)
        self.assertTrue(all(frame.get_size() == (512, 1024) for frame in frames))
        self.assertTrue(all(frame.get_at((0, 0)).a == 0 for frame in frames))
        self.assertGreater(len({pygame.image.tobytes(frame, "RGBA") for frame in frames}), 1)
        animation.update(0, grounded=True, vx=4, vy=0)
        renders = []
        for progress in (0.1, 0.5, 0.9):
            target = pygame.Surface((100, 100), pygame.SRCALPHA)
            animation.draw(target, 36, 10, 28, 56, 1, None, None, None, progress)
            bounds = target.get_bounding_rect()
            self.assertEqual(bounds.bottom, 66)
            self.assertEqual(bounds.height, 64)
            self.assertLessEqual(abs(bounds.centerx - 50), 3)
            renders.append(pygame.image.tobytes(target, "RGBA"))
        self.assertEqual(len(set(renders)), 3)


if __name__ == "__main__":
    unittest.main()
