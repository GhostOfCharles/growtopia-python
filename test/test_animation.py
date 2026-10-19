"""Focused animation and composition checks; no game saves are loaded or written."""

from collections import defaultdict
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame
import main as game
from src.animation import PlayerAnimation, PunchAnim


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def scene(self):
        font = pygame.font.Font(None, 24)
        app = SimpleNamespace(current_account=game.Account(), small_font=font,
                              hotbar_count_font=font, btn_font=font, label_font=font,
                              current_username="Animation", save_worlds=Mock(),
                              save_accounts=Mock())
        tiles = [[game.AIR] * game.GRID_W for _ in range(game.GRID_H)]
        tiles[40] = [game.DIRT] * game.GRID_W
        scene = game.GameScene(app, game.World("Animation", tiles, [50, 40]))
        scene.player.on_ground = True
        return scene

    def render(self, animation, *, facing=1, punching=False):
        surface = pygame.Surface((80, 80), pygame.SRCALPHA)
        animation.draw(surface, 25, 10, 28, 56, facing, game.HEAD_COLOR,
                       game.BODY_COLOR, game.OUTLINE, 0.5 if punching else None)
        return pygame.image.tobytes(surface, "RGBA")

    def test_state_transitions_follow_motion_without_changing_it(self):
        animation = PlayerAnimation()
        for grounded, vx, vy, expected in (
                (True, 0, 0, "idle"), (True, 4, 0, "walking"),
                (False, 4, -5, "jumping"), (False, 4, 0, "falling"),
                (False, -4, 5, "falling"), (True, 0, 0, "idle")):
            animation.update(16, grounded=grounded, vx=vx, vy=vy)
            self.assertEqual(animation.state, expected)

    def test_sprinting_animation_uses_six_configured_frames_at_fourteen_fps(self):
        scene=self.scene()
        animation=scene.player_animation
        frames=animation.sprite_clips["sprinting"]
        self.assertEqual(len(frames),6)
        self.assertTrue(all(frame.get_size()==(400,724) for frame in frames))
        self.assertTrue(all(frame.get_flags()&pygame.SRCALPHA for frame in frames))
        self.assertTrue(all(frame.get_at((0,0)).a==0 for frame in frames))
        self.assertAlmostEqual(animation.frame_durations["sprinting"][0],1000/14,places=3)
        animation.update(72,grounded=True,vx=8,vy=0,sprinting=True)
        self.assertEqual(animation.state,"sprinting")
        self.assertEqual(animation.frame,1)
        animation.update(16,grounded=False,vx=8,vy=-4,sprinting=True)
        self.assertEqual(animation.state,"jumping")
        animation.update(16,grounded=False,vx=8,vy=4,sprinting=True)
        self.assertEqual(animation.state,"falling")

    def test_sprint_frames_keep_complete_silhouettes_without_cell_edge_trails(self):
        scene = self.scene()
        animation = scene.player_animation
        frames = animation.sprite_clips["sprinting"]
        self.assertNotIn("sprinting", animation._preserve_canvas_states)
        self.assertEqual(len({pygame.image.tobytes(frame, "RGBA") for frame in frames}), 6)
        for frame in frames:
            mask = pygame.mask.from_surface(frame, 1)
            self.assertGreater(max(part.count() for part in mask.connected_components()), 80000)
            self.assertFalse(any(frame.get_at((edge, y)).a > 15
                                 for edge in (0, frame.get_width()-1)
                                 for y in range(frame.get_height())))

        heights = []
        for frame_index in range(len(frames)):
            animation.state = "sprinting"
            animation.elapsed_ms = frame_index * 1000 / 14
            surface = pygame.Surface((100, 100), pygame.SRCALPHA)
            animation.draw(surface, 36, 10, 28, 56, 1, game.HEAD_COLOR,
                           game.BODY_COLOR, game.OUTLINE)
            heights.append(surface.get_bounding_rect().height)
            bounds = surface.get_bounding_rect()
            self.assertIn(bounds.bottom, (65, 66))  # raised running foot or ground contact
        self.assertTrue(all(62 <= height <= 64 for height in heights))

    def test_every_player_and_zombie_pose_renders_unclipped_in_both_directions(self):
        scene = self.scene()
        zombie_animation = PlayerAnimation(scene.zombie_durations, scene.zombie_clips)
        for actor, animation in (("player", scene.player_animation),
                                 ("zombie", zombie_animation)):
            for state, frames in animation.sprite_clips.items():
                for index in range(len(frames)):
                    with self.subTest(actor=actor, state=state, frame=index):
                        animation.state = state if state != "punch" else "idle"
                        if state not in ("punch", "attack"):
                            animation.elapsed_ms = sum(animation.frame_durations[state][:index]) + 1
                        options = {}
                        if state == "punch":
                            options["punch_progress"] = (index + 0.25) / len(frames)
                        elif state == "attack":
                            options["full_body_state"] = "attack"
                            options["full_body_elapsed_ms"] = sum(
                                animation.frame_durations[state][:index]) + 1
                        bounds = []
                        for facing in (1, -1):
                            surface = pygame.Surface((160, 140), pygame.SRCALPHA)
                            animation.draw(surface, 66, 30, 28, 56, facing,
                                           game.HEAD_COLOR, game.BODY_COLOR,
                                           game.OUTLINE, **options)
                            rect = surface.get_bounding_rect(min_alpha=16)
                            self.assertGreaterEqual(rect.height, 40 if state == "heavy_landing" else 54)
                            self.assertLessEqual(rect.height, 64)
                            self.assertGreater(rect.left, 0)
                            self.assertGreater(rect.top, 0)
                            self.assertLess(rect.right, surface.get_width())
                            self.assertLessEqual(rect.bottom, 86)
                            self.assertGreaterEqual(rect.bottom, 84)
                            bounds.append(rect)
                        self.assertLessEqual(abs(bounds[0].width - bounds[1].width), 1)
                        self.assertLessEqual(abs(bounds[0].height - bounds[1].height), 1)

        # All zombie states share one crop, so its scratch crouch stays short.
        self.assertEqual(len({tuple(bounds) for bounds in zombie_animation._clip_bounds.values()}), 1)

    def test_sprint_input_raises_speed_and_swept_collision_stops_at_wall(self):
        self.assertEqual(game.MOVE_SPEED, 3.0)
        self.assertEqual(game.SPRINT_SPEED_MULTIPLIER, 1.5)
        scene=self.scene()
        player=scene.player
        keys=defaultdict(bool)
        keys[pygame.K_d]=True
        keys[pygame.K_LSHIFT]=True
        player.on_ground=True
        player.update(game.SIMULATION_STEP_MS,keys)
        self.assertEqual(player.vx,game.MOVE_SPEED*game.SPRINT_SPEED_MULTIPLIER)
        self.assertTrue(player.sprinting)
        keys[pygame.K_LSHIFT]=False
        player.update(game.SIMULATION_STEP_MS,keys)
        self.assertEqual(player.vx,game.MOVE_SPEED)
        self.assertFalse(player.sprinting)
        keys[pygame.K_d]=False
        keys[pygame.K_a]=True
        keys[pygame.K_RSHIFT]=True
        player.update(game.SIMULATION_STEP_MS,keys)
        self.assertEqual(player.vx,-game.MOVE_SPEED*game.SPRINT_SPEED_MULTIPLIER)
        self.assertTrue(player.sprinting)

        player.x=50*game.TILE+2
        player.y=40*game.TILE-game.PLAYER_H
        player.on_ground=True
        scene.world.tiles[39][51]=game.STONE
        keys[pygame.K_a]=False
        keys[pygame.K_d]=True
        player.update(game.SIMULATION_STEP_MS,keys)
        self.assertLessEqual(player.x+game.PLAYER_W,51*game.TILE)

    def test_configurable_timing_and_remainder(self):
        animation = PlayerAnimation({"walking": (40, 60, 80, 100)})
        animation.update(39, grounded=True, vx=4, vy=0)
        self.assertEqual(animation.frame, 0)
        animation.update(1, grounded=True, vx=4, vy=0)
        self.assertEqual(animation.frame, 1)
        animation.update(280, grounded=True, vx=4, vy=0)
        self.assertEqual(animation.frame, 1)
        animation.update(1, grounded=False, vx=4, vy=-3)
        self.assertEqual(animation.frame, 0)
        self.assertEqual(animation.elapsed_ms, 1)

    def test_same_elapsed_time_gives_same_frame_at_different_update_rates(self):
        outcomes = []
        for hz in (30, 60, 120, 144):
            animation = PlayerAnimation()
            remaining = 720.0
            while remaining > 1e-8:
                dt = min(1000 / hz, remaining)
                animation.update(dt, grounded=True, vx=4, vy=0)
                remaining -= dt
            outcomes.append(animation.frame)
        self.assertEqual(outcomes, [0, 0, 0, 0])

    def test_jumping_holds_last_pose_and_falling_loops(self):
        animation = PlayerAnimation()
        animation.update(1000, grounded=False, vx=0, vy=-1)
        self.assertEqual(animation.frame, 1)
        animation.update(240, grounded=False, vx=0, vy=1)
        self.assertEqual(animation.frame, 0)

    def test_invalid_timing_is_rejected(self):
        for durations in ((), (0,), (-1,), (float("inf"),)):
            with self.assertRaises(ValueError):
                PlayerAnimation({"idle": durations})
        with self.assertRaises(ValueError):
            PunchAnim(0)

    def test_full_body_action_replaces_locomotion_and_holds_last_frame(self):
        idle = pygame.Surface((28,56),pygame.SRCALPHA)
        idle.fill((0,255,0,255))
        frames=[]
        for red in (40,80,120,160,200,240):
            frame=pygame.Surface((28,56),pygame.SRCALPHA)
            frame.fill((red,0,0,255))
            frames.append(frame)
        animation=PlayerAnimation(sprite_clips={
            "idle":{"frames":(idle,),"durations_ms":(100,)},
            "attack":{"frames":frames,"durations_ms":(100,)*6}},
            sprite_height=56,preserve_canvas=True)
        surface=pygame.Surface((28,56),pygame.SRCALPHA)
        animation.draw(surface,0,0,28,56,1,game.HEAD_COLOR,game.BODY_COLOR,
                       game.OUTLINE,full_body_state="attack",full_body_elapsed_ms=310)
        self.assertEqual(surface.get_at((14,28))[:3],(160,0,0))
        animation.draw(surface,0,0,28,56,-1,game.HEAD_COLOR,game.BODY_COLOR,
                       game.OUTLINE,full_body_state="attack",full_body_elapsed_ms=900)
        self.assertEqual(surface.get_at((14,28))[:3],(240,0,0))

    def test_distinct_states_frames_facing_and_punch_overlay_render(self):
        animation = PlayerAnimation()
        images = []
        for grounded, vx, vy in ((True, 0, 0), (True, 4, 0),
                                (False, 4, -3), (False, 4, 3)):
            animation.update(1, grounded=grounded, vx=vx, vy=vy)
            images.append(self.render(animation))
        self.assertEqual(len(set(images)), 4)
        animation.update(121, grounded=False, vx=4, vy=3)
        self.assertNotEqual(self.render(animation), images[-1])
        self.assertNotEqual(self.render(animation, facing=-1), self.render(animation))
        self.assertNotEqual(self.render(animation, punching=True), self.render(animation))
        animation = PlayerAnimation()
        idle = self.render(animation)
        animation.update(600, grounded=True, vx=0, vy=0)
        self.assertNotEqual(self.render(animation), idle)
        animation.update(1, grounded=True, vx=4, vy=0)
        walk = self.render(animation)
        animation.update(90, grounded=True, vx=4, vy=0)
        self.assertNotEqual(self.render(animation), walk)

    def test_rendering_does_not_advance_animation_or_mutate_physics(self):
        scene = self.scene()
        before = vars(scene.player).copy()
        animation_before = vars(scene.player_animation).copy()
        for _ in range(3):
            scene.draw(pygame.Surface((game.WIDTH, game.HEIGHT)))
        self.assertEqual(vars(scene.player), before)
        self.assertEqual(vars(scene.player_animation), animation_before)
        scene.game.save_worlds.assert_not_called()
        scene.game.save_accounts.assert_not_called()

    def test_damage_tints_sprite_red_without_changing_its_bounds(self):
        scene = self.scene()
        scene.player.x = 10
        scene.player.y = 10
        sprite = pygame.Surface((28, 56), pygame.SRCALPHA)
        sprite.fill((40, 200, 60, 255))
        animation = PlayerAnimation(sprite_clips={
            "idle": {"frames": (sprite,), "durations_ms": (100,)},
        })
        normal = pygame.Surface((80, 90), pygame.SRCALPHA)
        scene.player.draw(normal, 0, 0, animation)

        scene.player.apply_damage(1)
        self.assertEqual(scene.player.flash_ms, game.LAVA_FLASH_MS)
        damaged = pygame.Surface((80, 90), pygame.SRCALPHA)
        scene.player.draw(damaged, 0, 0, animation)

        point = (24, 34)
        normal_color = normal.get_at(point)
        damaged_color = damaged.get_at(point)
        self.assertEqual(normal_color[:3], (40, 200, 60))
        self.assertGreater(damaged_color.r, damaged_color.g)
        self.assertGreater(damaged_color.r, damaged_color.b)
        self.assertEqual(damaged.get_bounding_rect(), normal.get_bounding_rect())

    def test_damage_flash_tints_are_cached_by_frame_and_intensity(self):
        animation = PlayerAnimation()
        sprite = pygame.Surface((28, 56), pygame.SRCALPHA)
        sprite.fill((40, 200, 60, 255))
        first = animation._flash_tint(sprite, 0.5)
        repeated = animation._flash_tint(sprite, 0.51)
        self.assertIs(first, repeated)
        self.assertEqual(len(animation._flash_masks), 1)
        self.assertEqual(len(animation._flash_tinted_frames), 1)

    def test_procedural_fallback_renders_about_two_tiles_tall_at_feet_anchor(self):
        animation = PlayerAnimation()
        surface = pygame.Surface((100, 100), pygame.SRCALPHA)
        animation.draw(surface, 36, 10, 28, 56, 1, (255, 0, 0),
                       (0, 0, 255), (0, 0, 0))
        bounds = surface.get_bounding_rect()
        self.assertEqual(bounds.height, 64)
        self.assertEqual(bounds.bottom, 66)

    def test_walking_and_jumping_continue_during_punch(self):
        scene = self.scene()
        baseline = self.scene()
        scene._punch_anim_toward(52, 39)
        for pressed, state in ((pygame.K_d, "walking"), (pygame.K_SPACE, "jumping")):
            keys = defaultdict(bool, {pressed: True})
            with patch.object(pygame.key, "get_pressed", return_value=keys):
                scene.update(game.SIMULATION_STEP_MS)
                baseline.update(game.SIMULATION_STEP_MS)
            self.assertEqual(scene.player_animation.state, state)
            self.assertTrue(scene.punch.active)
            self.assertEqual((scene.player.x, scene.player.y, scene.player.vx, scene.player.vy),
                             (baseline.player.x, baseline.player.y, baseline.player.vx, baseline.player.vy))
            scene.draw(pygame.Surface((game.WIDTH, game.HEIGHT)))
        with patch.object(pygame.key, "get_pressed", return_value=defaultdict(bool)):
            for _ in range(45):
                scene.update(game.SIMULATION_STEP_MS)
        self.assertEqual(scene.player_animation.state, "idle")
        self.assertFalse(scene.punch.active)

    def test_punch_duration_and_independent_locomotion_clock(self):
        punch = PunchAnim(240)
        punch.start((0, 0), (40, 20))
        punch.update(120)
        self.assertEqual(punch.current_pos(), (40, 20))
        punch.update(120)
        self.assertFalse(punch.active)
        self.assertEqual(punch.current_pos((5, 5)), (5, 5))


if __name__ == "__main__":
    unittest.main()
