"""Headless tests for cached sound effects and playback guards."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from src.audio import AudioManager, SOUND_FILES


class FakeChannel:
    def __init__(self):
        self.volume = None
        self.played = []
        self.stop_count = 0

    def set_volume(self, volume):
        self.volume = volume

    def play(self, sound):
        self.played.append(sound)

    def stop(self):
        self.stop_count += 1


class FakeMixer:
    def __init__(self, fail_init=False):
        self.fail_init = fail_init
        self.channel = FakeChannel()
        self.num_channels = None
        self.loaded = []
        self.reserved = 0
        self.keyed_channel = FakeChannel()
        self.movement_channel = FakeChannel()

    def get_init(self):
        return not self.fail_init

    def init(self):
        if self.fail_init:
            raise pygame.error("no output device")

    def set_num_channels(self, count):
        self.num_channels = count

    def set_reserved(self, count):
        self.reserved = count

    def Channel(self, index):
        return self.keyed_channel if index == 0 else self.movement_channel

    def Sound(self, path=None, file=None):
        if path is not None and Path(path).name == "broken_block_hard.WAV":
            raise pygame.error("invalid WAV")
        sound = object()
        self.loaded.append((path if path is not None else file, sound))
        return sound

    def find_channel(self, force=False):
        return self.channel


class AudioManagerTests(unittest.TestCase):
    def make_sound_dir(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name in SOUND_FILES.values():
            root.joinpath(name).touch()
        # Verify discovery is case-insensitive against the project's real style.
        (root / "broken_block_hard.wav").rename(root / "broken_block_hard.WAV")
        return root

    def test_cached_loading_uses_case_insensitive_filenames_and_skips_invalid(self):
        mixer = FakeMixer()
        manager = AudioManager(self.make_sound_dir(), mixer=mixer)
        self.assertTrue(manager.available)
        self.assertEqual(mixer.num_channels, 12)
        self.assertNotIn("block_hard", manager.sounds)
        self.assertIn("burn", manager.sounds)
        self.assertEqual(len(manager.sounds), len(SOUND_FILES) - 1)
        self.assertEqual(len(mixer.loaded), len(manager.sounds))

    def test_volume_and_per_event_cooldown_prevent_duplicate_playback(self):
        mixer = FakeMixer()
        manager = AudioManager(self.make_sound_dir(), master_volume=.5,
                               sfx_volume=.4, mixer=mixer)
        self.assertTrue(manager.play("burn", cooldown_ms=350))
        self.assertFalse(manager.play("burn", cooldown_ms=350))
        self.assertAlmostEqual(mixer.channel.volume, .2)
        manager.update(349)
        self.assertFalse(manager.play("burn"))
        manager.update(1)
        self.assertTrue(manager.play("burn"))
        self.assertEqual(len(mixer.channel.played), 2)

        self.assertTrue(manager.play("cant_place", cooldown_ms=300))
        self.assertFalse(manager.play("cant_place", cooldown_ms=300))
        manager.update(300)
        self.assertTrue(manager.play("cant_place"))

    def test_repeated_block_hit_feedback_reuses_a_dedicated_channel(self):
        mixer = FakeMixer()
        manager = AudioManager(self.make_sound_dir(), mixer=mixer)
        self.assertTrue(manager.play("block_hit_soft", channel_key="block_hit", volume=.65))
        self.assertTrue(manager.play("block_hit_hard", channel_key="block_hit", volume=.65))
        self.assertEqual(mixer.reserved, 2)
        self.assertEqual(mixer.keyed_channel.stop_count, 1)
        self.assertEqual(len(mixer.keyed_channel.played), 2)
        self.assertEqual(mixer.channel.played, [])

    def test_movement_channel_replaces_pickup_tail_when_jumping(self):
        mixer = FakeMixer()
        manager = AudioManager(self.make_sound_dir(), mixer=mixer)
        self.assertTrue(manager.play("item_drop", channel_key="movement"))
        self.assertTrue(manager.play("jump", channel_key="movement"))
        self.assertEqual(mixer.movement_channel.stop_count, 1)
        self.assertEqual(len(mixer.movement_channel.played), 2)

    def test_ground_impact_loads_and_plays_original_pitch(self):
        from src.audio import PITCH_VARIATION_SOUNDS

        mixer = FakeMixer()
        manager = AudioManager(self.make_sound_dir(), mixer=mixer)
        self.assertIn("ground_impact", manager.sounds)
        self.assertNotIn("ground_impact", PITCH_VARIATION_SOUNDS)
        self.assertTrue(manager.play("ground_impact", channel_key="movement"))
        self.assertIs(mixer.movement_channel.played[-1], manager.sounds["ground_impact"])

    def test_pickup_uses_cached_higher_pitch_copy_of_item_drop(self):
        import io
        import wave

        root = self.make_sound_dir()
        source_path = root / SOUND_FILES["item_drop"]
        with wave.open(str(source_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00\x00" * 220)
        mixer = FakeMixer()
        manager = AudioManager(root, mixer=mixer)
        high = manager.pitch_variants["item_drop_high"][0]
        encoded = next(payload for payload, sound in mixer.loaded if sound is high)
        self.assertGreater(wave.open(io.BytesIO(encoded.getvalue())).getframerate(), 22050)

        loaded_count = len(mixer.loaded)
        self.assertTrue(manager.play("item_drop", channel_key="movement", pitch="high"))
        self.assertIs(mixer.movement_channel.played[-1], high)
        self.assertEqual(len(mixer.loaded), loaded_count)

    def test_block_sounds_build_and_reuse_cached_pitch_variants(self):
        import random
        import wave

        root = self.make_sound_dir()
        # Keep this mock's one deliberately-invalid uppercase filename test
        # from rejecting the hard destruction sample in this variant test.
        (root / "broken_block_hard.WAV").rename(root / "broken_block_hard.wav")
        for key in ("block_hit_soft", "block_hit_hard", "block_soft", "block_hard",
                    "block_placed"):
            path = root / SOUND_FILES[key]
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(22050)
                wav.writeframes(b"\x00\x00" * 220)
        mixer = FakeMixer()
        manager = AudioManager(root, mixer=mixer, rng=random.Random(4))
        self.assertEqual({name: len(variants) for name, variants in
                          manager.pitch_variants.items()},
                         {**{name: 5 for name in ("block_hit_soft", "block_hit_hard",
                                                 "block_soft", "block_hard", "block_placed")},
                          "dash": 1})  # Empty dash fixture falls back to its original.
        loaded_count = len(mixer.loaded)
        for _ in range(8):
            self.assertTrue(manager.play("block_hit_soft", channel_key="block_hit"))
        self.assertEqual(len(mixer.loaded), loaded_count)  # no per-hit processing/loading
        self.assertTrue(all(sound in manager.pitch_variants["block_hit_soft"]
                            for sound in mixer.keyed_channel.played))

    def test_dash_uses_cached_variants_volume_and_replaceable_channel(self):
        import wave

        root = self.make_sound_dir()
        with wave.open(str(root / SOUND_FILES["dash"]), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00\x00" * 220)
        mixer = FakeMixer()
        manager = AudioManager(root, mixer=mixer, master_volume=.5, sfx_volume=.6)
        self.assertEqual(len(manager.pitch_variants["dash"]), 5)
        loaded = len(mixer.loaded)
        for _ in range(2):
            self.assertTrue(manager.play("dash", channel_key="movement"))
        self.assertEqual(len(mixer.loaded), loaded)
        self.assertEqual(mixer.movement_channel.stop_count, 1)
        self.assertAlmostEqual(mixer.movement_channel.volume, .3)
        self.assertTrue(all(sound in manager.pitch_variants["dash"]
                            for sound in mixer.movement_channel.played))

    def test_missing_assets_busy_channels_and_mixer_failure_are_safe(self):
        mixer = FakeMixer()
        with tempfile.TemporaryDirectory() as empty:
            manager = AudioManager(empty, mixer=mixer)
            self.assertFalse(manager.play("jump"))
        manager = AudioManager(self.make_sound_dir(), mixer=mixer)
        mixer.find_channel = Mock(return_value=None)
        self.assertFalse(manager.play("jump"))
        broken_mixer = FakeMixer(fail_init=True)
        manager = AudioManager(self.make_sound_dir(), mixer=broken_mixer)
        self.assertFalse(manager.available)
        self.assertFalse(manager.play("jump"))


if __name__ == "__main__":
    unittest.main()
