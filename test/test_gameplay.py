"""Headless gameplay regressions; every write goes to a temporary save directory.

Run from the project root: python -m unittest discover -s test -v
"""

from collections import defaultdict
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pygame
import main as game


def keys_for(*pressed):
    return defaultdict(bool, {key: True for key in pressed})


class GameplayTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.original_saves = {
            path: path.read_bytes()
            for path in (PROJECT_ROOT / "worlds.json", PROJECT_ROOT / "accounts.json")
            if path.exists()
        }
        self.scratch = tempfile.TemporaryDirectory(prefix="sandbox-game-tests-")
        self.addCleanup(self.scratch.cleanup)
        for name in ("WORLDS_FILE", "ACCOUNTS_FILE"):
            target = Path(self.scratch.name) / getattr(game, name)
            patcher = patch.object(game, name, str(target))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = game.Game()
        self.app.set_username("Regression")
        self.scene = self.new_scene()
        self.key_patch = patch.object(pygame.key, "get_pressed", return_value=keys_for())
        self.mock_keys = self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.mouse_patch = patch.object(pygame.mouse, "get_pos", return_value=(800, 450))
        self.mock_mouse = self.mouse_patch.start()
        self.addCleanup(self.mouse_patch.stop)

    def tearDown(self):
        for path, before in self.original_saves.items():
            self.assertEqual(path.read_bytes(), before, f"Real save changed: {path}")

    def new_scene(self):
        tiles = [[game.AIR] * game.GRID_W for _ in range(game.GRID_H)]
        tiles[game.SURFACE_ROW] = [game.DIRT] * game.GRID_W
        tiles[-1] = [game.BEDROCK] * game.GRID_W
        world = game.World("Regression flat world", tiles, [50, game.SURFACE_ROW])
        self.app.worlds = [world]
        self.app.current_account = game.Account({"username": "Regression"})
        self.app.accounts["Regression"] = self.app.current_account
        scene = game.GameScene(self.app, world)
        self.app.scene = scene
        scene.player.on_ground = True
        return scene

    def advance(self, scene, duration_ms, render_hz, *pressed):
        self.mock_keys.return_value = keys_for(*pressed)
        remaining = duration_ms
        minimum_y = scene.player.y
        while remaining > 1e-7:
            elapsed = min(1000.0 / render_hz, remaining)
            scene.update(elapsed)
            minimum_y = min(minimum_y, scene.player.y)
            remaining -= elapsed
        return minimum_y

    def screen_tile(self, c, r):
        return (int((c + 0.5) * game.TILE - self.scene.cam_x),
                int((r + 0.5) * game.TILE - self.scene.cam_y))

    def test_movement_jump_and_camera_match_across_render_rates(self):
        outcomes = {}
        for hz in (30, 60, 120, 144):
            with self.subTest(render_hz=hz):
                scene = self.new_scene()
                start_x, start_y = scene.player.x, scene.player.y
                apex = self.advance(scene, 1000, hz, pygame.K_d, pygame.K_SPACE)
                self.advance(scene, 500, hz)
                self.advance(scene, 500, hz, pygame.K_a)
                player = scene.player
                self.assertAlmostEqual(player.x - start_x, game.MOVE_SPEED * 30, places=6)
                self.assertAlmostEqual(player.y, start_y, places=6)
                self.assertLess(apex, start_y - 100)
                outcomes[hz] = (player.x, player.y, player.vx, player.vy,
                                apex, scene.cam_x, scene.cam_y, player.hp)
        baseline = outcomes[60]
        for hz, outcome in outcomes.items():
            with self.subTest(render_hz=hz):
                for observed, expected in zip(outcome, baseline):
                    self.assertAlmostEqual(observed, expected, places=6)

    def test_nominal_horizontal_speed_is_preserved(self):
        start_x = self.scene.player.x
        self.advance(self.scene, 1000, 60, pygame.K_RIGHT)
        self.assertAlmostEqual(self.scene.player.x - start_x, game.MOVE_SPEED * 60)
        self.assertTrue(self.scene.player.on_ground)

    def test_long_frame_lands_on_first_floor(self):
        player = self.scene.player
        player.y -= 100
        player.vy = game.MAX_FALL
        player.on_ground = False
        self.scene.update(200)
        self.assertAlmostEqual(player.y + game.PLAYER_H, game.SURFACE_ROW * game.TILE)
        self.assertTrue(player.on_ground)
        self.assertFalse(player._collides(player.x, player.y))

    def test_extreme_frame_discards_backlog_after_bounded_catchup(self):
        start_x = self.scene.player.x
        self.mock_keys.return_value = keys_for(pygame.K_d)
        self.scene.update(2000)
        simulated = self.scene.time_ms
        self.assertGreater(simulated, 0)
        self.assertLessEqual(simulated, game.MAX_FRAME_MS + 1e-7)
        self.assertLess(self.scene.simulation_accumulator_ms, game.SIMULATION_STEP_MS)
        self.assertGreater(self.scene.player.x, start_x)
        self.assertLessEqual(self.scene.player.x - start_x,
                             game.MOVE_SPEED * game.MAX_FRAME_MS / game.SIMULATION_STEP_MS + 1e-7)
        after_stall_x = self.scene.player.x
        self.scene.update(game.SIMULATION_STEP_MS)
        self.assertAlmostEqual(self.scene.time_ms - simulated, game.SIMULATION_STEP_MS)
        self.assertAlmostEqual(self.scene.player.x - after_stall_x, game.MOVE_SPEED)

    def test_direct_long_player_update_cannot_cross_thin_floor(self):
        player = self.scene.player
        player.y -= 80
        player.vy = game.MAX_FALL
        player.on_ground = False
        player.update(200, keys_for())
        self.assertAlmostEqual(player.y + game.PLAYER_H, game.SURFACE_ROW * game.TILE)
        self.assertTrue(player.on_ground)

    def test_direct_long_player_update_cannot_cross_wall(self):
        player = self.scene.player
        wall_col = 53
        for row in range(game.SURFACE_ROW - 5, game.SURFACE_ROW):
            self.scene.world.tiles[row][wall_col] = game.STONE
        player.x = wall_col * game.TILE - game.PLAYER_W - 4
        player.update(200, keys_for(pygame.K_d))
        self.assertAlmostEqual(player.x + game.PLAYER_W, wall_col * game.TILE)
        self.assertEqual(player.vx, 0)
        self.assertFalse(player._collides(player.x, player.y))

    def test_direct_long_jump_update_stops_below_ceiling(self):
        player = self.scene.player
        ceiling_row = game.SURFACE_ROW - 3
        for col in (50, 51):
            self.scene.world.tiles[ceiling_row][col] = game.STONE
        player.y = (ceiling_row + 1) * game.TILE + 4
        player.on_ground = True
        player.update(200, keys_for(pygame.K_SPACE))
        self.assertAlmostEqual(player.y, (ceiling_row + 1) * game.TILE)
        self.assertEqual(player.vy, 0)
        self.assertFalse(player._collides(player.x, player.y))

    def test_heavy_landing_dust_uses_actual_fall_distance_and_emits_once(self):
        for fall_tiles, expected_emissions in ((4, 0), (5, 1)):
            with self.subTest(fall_tiles=fall_tiles):
                scene = self.new_scene()
                player = scene.player
                player.y = (game.SURFACE_ROW - fall_tiles) * game.TILE - game.PLAYER_H
                player.vy = 0.0
                player.on_ground = False
                emit = Mock(wraps=scene.effects.emit_landing)
                scene.effects.emit_landing = emit

                self.advance(scene, 1000, 60)
                self.assertTrue(player.on_ground)
                self.assertAlmostEqual(player.y + game.PLAYER_H,
                                       game.SURFACE_ROW * game.TILE)
                self.assertEqual(emit.call_count, expected_emissions)
                if expected_emissions:
                    self.assertGreaterEqual(emit.call_args.args[2], 5.0)
                    # Grounded simulation steps must not repeat the impact.
                    self.advance(scene, 300, 60)
                    self.assertEqual(emit.call_count, 1)

    def test_normal_jump_descent_does_not_emit_heavy_landing_dust(self):
        scene = self.new_scene()
        player = scene.player
        emit = Mock(wraps=scene.effects.emit_landing)
        scene.effects.emit_landing = emit

        self.advance(scene, game.SIMULATION_STEP_MS, 60, pygame.K_SPACE)
        self.advance(scene, 1000, 60)

        self.assertTrue(player.on_ground)
        self.assertEqual(emit.call_count, 0)

    def test_dropped_items_float_near_spawn_tile_with_pop_and_bob(self):
        drop = game.DroppedItem(self.scene.world, game.DIRT, 60, game.SURFACE_ROW - 1)
        origin = (drop.x, drop.y)
        center_x = drop.x + game.DROP_SIZE / 2
        center_y = drop.y + game.DROP_SIZE / 2
        self.assertLessEqual(abs(center_x - (60.5 * game.TILE)), game.DROP_SPAWN_JITTER)
        self.assertLessEqual(abs(center_y - ((game.SURFACE_ROW - .5) * game.TILE)),
                             game.DROP_SPAWN_JITTER)
        drop.update(60, self.scene.player)
        self.assertEqual((drop.x, drop.y), origin)
        first_offset = drop.bob_offset
        drop.update(100, self.scene.player)
        self.assertEqual((drop.x, drop.y), origin)
        self.assertNotEqual(drop.bob_offset, first_offset)
        self.assertFalse(drop.collected)

    def test_keyboard_mouse_and_wheel_keep_selecting_hotbar(self):
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4))
        self.assertEqual(self.scene.hotbar.selected, 3)
        self.scene.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=1))
        self.assertEqual(self.scene.hotbar.selected, 2)
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=self.scene.hotbar.slots[6].center))
        self.assertEqual(self.scene.hotbar.selected, 6)
        self.assertFalse(self.scene.damage)

    def test_world_tile_uses_texture_with_colored_fallback(self):
        self.scene.world.tiles = [[game.AIR] * game.GRID_W for _ in range(game.GRID_H)]
        self.scene.world.tiles[10][10] = game.DIRT
        self.scene.cam_x = 0
        self.scene.cam_y = 0
        self.scene.player.x = 1200
        self.scene.player.y = 200
        surface = pygame.Surface((game.WIDTH, game.HEIGHT))

        texture = self.scene.block_textures[game.DIRT]
        self.scene.draw(surface)
        self.assertEqual(surface.get_at((10 * game.TILE + 16, 10 * game.TILE + 16)),
                         texture.get_at((16, 16)))
        # The world scene now draws a gradient sky rather than the old flat SKY fill.
        sky_point = (10 * game.TILE - 1, 10 * game.TILE + 16)
        self.assertEqual(surface.get_at(sky_point),
                         self.scene.background._gradient.get_at(sky_point))

        self.scene.block_textures.pop(game.DIRT)
        self.scene.draw(surface)
        self.assertEqual(surface.get_at((10 * game.TILE + 16, 10 * game.TILE + 16)),
                         game.TILE_COLORS[game.DIRT])

    def test_hotbar_and_dropped_item_use_cached_block_textures(self):
        self.scene.hotbar.items[0] = {"tile": game.DIRT, "count": 1}
        surface = pygame.Surface((game.WIDTH, game.HEIGHT))
        self.scene.hotbar.draw(surface, self.scene.block_icons)
        swatch = self.scene.hotbar.slots[0].inflate(-20, -20)
        point = (swatch.x + 10, swatch.y + 10)
        self.assertEqual(surface.get_at(point),
                         self.scene.block_icons[game.DIRT].get_at((10, 10)))

        drop = game.DroppedItem(self.scene.world, game.DIRT, 10, 10)
        drop.draw(surface, 0, 0, self.scene.block_drop_textures)
        drop_point = (int(drop.x) + game.DROP_SIZE // 2,
                      int(drop.y + drop.bob_offset) + game.DROP_SIZE // 2)
        self.assertEqual(surface.get_at(drop_point),
                         self.scene.block_drop_textures[game.DIRT].get_at((9, 9)))

    def test_shared_tile_edges_hide_baked_lines_but_keep_exposed_outline(self):
        c, r = 10, 10
        self.scene.world.tiles[r][c] = game.DIRT
        self.scene.world.tiles[r][c + 1] = game.GRASS
        self.scene.world.tiles[r - 1][c] = game.STONE
        source = self.scene.block_textures[game.DIRT]
        variant = self.scene._terrain_texture_for(c, r, game.DIRT)

        self.assertEqual(variant.get_at((31, 16)), source.get_at((30, 16)))
        self.assertEqual(variant.get_at((16, 0)), source.get_at((16, 1)))
        self.assertEqual(variant.get_at((0, 16)), source.get_at((0, 16)))
        self.assertEqual(variant.get_at((16, 31)), source.get_at((16, 31)))
        self.assertIs(self.scene._terrain_texture_for(c, r, game.DIRT), variant)

    def test_mining_pickup_placement_and_save_roundtrip(self):
        c, r = 52, game.SURFACE_ROW
        with patch.object(game.random, "random", return_value=0):
            for hit in range(game.BREAK_HITS[game.DIRT]):
                self.scene._try_break(c, r)
                if hit + 1 < game.BREAK_HITS[game.DIRT]:
                    self.advance(self.scene, game.BLOCK_HIT_COOLDOWN_MS, 60)
        self.assertEqual(self.scene.world.get(c, r), game.AIR)
        self.assertNotIn((c, r), self.scene.damage)
        self.assertEqual(len(self.scene.drops), 1)
        drop = self.scene.drops[0]
        drop.x = self.scene.player.x + (game.PLAYER_W - game.DROP_SIZE) / 2
        drop.y = self.scene.player.y + (game.PLAYER_H - game.DROP_SIZE) / 2
        self.scene.update(1000 / 60)
        self.assertFalse(self.scene.drops)
        self.assertEqual(self.scene.hotbar.items[1], {"tile": game.DIRT, "count": 1})
        self.scene.hotbar.select(1)
        self.scene._try_place(c, r)
        self.assertEqual(self.scene.world.get(c, r), game.DIRT)
        self.assertEqual(self.scene.hotbar.selected, 0)
        self.assertEqual(self.scene.hotbar.items[1], {"tile": None, "count": 0})
        loaded_world = game.World.from_any(game.load_worlds()[0])
        loaded_account = game.load_accounts()["Regression"]
        self.assertEqual(loaded_world.to_dict(), self.scene.world.to_dict())
        self.assertEqual(loaded_account.to_dict(), self.app.current_account.to_dict())

    def test_invalid_breaks_do_not_damage_bedrock_or_distant_tiles(self):
        self.scene.world.tiles[game.SURFACE_ROW][52] = game.BEDROCK
        for target in ((52, game.SURFACE_ROW), (80, game.SURFACE_ROW), (-1, 40)):
            self.scene._try_break(*target)
        self.assertFalse(self.scene.damage)
        self.assertFalse(self.scene.drops)
        self.assertEqual(self.scene.world.get(52, game.SURFACE_ROW), game.BEDROCK)

    def test_placement_respects_overlap_range_and_cooldown(self):
        self.scene.hotbar.add_item(game.DIRT, 3)
        self.scene.hotbar.select(1)
        player_col = int(self.scene.player.x // game.TILE)
        player_row = int(self.scene.player.y // game.TILE)
        self.scene._try_place(player_col, player_row)
        self.scene._try_place(90, player_row)
        self.assertEqual(self.scene.hotbar.selected_item()["count"], 3)
        target = (52, game.SURFACE_ROW - 1)
        self.scene._try_place(*target)
        self.scene._try_place(53, game.SURFACE_ROW - 1)
        self.assertEqual(self.scene.world.get(*target), game.DIRT)
        self.assertEqual(self.scene.world.get(53, game.SURFACE_ROW - 1), game.AIR)
        self.assertEqual(self.scene.hotbar.selected_item()["count"], 2)
        self.advance(self.scene, game.PLACE_COOLDOWN, 60)
        self.scene._try_place(53, game.SURFACE_ROW - 1)
        self.assertEqual(self.scene.world.get(53, game.SURFACE_ROW - 1), game.DIRT)
        self.assertEqual(self.scene.hotbar.selected_item()["count"], 1)

    def test_placement_rejects_fractional_player_overlap_but_allows_touch(self):
        target = (52, game.SURFACE_ROW - 1)
        self.scene.hotbar.add_item(game.DIRT, 2)
        self.scene.hotbar.select(1)
        self.scene.player.x = target[0] * game.TILE - game.PLAYER_W + 0.2
        self.assertFalse(self.scene._try_place(*target))
        self.assertEqual(self.scene.world.get(*target), game.AIR)
        self.assertEqual(self.scene.hotbar.selected_item()["count"], 2)
        self.scene.player.x = target[0] * game.TILE - game.PLAYER_W
        self.assertTrue(self.scene._try_place(*target))
        self.assertEqual(self.scene.world.get(*target), game.DIRT)
        self.assertEqual(self.scene.hotbar.selected_item()["count"], 1)

    def test_successful_block_placement_plays_placed_sound_only_after_commit(self):
        self.app.audio.play = Mock(return_value=True)
        self.scene.hotbar.add_item(game.DIRT, 2)
        self.scene.hotbar.select(1)
        target = (52, game.SURFACE_ROW - 1)
        self.scene.world.tiles[target[1]][target[0]] = game.DIRT
        self.assertFalse(self.scene._try_place(*target))  # occupied
        self.assertEqual(self.app.audio.play.call_args.args[0], "cant_place")
        self.app.audio.play.reset_mock()
        self.scene.world.tiles[target[1]][target[0]] = game.AIR
        self.scene.player.x = target[0] * game.TILE - game.PLAYER_W
        self.assertTrue(self.scene._try_place(*target))
        self.app.audio.play.assert_called_once_with("block_placed")

    def test_damage_progress_expires(self):
        target = (52, game.SURFACE_ROW)
        self.scene._try_break(*target)
        self.assertEqual(self.scene.damage[target]["hits"], 1)
        self.advance(self.scene, game.DAMAGE_RESET_MS + 100, 60)
        self.assertNotIn(target, self.scene.damage)
        self.assertEqual(self.scene.world.get(*target), game.DIRT)

    def test_lava_damage_regeneration_and_respawn_remain_available(self):
        player = self.scene.player
        col = int(player.x // game.TILE)
        row = int(player.y // game.TILE)
        self.scene.world.tiles[row][col] = game.LAVA
        self.scene._apply_lava_damage(100)
        self.assertAlmostEqual(player.hp, game.MAX_HP - game.LAVA_DPS * 0.1)
        self.assertGreater(player.knockback_ms, 0)
        self.scene.world.tiles[row][col] = game.AIR
        player.knockback_ms = 0
        self.advance(self.scene, game.REGEN_DELAY_MS + 1000, 60)
        self.assertEqual(player.hp, game.MAX_HP)
        player.hp = 1
        player.x += 40
        player.respawn()
        self.assertEqual((player.x, player.y), (player.spawn_x, player.spawn_y))
        self.assertEqual(player.hp, game.MAX_HP)

    def test_real_save_formats_load_and_roundtrip_from_copies(self):
        worlds_path = PROJECT_ROOT / "worlds.json"
        accounts_path = PROJECT_ROOT / "accounts.json"
        if not worlds_path.exists() or not accounts_path.exists():
            self.skipTest("No existing project saves to inspect")
        raw_worlds = json.loads(worlds_path.read_text(encoding="utf-8"))
        worlds = [game.World.from_any(entry) for entry in raw_worlds]
        for world, original in zip(worlds, raw_worlds):
            if isinstance(original, dict):
                self.assertEqual(world.to_dict(), original)
        game.save_worlds([world.to_dict() for world in worlds])
        self.assertEqual(game.load_worlds(), [world.to_dict() for world in worlds])
        raw_accounts = json.loads(accounts_path.read_text(encoding="utf-8"))
        accounts = {name: game.Account(data) for name, data in raw_accounts.items()}
        game.save_accounts(accounts)
        self.assertEqual({name: acc.to_dict() for name, acc in game.load_accounts().items()},
                         {name: acc.to_dict() for name, acc in accounts.items()})

    def test_menu_and_gameplay_render_and_escape_saves_profile(self):
        surface = pygame.Surface((game.WIDTH, game.HEIGHT))
        self.scene.draw(surface)
        self.assertNotEqual(surface.get_at((0, game.HEIGHT // 2))[:3], (0, 0, 0))
        self.scene.hotbar.add_item(game.STONE, 2)
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertTrue(self.scene.paused)
        save_exit = next(rect for rect, label in self.scene.hud.layout.pause_buttons
                         if label == "Save and Exit")
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=save_exit.center))
        self.assertIsInstance(self.app.scene, game.MenuScene)
        self.app.scene.draw(surface)
        self.assertEqual(game.load_accounts()["Regression"].inventory[1],
                         {"tile": game.STONE, "count": 2})

    def test_pause_freezes_game_and_escape_resumes(self):
        start = (self.scene.player.x, self.scene.time_ms)
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertTrue(self.scene.paused)
        self.mock_keys.return_value = keys_for(pygame.K_d)
        self.scene.update(500)
        self.assertEqual((self.scene.player.x, self.scene.time_ms), start)
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertFalse(self.scene.paused)
        self.advance(self.scene, 100, 60, pygame.K_d)
        self.assertGreater(self.scene.player.x, start[0])

    def test_pause_button_and_overlay_clicks_do_not_start_world_actions(self):
        pause_point = self.scene.hud.layout.pause_button.center
        with patch.object(self.scene, "_try_break") as mine, \
                patch.object(self.scene, "_try_place") as place:
            self.scene.handle_event(pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=pause_point))
            self.assertTrue(self.scene.paused)
            self.scene.handle_event(pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=self.screen_tile(52, game.SURFACE_ROW - 1)))
            self.assertTrue(self.scene.paused)
            mine.assert_not_called()
            place.assert_not_called()

    def test_pause_settings_controls_and_responsive_layout(self):
        other_size = game.HUDRenderer((900, 600)).layout
        self.assertEqual(other_size.hotbar_slots[0].left,
                         (900 - (8 * other_size.slot_size + 7 * other_size.slot_gap)) // 2)
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        settings = next(rect for rect, label in self.scene.hud.layout.pause_buttons
                        if label == "Settings")
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=settings.center))
        self.assertEqual(self.scene.pause_page, "settings")
        scale_up, _ = self.scene.hud._settings_controls()[1]
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=scale_up.center))
        self.assertGreater(self.scene.hud.scale, 1.0)
        back = self.scene.hud.pause_button_rects("settings")[0][0]
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=back.center))
        controls = next(rect for rect, label in self.scene.hud.layout.pause_buttons
                        if label == "Controls")
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=controls.center))
        self.assertEqual(self.scene.pause_page, "controls")

    def test_audio_jump_break_selection_damage_and_world_transitions(self):
        audio = self.app.audio
        audio.play = Mock(return_value=True)

        self.scene.player.on_ground = True
        self.scene._simulate_step(game.SIMULATION_STEP_MS, keys_for(pygame.K_SPACE))
        self.scene._simulate_step(game.SIMULATION_STEP_MS, keys_for(pygame.K_SPACE))
        self.assertEqual([call.args[0] for call in audio.play.call_args_list].count("jump"), 1)
        self.assertEqual(audio.play.call_args.kwargs["channel_key"], "movement")

        for tile, sound in ((game.DIRT, "block_soft"), (game.STONE, "block_hard")):
            scene = self.new_scene()
            audio.play.reset_mock()
            col, row = 50, game.SURFACE_ROW + 1
            scene.world.tiles[row][col] = tile
            scene.damage[(col, row)] = {"hits": game.BREAK_HITS[tile] - 1,
                                        "timer": game.DAMAGE_RESET_MS}
            self.assertTrue(scene._try_break(col, row))
            self.assertIn(sound, [call.args[0] for call in audio.play.call_args_list])
            self.assertIn("block_hit_hard" if tile == game.STONE else "block_hit_soft",
                          [call.args[0] for call in audio.play.call_args_list])

        scene = self.new_scene()
        audio.play.reset_mock()
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3))
        self.assertEqual([call.args[0] for call in audio.play.call_args_list],
                         ["hotbar_select", "hotbar_select"])

        audio.play.reset_mock()
        scene.player.hp = .1
        with patch.object(scene.player, "overlapping_lava_tiles", return_value=[(50, 40)]):
            scene._apply_lava_damage(100)
        self.assertEqual([call.args[0] for call in audio.play.call_args_list].count("death"), 1)
        self.assertEqual([call.args[0] for call in audio.play.call_args_list].count("burn"), 1)

        audio.play.reset_mock()
        self.app.scene = game.MenuScene(self.app)
        self.app.change_scene(scene)
        scene.on_exit()
        self.assertEqual([call.args[0] for call in audio.play.call_args_list],
                         ["enter_world", "leave_world"])

    def test_configured_block_durability_and_hit_destruction_feedback(self):
        self.assertEqual(game.BLOCK_DURABILITY[game.DIRT], 4)
        self.assertEqual(game.BLOCK_DURABILITY[game.GRASS], 4)
        self.assertEqual(game.BLOCK_DURABILITY[game.STONE], 10)
        self.assertIs(game.BREAK_HITS, game.BLOCK_DURABILITY)

        for tile, expected_hits, hit_sound, broken_sound in (
                (game.DIRT, 4, "block_hit_soft", "block_soft"),
                (game.GRASS, 4, "block_hit_soft", "block_soft"),
                (game.STONE, 10, "block_hit_hard", "block_hard")):
            scene = self.new_scene()
            audio = self.app.audio
            audio.play = Mock(return_value=True)
            col, row = 50, game.SURFACE_ROW + 1
            scene.world.tiles[row][col] = tile

            for _ in range(expected_hits - 1):
                self.assertTrue(scene._try_break(col, row))
                self.assertEqual(scene.world.tiles[row][col], tile)
                self.advance(scene, game.BLOCK_HIT_COOLDOWN_MS, 60)
            self.assertNotIn(broken_sound,
                             [call.args[0] for call in audio.play.call_args_list])
            self.advance(scene, game.BLOCK_HIT_COOLDOWN_MS, 60)
            self.assertTrue(scene._try_break(col, row))
            self.assertEqual(scene.world.tiles[row][col], game.AIR)
            names = [call.args[0] for call in audio.play.call_args_list]
            self.assertEqual(names.count(hit_sound), expected_hits)
            self.assertEqual(names.count(broken_sound), 1)
            self.assertEqual(audio.play.call_args_list[-2].kwargs["volume"],
                             game.BLOCK_HIT_FINAL_VOLUME)

        audio = self.app.audio
        audio.play.reset_mock()
        self.assertFalse(scene._try_break(col, row))  # now empty
        self.assertFalse(scene._try_break(50, game.GRID_H - 1))  # bedrock
        audio.play.assert_not_called()

    def test_invalid_placement_emits_feedback_only_for_attempted_tile(self):
        self.app.audio.play = Mock(return_value=True)
        self.scene.hotbar.add_item(game.DIRT)
        self.scene.hotbar.select(1)
        self.assertFalse(self.scene._try_place(50, game.SURFACE_ROW))  # occupied
        self.assertEqual(self.app.audio.play.call_args.args[0], "cant_place")
        self.assertEqual(self.app.audio.play.call_args.kwargs["cooldown_ms"],
                         game.INVALID_PLACE_SOUND_COOLDOWN_MS)
        self.app.audio.play.reset_mock()
        self.scene.hotbar.select(0)
        self.assertFalse(self.scene._try_place(50, game.SURFACE_ROW))  # fist, no placement
        self.app.audio.play.assert_not_called()

    def test_item_pickup_sound_plays_when_drop_is_collected(self):
        self.app.audio.play = Mock(return_value=True)
        self.scene.player.on_ground = True

        class Pickup:
            tile_type = game.DIRT
            collected = False

            def update(self, _dt, _player):
                self.collected = True

        self.scene.drops = [Pickup()]
        self.scene._simulate_step(game.SIMULATION_STEP_MS, keys_for())
        self.app.audio.play.assert_called_once_with(
            "item_drop", channel_key="movement", pitch="high")
        self.assertEqual(self.scene.drops, [])

    def test_jump_and_airborne_pickup_do_not_stack_drop_sound(self):
        self.app.audio.play = Mock(return_value=True)
        self.scene.player.on_ground = True

        class Pickup:
            tile_type = game.DIRT
            collected = False

            def update(self, _dt, _player):
                self.collected = True

        self.scene.drops = [Pickup()]
        self.scene._simulate_step(game.SIMULATION_STEP_MS, keys_for(pygame.K_SPACE))
        self.assertEqual([call.args[0] for call in self.app.audio.play.call_args_list],
                         ["jump"])
        self.assertEqual(self.scene.hotbar.items[1], {"tile": game.DIRT, "count": 1})

    def test_profile_world_creation_and_existing_world_selection_controls(self):
        self.app.change_scene(game.MenuScene(self.app))
        menu = self.app.scene
        menu.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=menu.name_input.rect.center))
        for _ in menu.name_input.text:
            menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, unicode=""))
        for character in "New Tester":
            menu.handle_event(pygame.event.Event(
                pygame.KEYDOWN, key=ord(character.lower()), unicode=character))
        menu.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=menu.buttons[0].rect.center))
        self.assertEqual(self.app.current_username, "New Tester")
        self.assertIsInstance(self.app.scene, game.CreateWorldScene)
        chooser = self.app.scene
        chooser.draw(self.app.screen)
        chooser.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=chooser.input.rect.center))
        for character in "Fresh World":
            chooser.handle_event(pygame.event.Event(
                pygame.KEYDOWN, key=ord(character.lower()), unicode=character))
        chooser.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r"))
        self.assertIsInstance(self.app.scene, game.GameScene)
        created_world = self.app.scene.world
        self.assertEqual(created_world.name, "Fresh World")
        self.assertIn("New Tester", game.load_accounts())
        self.assertIn("Fresh World", [world["name"] for world in game.load_worlds()])
        self.app.scene.draw(self.app.screen)
        self.app.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        paused_scene = self.app.scene
        save_exit = next(rect for rect, label in paused_scene.hud.layout.pause_buttons
                         if label == "Save and Exit")
        paused_scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=save_exit.center))
        menu = self.app.scene
        menu.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=menu.buttons[0].rect.center))
        chooser = self.app.scene
        index = chooser.world_list.items.index("Fresh World")
        row_point = (chooser.world_list.rect.x + 20,
                     chooser.world_list.rect.y + index * chooser.world_list.row_h + 20)
        chooser.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=row_point))
        self.assertIsInstance(self.app.scene, game.GameScene)
        self.assertIs(self.app.scene.world, created_world)

    def test_game_loop_quit_event_saves_inventory_and_shuts_down(self):
        self.scene.hotbar.add_item(game.STONE, 3)
        clock = Mock()
        clock.tick.return_value = game.SIMULATION_STEP_MS
        with patch.object(self.app, "clock", clock), \
                patch.object(pygame.event, "get", return_value=[pygame.event.Event(pygame.QUIT)]), \
                patch.object(pygame.display, "flip", wraps=pygame.display.flip) as flip, \
                patch.object(pygame, "quit", wraps=pygame.quit) as quit_pygame, \
                patch.object(game.sys, "exit", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.app.run()
        self.assertFalse(self.app.running)
        clock.tick.assert_called_once_with(game.FPS)
        flip.assert_called_once()
        quit_pygame.assert_called_once()
        self.assertEqual(game.load_accounts()["Regression"].inventory[1],
                         {"tile": game.STONE, "count": 3})

    def test_ui_panels_and_hotbar_gaps_do_not_trigger_world_actions(self):
        first_slot = self.scene.hotbar.slots[0]
        layout = self.scene.hud.layout
        points = (layout.player_panel.center, layout.world_panel.center,
                  layout.pause_button.center, layout.item_label.center,
                  (first_slot.right + game.HOTBAR_GAP // 2, first_slot.centery),
                  first_slot.center)
        with patch.object(self.scene, "_try_break") as mine, \
                patch.object(self.scene, "_try_place") as place:
            for point in points:
                with self.subTest(point=point):
                    self.assertTrue(self.scene._action_over_ui(point))
                    self.scene.handle_event(pygame.event.Event(
                        pygame.MOUSEBUTTONDOWN, button=1, pos=point))
                    self.advance(self.scene, game.ACTION_REPEAT_MS + 50, 60)
            mine.assert_not_called()
            place.assert_not_called()

    def test_lower_hotbar_edges_and_gaps_cannot_start_dragged_hold(self):
        first_slot = self.scene.hotbar.slots[0]
        points = ((first_slot.centerx, first_slot.bottom - 1),
                  (first_slot.centerx, first_slot.bottom - 12),
                  (first_slot.right + game.HOTBAR_GAP // 2, first_slot.bottom - 12))
        world_point = self.screen_tile(52, game.SURFACE_ROW - 1)
        with patch.object(self.scene, "_try_break") as mine, \
                patch.object(self.scene, "_try_place") as place:
            for point in points:
                with self.subTest(point=point):
                    self.assertTrue(self.scene._action_over_ui(point))
                    self.scene.handle_event(pygame.event.Event(
                        pygame.MOUSEBUTTONDOWN, button=1, pos=point))
                    self.scene.handle_event(pygame.event.Event(
                        pygame.MOUSEMOTION, pos=world_point, rel=(0, 0), buttons=(1, 0, 0)))
                    self.advance(self.scene, game.ACTION_REPEAT_MS * 2, 60)
                    self.assertFalse(self.scene._held_buttons)
                    self.scene.handle_event(pygame.event.Event(
                        pygame.MOUSEBUTTONUP, button=1, pos=world_point))
            mine.assert_not_called()
            place.assert_not_called()

    def test_outside_viewport_clicks_do_not_start_world_actions(self):
        points = ((-1, 450), (game.WIDTH, 450), (800, -1), (800, game.HEIGHT))
        with patch.object(self.scene, "_try_break") as mine, \
                patch.object(self.scene, "_try_place") as place:
            for point in points:
                with self.subTest(point=point):
                    self.assertTrue(self.scene._action_over_ui(point))
                    self.scene.handle_event(pygame.event.Event(
                        pygame.MOUSEBUTTONDOWN, button=1, pos=point))
                    self.advance(self.scene, game.ACTION_REPEAT_MS * 2, 60)
                    self.assertFalse(self.scene._held_buttons)
            mine.assert_not_called()
            place.assert_not_called()

    def test_held_action_pauses_over_ui_or_outside_then_resumes_in_world(self):
        for blocked_point in (self.scene.hud.layout.player_panel.center,
                              (-1, 450), (game.WIDTH, 450)):
            with self.subTest(blocked_point=blocked_point):
                self.scene = self.new_scene()
                target = (52, game.SURFACE_ROW - 1)
                world_point = self.screen_tile(*target)
                with patch.object(self.scene, "_try_break", return_value=True) as mine:
                    self.scene.handle_event(pygame.event.Event(
                        pygame.MOUSEBUTTONDOWN, button=1, pos=world_point))
                    self.assertEqual(mine.call_count, 1)
                    self.scene.handle_event(pygame.event.Event(
                        pygame.MOUSEMOTION, pos=blocked_point, rel=(0, 0), buttons=(1, 0, 0)))
                    self.advance(self.scene, game.ACTION_REPEAT_MS * 2, 60)
                    self.assertEqual(mine.call_count, 1)
                    self.scene.handle_event(pygame.event.Event(
                        pygame.MOUSEMOTION, pos=world_point, rel=(0, 0), buttons=(1, 0, 0)))
                    self.advance(self.scene, game.ACTION_REPEAT_MS, 60)
                    self.assertEqual(mine.call_count, 2)
                    self.assertEqual(mine.call_args.args, target)

    def test_hold_repeats_mining_and_release_stops_it(self):
        target = (52, game.SURFACE_ROW - 1)
        self.scene.world.tiles[target[1]][target[0]] = game.STONE
        point = self.screen_tile(*target)
        self.mock_mouse.return_value = point
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=point))
        self.assertEqual(self.scene.damage[target]["hits"], 1)
        self.advance(self.scene, game.ACTION_REPEAT_MS + game.SIMULATION_STEP_MS, 60)
        self.assertEqual(self.scene.damage[target]["hits"], 2)
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=point))
        self.advance(self.scene, game.ACTION_REPEAT_MS * 2, 60)
        self.assertEqual(self.scene.damage[target]["hits"], 2)

    def test_held_action_cadence_matches_across_render_rates(self):
        schedules = {}
        for hz in (30, 60, 120, 144):
            with self.subTest(render_hz=hz):
                scene = self.new_scene()
                self.scene = scene
                target = (52, game.SURFACE_ROW - 1)
                scene.world.tiles[target[1]][target[0]] = game.STONE
                calls = []

                def accepted_hit(*cell):
                    self.assertEqual(cell, target)
                    calls.append(scene.time_ms)
                    return True

                with patch.object(scene, "_try_break", side_effect=accepted_hit):
                    scene.handle_event(pygame.event.Event(
                        pygame.MOUSEBUTTONDOWN, button=1, pos=self.screen_tile(*target)))
                    self.advance(scene, 2000, hz)
                schedules[hz] = calls
                self.assertEqual(calls[0], 0)
                self.assertEqual(len(calls), 1 + int(2000 / game.ACTION_REPEAT_MS))
        for hz, calls in schedules.items():
            with self.subTest(render_hz=hz):
                self.assertEqual(calls, schedules[60])

    def test_manual_clicks_keep_immediate_mining_response(self):
        target = (52, game.SURFACE_ROW)
        point = self.screen_tile(*target)
        with patch.object(game.random, "random", return_value=1):
            for hit in range(game.BREAK_HITS[game.DIRT]):
                if hit:
                    self.advance(self.scene, game.BLOCK_HIT_COOLDOWN_MS, 60)
                self.scene.handle_event(pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1, pos=point))
                self.scene.handle_event(pygame.event.Event(
                    pygame.MOUSEBUTTONUP, button=1, pos=point))
        self.assertEqual(self.scene.world.get(*target), game.AIR)
        self.assertEqual(self.scene.time_ms,
                         (game.BREAK_HITS[game.DIRT] - 1) * game.BLOCK_HIT_COOLDOWN_MS)

    def test_successful_block_hits_are_limited_to_five_per_second(self):
        self.assertEqual(game.BLOCK_HIT_COOLDOWN_MS, 200)
        self.assertEqual(1000 / game.BLOCK_HIT_COOLDOWN_MS, 5)
        target = (52, game.SURFACE_ROW)
        self.assertTrue(self.scene._try_break(*target))
        self.assertFalse(self.scene._try_break(*target))
        self.assertEqual(self.scene.damage[target]["hits"], 1)
        self.advance(self.scene, game.BLOCK_HIT_COOLDOWN_MS - 1, 60)
        self.assertEqual(self.scene.damage[target]["hits"], 1)
        self.advance(self.scene, 1, 60)
        self.assertTrue(self.scene._try_break(*target))
        self.assertEqual(self.scene.damage[target]["hits"], 2)

    def test_changing_selection_cancels_a_held_action(self):
        target = (52, game.SURFACE_ROW - 1)
        self.scene.world.tiles[target[1]][target[0]] = game.STONE
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=self.screen_tile(*target)))
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
        self.advance(self.scene, game.ACTION_REPEAT_MS * 2, 60)
        self.assertEqual(self.scene.damage[target]["hits"], 1)
        self.assertFalse(self.scene._held_buttons)

    def test_last_placed_item_does_not_turn_hold_into_mining(self):
        target = (52, game.SURFACE_ROW - 1)
        self.scene.hotbar.add_item(game.DIRT)
        self.scene.hotbar.select(1)
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=self.screen_tile(*target)))
        self.assertEqual(self.scene.hotbar.selected, 0)
        self.advance(self.scene, game.ACTION_REPEAT_MS * 3, 60)
        self.assertEqual(self.scene.world.get(*target), game.DIRT)
        self.assertNotIn(target, self.scene.damage)
        self.assertFalse(self.scene._held_buttons)

    def test_focus_loss_cancels_hold_and_suspension_does_not_catch_up(self):
        target = (52, game.SURFACE_ROW - 1)
        self.scene.world.tiles[target[1]][target[0]] = game.STONE
        self.scene.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=self.screen_tile(*target)))
        start_x = self.scene.player.x
        self.mock_keys.return_value = keys_for(pygame.K_d)
        self.scene.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.scene.update(5000)
        self.assertEqual(self.scene.player.x, start_x)
        self.assertFalse(self.scene._held_buttons)
        self.assertEqual(self.scene.damage[target]["hits"], 1)
        self.scene.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        self.scene.update(5000)
        self.assertEqual(self.scene.player.x, start_x)
        self.scene.update(game.SIMULATION_STEP_MS)
        self.assertEqual(self.scene.player.x, start_x + game.MOVE_SPEED)
        self.assertEqual(self.scene.damage[target]["hits"], 1)

    def test_jump_tap_between_simulation_steps_is_retained(self):
        start_y = self.scene.player.y
        self.scene.update(game.SIMULATION_STEP_MS / 2)
        self.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        self.scene.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE))
        self.scene.update(game.SIMULATION_STEP_MS / 2)
        self.assertLess(self.scene.player.y, start_y)
        self.assertLess(self.scene.player.vy, 0)
        self.assertFalse(self.scene.player.on_ground)

    def test_fist_tracks_current_player_origin_and_camera(self):
        target = (52, game.SURFACE_ROW - 1)
        self.scene._punch_anim_toward(*target)
        expected_target = ((target[0] + 0.5) * game.TILE,
                           (target[1] + 0.5) * game.TILE)
        self.assertEqual(self.scene.punch.target, expected_target)
        self.scene.punch.update(game.PUNCH_DURATION / 4)
        self.scene.player.x += 17
        self.scene.cam_x += 9
        self.scene.cam_y -= 5
        current_origin = (self.scene.player.x + game.PLAYER_W / 2,
                          self.scene.player.y + game.PLAYER_H / 2)
        surface = pygame.Surface((game.WIDTH, game.HEIGHT))
        expected_current = self.scene.punch.current_pos(current_origin)
        expected_screen_target = (expected_current[0] - self.scene.cam_x,
                                  expected_current[1] - self.scene.cam_y)
        with patch.object(self.scene.punch_effect, "draw",
                          wraps=self.scene.punch_effect.draw) as sprite_effect:
            with patch.object(pygame.draw, "line") as hardcoded_lines:
                self.scene._draw_fist(surface)
        self.assertEqual(sprite_effect.call_count, 1)
        self.assertEqual(sprite_effect.call_args.args[1],
                         (current_origin[0] - self.scene.cam_x,
                          current_origin[1] - self.scene.cam_y))
        self.assertEqual(sprite_effect.call_args.args[2], expected_screen_target)
        self.assertEqual(sprite_effect.call_args.args[3], self.scene.punch.progress())
        hardcoded_lines.assert_not_called()
        self.scene.punch.update(game.PUNCH_DURATION / 4)
        self.assertEqual(self.scene.punch.current_pos(current_origin), expected_target)

    def test_punch_target_turns_player_toward_target_tile(self):
        player = self.scene.player
        player_center_x = player.x + game.PLAYER_W / 2
        right_tile = int(player_center_x // game.TILE) + 1
        left_tile = int(player_center_x // game.TILE) - 1

        player.facing = -1
        self.scene._punch_anim_toward(right_tile, 10)
        self.assertEqual(player.facing, 1)

        # Direction updates even when the current swing cannot restart.
        self.scene._punch_anim_toward(left_tile, 10)
        self.assertEqual(player.facing, -1)

    def test_impacts_are_world_anchored_expire_and_do_not_change_loot_rng(self):
        target = (52, game.SURFACE_ROW)
        before_rng = game.random.getstate()
        self.assertTrue(self.scene._try_break(*target))
        self.assertEqual(game.random.getstate(), before_rng)
        particles = self.scene.effects.particles
        self.assertTrue(particles)
        center = ((target[0] + 0.5) * game.TILE, (target[1] + 0.5) * game.TILE)
        for particle in particles:
            self.assertLessEqual(abs(particle.x - center[0]), game.TILE / 2)
            self.assertLessEqual(abs(particle.y - center[1]), game.TILE / 2)
        self.advance(self.scene, 500, 60)
        self.assertFalse(self.scene.effects.particles)
        self.assertEqual(self.scene.damage[target]["hits"], 1)

    def test_impact_render_buffer_stays_local_to_particles(self):
        effects = game.BlockEffects()
        effects.emit((320, 240), game.TILE_COLORS[game.DIRT], "hit")
        surface = pygame.Surface((game.WIDTH, game.HEIGHT))
        effects.draw(surface, 0, 0)
        self.assertIsNotNone(effects._layer)
        self.assertLess(effects._layer.get_width(), game.WIDTH // 2)
        self.assertLess(effects._layer.get_height(), game.HEIGHT // 2)

    def test_crack_overlay_is_reused_until_damage_changes(self):
        target = (52, game.SURFACE_ROW)
        self.scene.damage[target] = {"hits": 1, "timer": game.DAMAGE_RESET_MS}
        surface = pygame.Surface((game.WIDTH, game.HEIGHT))
        self.scene._draw_cracks(surface, *target, 0, 0)
        cached = self.scene.damage[target]["crack_surface"]
        self.scene._draw_cracks(surface, *target, 0, 0)
        self.assertIs(self.scene.damage[target]["crack_surface"], cached)

    def test_empty_punch_has_animation_and_no_hit_effects(self):
        target = (52, game.SURFACE_ROW - 1)
        self.assertFalse(self.scene._try_break(*target))
        self.assertTrue(self.scene.punch.active)
        self.assertFalse(self.scene.effects.particles)
        self.assertFalse(self.scene.damage)
        self.assertFalse(self.scene.drops)

    def test_visual_particle_pool_stays_bounded(self):
        for _ in range(100):
            self.scene.effects.emit((100, 100), game.TILE_COLORS[game.DIRT], "break")
        self.assertLessEqual(len(self.scene.effects.particles), self.scene.effects.MAX_PARTICLES)
        self.scene.effects.update(1000)
        self.assertFalse(self.scene.effects.particles)


if __name__ == "__main__":
    unittest.main()
