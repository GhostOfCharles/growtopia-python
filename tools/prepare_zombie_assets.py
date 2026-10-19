"""Prepare the supplied opaque zombie sources; originals remain untouched.

Explicit source strips were checked visually (attack cells are not uniform).
Background thresholds are specific to these supplied black/white/checker PNGs.
27px standing art on a 28x56 canvas leaves room for the extended scratch arm.
"""
import json
from pathlib import Path
import pygame

ROOT = Path(__file__).resolve().parents[1]
LAYOUTS = {
    "idle": ("zombie_idle.png", [0, 1254], [600]),
    "walking": ("zombie_walking.png", [0, 1032, 2064, 3096, 4128], [130] * 4),
    "jumping": ("zombie_jump.png", [0, 1440], [100]),
    "falling": ("zombie_falling.png", [0, 1440], [120]),
    "attack": ("zombie_attack.png", [0, 576, 1170, 1840, 2428, 3080, 3584],
               [100, 100, 90, 90, 110, 130]),
}


def prepare():
    destination = ROOT / "assets/characters/zombie"
    destination.mkdir(parents=True, exist_ok=True)
    config = {"animations": {}}
    for state, (filename, edges, durations) in LAYOUTS.items():
        source = pygame.image.load(str(ROOT / "assets/zombie" / filename))
        frames = []
        for left, right in zip(edges, edges[1:]):
            crop = source.subsurface((left, 0, right-left, source.get_height()))
            small = pygame.transform.scale(crop, (crop.get_width()//4, crop.get_height()//4))
            clean = pygame.Surface(small.get_size(), pygame.SRCALPHA)
            for x in range(small.get_width()):
                for y in range(small.get_height()):
                    color = small.get_at((x, y))
                    rgb = color[:3]
                    background = (max(rgb) < 12 if state == "idle" else
                                  max(rgb)-min(rgb) < 20 and min(rgb) > 55)
                    if not background:
                        clean.set_at((x, y), (*rgb, 255))
            bounds = clean.get_bounding_rect()
            if not bounds:
                raise ValueError(f"Empty frame in {filename}")
            # Use the feet, rather than an extended scratch arm, as the anchor.
            feet = clean.subsurface((bounds.x, bounds.y + int(bounds.h*.8),
                                     bounds.w, bounds.h-int(bounds.h*.8)))
            foot_bounds = feet.get_bounding_rect()
            anchor = foot_bounds.centerx
            frames.append((clean.subsurface(bounds).copy(), anchor))
        scale = min(27/max(f.get_height() for f, _ in frames),
                    *(13/max(a, f.get_width()-a, 1) for f, a in frames))
        sheet = pygame.Surface((28*len(frames), 56), pygame.SRCALPHA)
        for index, (frame, anchor) in enumerate(frames):
            size = (max(1, round(frame.get_width()*scale)),
                    max(1, round(frame.get_height()*scale)))
            reduced = pygame.transform.scale(frame, size)
            sheet.blit(reduced, (index*28+14-round(anchor*scale), 56-size[1]))
        pygame.image.save(sheet, str(destination / f"{state}.png"))
        config["animations"][state] = {
            "sheet": f"characters/zombie/{state}.png", "frame_size": [28, 56],
            "count": len(frames), "durations_ms": durations}
    (destination / "animation.json").write_text(json.dumps(config, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    prepare()
