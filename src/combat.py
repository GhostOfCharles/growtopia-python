"""Small geometry helpers shared by player and NPC melee attacks."""
import math


def segment_box_fraction(start, end, rect):
    """First fraction along a segment inside a float hurtbox, or None."""
    lo, hi = 0.0, 1.0
    for origin, destination, minimum, maximum in (
            (start[0], end[0], rect.left, rect.right),
            (start[1], end[1], rect.top, rect.bottom)):
        delta = destination-origin
        if abs(delta) < 1e-9:
            if not minimum <= origin <= maximum:
                return None
        else:
            a, b = (minimum-origin)/delta, (maximum-origin)/delta
            lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
            if lo > hi:
                return None
    return lo


def line_clear(world, start, end, tile_size):
    """Conservative supercover tile traversal, including solid corner contacts."""
    x, y = math.floor(start[0]/tile_size), math.floor(start[1]/tile_size)
    end_x, end_y = math.floor(end[0]/tile_size), math.floor(end[1]/tile_size)
    dx, dy = end[0]-start[0], end[1]-start[1]
    step_x, step_y = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    tx = (((x+(dx > 0))*tile_size-start[0])/dx) if dx else math.inf
    ty = (((y+(dy > 0))*tile_size-start[1])/dy) if dy else math.inf
    dtx = tile_size/abs(dx) if dx else math.inf
    dty = tile_size/abs(dy) if dy else math.inf
    while True:
        if world.is_solid(x, y):
            return False
        if (x, y) == (end_x, end_y):
            return True
        if abs(tx-ty) < 1e-9:
            if world.is_solid(x+step_x, y) or world.is_solid(x, y+step_y):
                return False
            x, y = x+step_x, y+step_y
            tx, ty = tx+dtx, ty+dty
        elif tx < ty:
            x, tx = x+step_x, tx+dtx
        else:
            y, ty = y+step_y, ty+dty
