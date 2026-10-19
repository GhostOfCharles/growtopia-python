"""Separate the six overlapping poses in the original player sprint sheet.

Run from the project root with ``python tools/prepare_sprint_frames.py`` after
replacing the source sheet. The source PNG is kept unchanged.
"""

from pathlib import Path

import pygame


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/characters/player/player_sprinting.png"
OUTPUT = ROOT / "assets/characters/player/animations/sprinting"
FRAME_WIDTH = 400
FRAME_COUNT = 6


def prepare(source=SOURCE, output=OUTPUT):
    sheet = pygame.image.load(str(source))
    components = pygame.mask.from_surface(sheet, threshold=1).connected_components()
    bodies = sorted(components, key=lambda part: part.count(), reverse=True)[:FRAME_COUNT]
    if len(bodies) != FRAME_COUNT or bodies[-1].count() < 1000:
        raise ValueError("The sprint sheet does not contain six separate full-body poses")
    bodies.sort(key=lambda part: part.get_bounding_rects()[0].centerx)
    body_ids = {id(part) for part in bodies}
    bounds = [part.get_bounding_rects()[0] for part in bodies]
    if any(rect.width > FRAME_WIDTH for rect in bounds):
        raise ValueError("A sprint pose is wider than the output frame")

    output.mkdir(parents=True, exist_ok=True)
    for index, (body, rect) in enumerate(zip(bodies, bounds)):
        keep = pygame.Mask(sheet.get_size())
        keep.draw(body, (0, 0))
        nearby = rect.inflate(12, 12)
        for part in components:
            if id(part) in body_ids:
                continue
            part_rect = part.get_bounding_rects()[0]
            closest = min(range(FRAME_COUNT),
                          key=lambda i: abs(part_rect.centerx - bounds[i].centerx))
            if closest == index and nearby.colliderect(part_rect):
                keep.draw(part, (0, 0))

        white_mask = keep.to_surface(setcolor=(255, 255, 255, 255),
                                     unsetcolor=(0, 0, 0, 0))
        isolated = sheet.copy()
        isolated.blit(white_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        frame = pygame.Surface((FRAME_WIDTH, sheet.get_height()), pygame.SRCALPHA)
        frame.blit(isolated, (FRAME_WIDTH // 2 - rect.centerx, 0))
        pygame.image.save(frame, str(output / f"frame-{index}.png"))


if __name__ == "__main__":
    prepare()
