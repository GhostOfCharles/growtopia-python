"""Normalize the original four-pose dash sheet without modifying its source.

Run from the project root: python tools/prepare_dash_frames.py
"""

from pathlib import Path

import pygame


ROOT = Path(__file__).resolve().parents[1]


def prepare():
    source = pygame.image.load(str(ROOT / "assets/characters/player/dashing.png"))
    if not source.get_flags() & pygame.SRCALPHA:
        raise ValueError("Dash source needs a transparent background")
    output = pygame.Surface((112, 56), pygame.SRCALPHA)
    if source.get_size() == (112, 56):
        output.blit(source, (0, 0))
    else:
        # The generated source has four disconnected poses rather than uniform
        # 28x56 cells. Extract complete bodies instead of cutting through hair.
        bodies = sorted(pygame.mask.from_surface(source, 16).connected_components(),
                        key=lambda body: body.count(), reverse=True)[:4]
        if len(bodies) != 4 or min(body.count() for body in bodies) < 1000:
            raise ValueError("Expected four separate full-body dash poses")
        bodies.sort(key=lambda body: body.get_bounding_rects()[0].centerx)
        bounds = [body.get_bounding_rects()[0] for body in bodies]
        scale = min(28 / max(rect.width for rect in bounds),
                    56 / max(rect.height for rect in bounds))
        for index, (body, rect) in enumerate(zip(bodies, bounds)):
            frame = source.subsurface(rect).copy()
            keep = body.to_surface(setcolor=(255, 255, 255, 255),
                                   unsetcolor=(0, 0, 0, 0)).subsurface(rect)
            frame.blit(keep, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            frame = pygame.transform.scale(frame, (max(1, round(rect.width * scale)),
                                                   max(1, round(rect.height * scale))))
            output.blit(frame, frame.get_rect(midbottom=(index * 28 + 14, 56)))
    destination = ROOT / "assets/characters/player/animations/dashing.png"
    pygame.image.save(output, str(destination))
    print(f"Saved {destination}: {output.get_size()}, four transparent frames")


if __name__ == "__main__":
    prepare()
