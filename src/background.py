"""Cached, deterministic pixel-art sky and cloud renderer."""

from dataclasses import dataclass
import math
import random

import pygame


@dataclass(frozen=True)
class BackgroundConfig:
    top_color: tuple = (75, 151, 220)
    bottom_color: tuple = (151, 205, 242)
    cloud_count: int = 6
    min_cloud_speed: float = 3.0
    max_cloud_speed: float = 8.0
    min_parallax: float = 0.05
    max_parallax: float = 0.16
    cloud_alpha: int = 190
    seed: int = 481516


_CLOUD_SHAPES = (
    ("  ####  ", " ###### ", "########", "########", " ###### "),
    ("   ###  ", "  ##### ", " #######", "########", " ###### "),
    ("  ##### ", " #######", "########", "########", "  ##### "),
)
_PIXEL = 4


class BackgroundRenderer:
    """Draw a cached vertical gradient with slowly drifting blocky clouds."""

    def __init__(self, size, config=None):
        self.width, self.height = map(int, size)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("background dimensions must be positive")
        self.config = config or BackgroundConfig()
        self.elapsed_seconds = 0.0
        self._gradient = self._make_gradient()
        self._cloud_images = self._make_cloud_images()
        self.clouds = self._make_clouds()

    def _make_gradient(self):
        surface = pygame.Surface((self.width, self.height))
        top, bottom = self.config.top_color, self.config.bottom_color
        denominator = max(1, self.height - 1)
        for y in range(self.height):
            t = y / denominator
            color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
            pygame.draw.line(surface, color, (0, y), (self.width - 1, y))
        return surface

    def _make_cloud_images(self):
        images = []
        for shape in _CLOUD_SHAPES:
            width, height = len(shape[0]), len(shape)
            image = pygame.Surface((width * _PIXEL, height * _PIXEL), pygame.SRCALPHA)
            for row, line in enumerate(shape):
                for col, cell in enumerate(line):
                    if cell == "#":
                        # A restrained cool tint keeps the cloud legible without
                        # making it look like a smooth, vector-style overlay.
                        shade = 250 if row < 2 else 245
                        pygame.draw.rect(image, (shade, 251, 255, self.config.cloud_alpha),
                                         (col * _PIXEL, row * _PIXEL, _PIXEL, _PIXEL))
            images.extend((pygame.transform.scale(image, (image.get_width() * scale,
                                                           image.get_height() * scale))
                           for scale in (2, 3)))
        return tuple(images)

    def _make_clouds(self):
        rng = random.Random(self.config.seed)
        clouds = []
        for index in range(max(0, int(self.config.cloud_count))):
            image = self._cloud_images[rng.randrange(len(self._cloud_images))]
            clouds.append({
                "image": image,
                "x": rng.uniform(-image.get_width() * 0.5, self.width),
                "y": rng.uniform(self.height * 0.06, self.height * 0.56),
                "speed": rng.uniform(self.config.min_cloud_speed,
                                      self.config.max_cloud_speed),
                "parallax": rng.uniform(self.config.min_parallax,
                                         self.config.max_parallax),
            })
        return clouds

    def update(self, dt_seconds):
        """Advance cloud drift by elapsed seconds; negative time is ignored."""
        dt = max(0.0, float(dt_seconds))
        if not math.isfinite(dt):
            raise ValueError("delta time must be finite")
        self.elapsed_seconds += dt
        for cloud in self.clouds:
            width = cloud["image"].get_width()
            cycle = self.width + width * 2
            cloud["x"] = ((cloud["x"] + cloud["speed"] * dt + width) % cycle) - width

    def cloud_layout(self, camera_x=0.0):
        """Return cloud screen positions, useful for drawing and focused tests."""
        return tuple((cloud["x"] - float(camera_x) * cloud["parallax"],
                      cloud["y"], cloud["image"].get_width(),
                      cloud["image"].get_height()) for cloud in self.clouds)

    def draw(self, surface, camera_x=0.0, camera_y=0.0):
        surface.blit(self._gradient, (0, 0))
        for cloud, (x, y, _width, _height) in zip(self.clouds,
                                                   self.cloud_layout(camera_x)):
            surface.blit(cloud["image"], (round(x), round(y - camera_y * cloud["parallax"])))
