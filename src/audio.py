"""Small cached sound-effect manager with graceful mixer fallback."""

from io import BytesIO
from pathlib import Path
import random
import wave

import pygame


SOUND_FILES = {
    "block_hard": "broken_block_hard.wav",
    "block_soft": "broken_block_soft.wav",
    "block_hit_hard": "breaking-block-hard.wav",
    "block_hit_soft": "breaking-block-soft.wav",
    "block_placed": "block-placed.wav",
    "death": "death_sound.wav",
    "ground_impact": "ground_impact.wav",
    "enter_world": "enter_world.wav",
    "equip": "equip.wav",
    "item_drop": "item_drop.wav",
    "jump": "jump.wav",
    "dash": "dash_sound.wav",
    "leave_world": "leave_world.wav",
    "hotbar_select": "select-item-hotbar.wav",
    "burn": "burn.wav",
    "cant_place": "cant_place_tile.wav",
}

PITCH_VARIATION_SOUNDS = frozenset({
    "block_hit_soft", "block_hit_hard", "block_soft", "block_hard",
    "block_placed", "dash",
})
PITCH_VARIATION_SEMITONES = 0.4
PITCH_VARIANT_STEPS = 5
PICKUP_PITCH_SEMITONES = 2.0


class NullAudioManager:
    """No-op adapter for scenes constructed without a game audio service."""

    def play(self, _name, cooldown_ms=0, channel_key=None, volume=1.0, pitch="normal"):
        return False

    def update(self, _dt_ms):
        pass


NULL_AUDIO = NullAudioManager()


class AudioManager:
    """Load sound assets once and play them through a bounded channel pool."""

    def __init__(self, sound_dir="assets/sounds", master_volume=0.8,
                 sfx_volume=0.8, max_channels=12, mixer=None, rng=None):
        self.sound_dir = Path(sound_dir)
        self.mixer = mixer if mixer is not None else pygame.mixer
        self.master_volume = self._clamp_volume(master_volume)
        self.sfx_volume = self._clamp_volume(sfx_volume)
        self.sounds = {}
        self.pitch_variants = {}
        self.rng = rng or random.Random()
        self.cooldowns_ms = {}
        self.keyed_channels = {}
        self._active_keys = set()
        self.available = False
        try:
            if not self.mixer.get_init():
                self.mixer.init()
            self.max_channels = max(1, int(max_channels))
            self.mixer.set_num_channels(self.max_channels)
            # Reserve one channel for replaceable repeated feedback such as
            # block-hit sounds; ordinary effects cannot steal it mid-play.
            if self.max_channels > 1 and hasattr(self.mixer, "set_reserved") and hasattr(self.mixer, "Channel"):
                reserved = 2 if self.max_channels > 2 else 1
                self.mixer.set_reserved(reserved)
                self.keyed_channels["block_hit"] = self.mixer.Channel(0)
                if self.max_channels > 2:
                    self.keyed_channels["movement"] = self.mixer.Channel(1)
            self.available = True
        except Exception:
            # Machines without an audio device still run the game normally.
            return

        files = {}
        try:
            files = {path.name.casefold(): path for path in self.sound_dir.iterdir()
                     if path.is_file()}
        except OSError:
            pass
        for name, expected in SOUND_FILES.items():
            path = files.get(expected.casefold())
            if path is None:
                continue
            try:
                self.sounds[name] = self.mixer.Sound(str(path))
                if name in PITCH_VARIATION_SOUNDS:
                    self.pitch_variants[name] = self._load_pitch_variants(path, self.sounds[name])
                elif name == "item_drop":
                    high = self._load_pitch_variant(path, PICKUP_PITCH_SEMITONES)
                    if high is not None:
                        self.pitch_variants["item_drop_high"] = (high,)
            except Exception:
                # One bad/missing WAV must not prevent other effects or gameplay.
                continue

    def _load_pitch_variants(self, path, original):
        """Build and cache small WAV-rate variants once, falling back to original."""
        variants = [original]
        try:
            with wave.open(str(path), "rb") as source:
                params = source.getparams()
                if params.comptype != "NONE":
                    return tuple(variants)
                frames = source.readframes(params.nframes)
            # The slight rate changes shift pitch and duration together, as in
            # natural variation from differently struck block sounds.
            span = PITCH_VARIATION_SEMITONES
            half = PITCH_VARIANT_STEPS // 2
            for index in range(-half, half + 1):
                if index == 0:
                    continue
                semitones = span * index / half
                rate = max(1, round(params.framerate * (2 ** (semitones / 12))))
                output = BytesIO()
                with wave.open(output, "wb") as target:
                    target.setnchannels(params.nchannels)
                    target.setsampwidth(params.sampwidth)
                    target.setframerate(rate)
                    target.writeframes(frames)
                variants.append(self.mixer.Sound(file=BytesIO(output.getvalue())))
        except Exception:
            # Unsupported/corrupt WAVs still retain their original sound.
            return tuple([original])
        return tuple(variants)

    def _load_pitch_variant(self, path, semitones):
        """Load one cached rate-shifted copy of a PCM WAV."""
        try:
            with wave.open(str(path), "rb") as source:
                params = source.getparams()
                if params.comptype != "NONE":
                    return None
                frames = source.readframes(params.nframes)
            output = BytesIO()
            with wave.open(output, "wb") as target:
                target.setnchannels(params.nchannels)
                target.setsampwidth(params.sampwidth)
                target.setframerate(max(1, round(
                    params.framerate * (2 ** (semitones / 12)))))
                target.writeframes(frames)
            return self.mixer.Sound(file=BytesIO(output.getvalue()))
        except Exception:
            return None

    @staticmethod
    def _clamp_volume(value):
        return max(0.0, min(1.0, float(value)))

    def set_volumes(self, master=None, sfx=None):
        if master is not None:
            self.master_volume = self._clamp_volume(master)
        if sfx is not None:
            self.sfx_volume = self._clamp_volume(sfx)

    def update(self, dt_ms):
        elapsed = max(0.0, float(dt_ms))
        for name in tuple(self.cooldowns_ms):
            remaining = self.cooldowns_ms[name] - elapsed
            if remaining <= 0:
                del self.cooldowns_ms[name]
            else:
                self.cooldowns_ms[name] = remaining

    def play(self, name, cooldown_ms=0, channel_key=None, volume=1.0, pitch="normal"):
        """Play an effect if loaded, a channel is free, and its cooldown expired."""
        sound = self.sounds.get(name)
        variants = self.pitch_variants.get(name)
        if variants:
            sound = self.rng.choice(variants)
        if pitch == "high":
            high_variants = self.pitch_variants.get(f"{name}_high")
            if high_variants:
                sound = self.rng.choice(high_variants)
        if not self.available or sound is None or self.cooldowns_ms.get(name, 0) > 0:
            return False
        try:
            channel = self.keyed_channels.get(channel_key) if channel_key else None
            if channel is not None:
                if channel_key in self._active_keys:
                    channel.stop()
            else:
                channel = self.mixer.find_channel(False)
            if channel is None:
                return False
            channel.set_volume(self.master_volume * self.sfx_volume * self._clamp_volume(volume))
            channel.play(sound)
        except Exception:
            return False
        if cooldown_ms > 0:
            self.cooldowns_ms[name] = float(cooldown_ms)
        if channel_key and channel_key in self.keyed_channels:
            self._active_keys.add(channel_key)
        return True
