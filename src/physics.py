"""Float-based tile collision and character motion shared by players and NPCs.

The world only needs an ``is_solid(column, row)`` query. Movement resolves
one axis at a time and checks every crossed tile boundary, so a long frame
cannot skip a thin wall or the first floor along the movement path.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterPhysics:
    tile_size: int
    width: int
    height: int
    step_ms: float
    gravity: float
    jump_velocity: float
    max_fall: float
    world_width: float


def integrate_character(body, dt, settings, *, vertical_velocity=None):
    """Shared player/NPC gravity and swept movement; input stays with callers."""
    f = dt / settings.step_ms
    body.vy = (min(settings.max_fall, body.vy + settings.gravity * f)
               if vertical_velocity is None else vertical_velocity)
    dx = body.vx * f
    if dx:
        body.x, hit = sweep_axis(body.world, body.x, body.y, settings.width,
                                 settings.height, dx, 0, settings.tile_size)
        if hit:
            body.vx = 0.0
    body.on_ground = False
    dy = body.vy * f
    if dy:
        body.y, hit = sweep_axis(body.world, body.x, body.y, settings.width,
                                 settings.height, dy, 1, settings.tile_size)
        if hit:
            body.on_ground = dy > 0
            body.vy = 0.0
    elif overlaps_solid(body.world, body.x, body.y+1, settings.width,
                        settings.height, settings.tile_size):
        body.on_ground = True
    body.x = max(0.0, min(settings.world_width-settings.width, body.x))


def damage_character(body, amount, flash_ms):
    body.hp = max(0.0, body.hp-amount)
    body.time_since_damage_ms = 0.0
    if amount > 0:
        body.flash_ms = max(body.flash_ms, flash_ms)


def knockback_character(body, source_x, width, horizontal, vertical, lock_ms,
                        invulnerability_ms):
    center = body.x + width/2
    direction = (1 if center > source_x else -1 if center < source_x
                 else -body.facing)
    body.vx = direction * horizontal
    body.vy = vertical
    body.on_ground = False
    body.knockback_ms = lock_ms
    body.invuln_ms = invulnerability_ms


def _occupied_cells(start, size, tile_size):
    """Return cells touched by a half-open interval, excluding its far edge."""
    return range(math.floor(start / tile_size),
                 math.ceil((start + size) / tile_size))


def overlaps_solid(world, x, y, width, height, tile_size):
    return any(world.is_solid(column, row)
               for row in _occupied_cells(y, height, tile_size)
               for column in _occupied_cells(x, width, tile_size))


def sweep_axis(world, x, y, width, height, delta, axis, tile_size):
    """Return (resolved coordinate, hit) for an axis (0=x, 1=y).

    Contact at the endpoint counts as a hit. The perpendicular interval is
    half-open, allowing an entity to slide along adjacent tiles without
    treating a shared edge as penetration. Existing overlap is not a spawn
    recovery policy; callers should place entities in unobstructed space.
    """
    if axis not in (0, 1):
        raise ValueError("axis must be 0 (horizontal) or 1 (vertical)")
    position, size = (x, width) if axis == 0 else (y, height)
    if delta == 0:
        return position, False
    perpendicular = _occupied_cells(y, height, tile_size) if axis == 0 else \
        _occupied_cells(x, width, tile_size)
    leading = position + size if delta > 0 else position
    destination = leading + delta
    if delta > 0:
        cells = range(math.floor(leading / tile_size),
                      math.floor(destination / tile_size) + 1)
    else:
        cells = range(math.ceil(leading / tile_size) - 1,
                      math.ceil(destination / tile_size) - 2, -1)
    for cell in cells:
        for other in perpendicular:
            column, row = (cell, other) if axis == 0 else (other, cell)
            if world.is_solid(column, row):
                boundary = cell * tile_size - size if delta > 0 else \
                    (cell + 1) * tile_size
                return float(boundary), True
    return position + delta, False
