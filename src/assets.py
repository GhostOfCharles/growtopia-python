"""Small cached PNG and sprite-sheet loader for pixel art assets."""

import json
from pathlib import Path

import pygame


class AssetManager:
    def __init__(self, asset_root="assets"):
        self.asset_root = Path(asset_root).resolve()
        self._images = {}
        self._scaled = {}

    def _path(self, path):
        path = Path(path)
        return path.resolve() if path.is_absolute() else (self.asset_root / path).resolve()

    def load_png(self, path):
        """Load a transparent PNG once and return its cached Surface."""
        resolved = self._path(path)
        if resolved not in self._images:
            image = pygame.image.load(str(resolved))
            self._images[resolved] = image.convert_alpha() if pygame.display.get_surface() else image.copy()
        return self._images[resolved]

    def scaled(self, path, size):
        """Return a nearest-neighbor scaled image, cached by path and size."""
        resolved = self._path(path)
        size = tuple(map(int, size))
        if min(size) <= 0:
            raise ValueError("Scaled image dimensions must be positive")
        key = resolved, size
        if key not in self._scaled:
            image = self.load_png(resolved)
            self._scaled[key] = pygame.transform.scale(image, size)
        return self._scaled[key]

    def load_frames(self, path, *, frame_size=None, count=None):
        """Load individual PNGs from a list, or slice a uniform sheet row-major."""
        if isinstance(path, (list, tuple)):
            return tuple(self.load_png(item) for item in path)
        sheet = self.load_png(path)
        if frame_size is None:
            return (sheet,)
        frame_width, frame_height = map(int, frame_size)
        if min(frame_width, frame_height) <= 0:
            raise ValueError("Frame dimensions must be positive")
        columns, rows = sheet.get_width() // frame_width, sheet.get_height() // frame_height
        if columns * frame_width != sheet.get_width() or rows * frame_height != sheet.get_height():
            raise ValueError(f"Sheet dimensions are not divisible by frame size: {path}")
        available = columns * rows
        if count is None:
            count = available
        if not 0 < count <= available:
            raise ValueError(f"Frame count must be between 1 and {available}")
        return tuple(sheet.subsurface((index % columns * frame_width,
                                      index // columns * frame_height,
                                      frame_width, frame_height)).copy()
                     for index in range(count))

    def load_clip(self, config):
        """Load a clip config with either `frames` PNG paths or a `sheet`."""
        try:
            if "frames" in config:
                frames = self.load_frames(config["frames"])
            elif "sheet" in config:
                frames = self.load_frames(config["sheet"], frame_size=config.get("frame_size"),
                                          count=config.get("count"))
            else:
                frames = ()
        except FileNotFoundError:
            return ()
        if frames and "durations_ms" in config and len(config["durations_ms"]) != len(frames):
            raise ValueError("Clip duration count must match frame count")
        return frames

    def load_animation_config(self, path):
        """Read a character JSON config and return clips plus timing overrides."""
        config_path = self._path(path)
        with config_path.open(encoding="utf-8") as source:
            config = json.load(source)
        clips = {}
        durations = {}
        for state, entry in config.get("animations", {}).items():
            if "durations_ms" in entry:
                durations[state] = tuple(entry["durations_ms"])
            clips[state] = {"frames": self.load_clip(entry),
                            "durations_ms": entry.get("durations_ms", ()),
                            "preserve_canvas": entry.get("preserve_canvas", False),
                            "render_scale": entry.get("render_scale", 1.0)}
        return clips, durations
