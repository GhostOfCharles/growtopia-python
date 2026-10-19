"""Original procedural block feedback; visual randomness never affects loot."""

from dataclasses import dataclass
import math
import random

import pygame


@dataclass
class ImpactParticle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    lifetime_ms: float
    color: tuple
    gravity: float = 0.0
    age_ms: float = 0.0
    ground_y: float | None = None
    puff: bool = False

    def update(self, dt):
        seconds = dt / 1000.0
        self.x += self.vx * seconds
        self.y += self.vy * seconds + 0.5 * self.gravity * seconds * seconds
        self.vy += self.gravity * seconds
        if self.ground_y is not None and self.y > self.ground_y - self.size / 2:
            self.y = self.ground_y - self.size / 2
            self.vy = self.gravity = 0.0
        self.age_ms += dt


@dataclass
class DashShockwave:
    x: float
    y: float
    direction: int
    lifetime_ms: float
    age_ms: float = 0.0


class BlockEffects:
    """Small world-space puffs and chips for accepted hit/break/place actions.

    Sizes, counts and lifetimes are original presentation choices, not measured
    Growtopia timings. The bounded pool has no collision or gameplay side effects.
    """

    MAX_PARTICLES = 192
    DASH_WAVE_LIFETIME_MS = 260.0
    DASH_WAVE_FRAMES = 20
    DASH_WAVE_MAX_COUNT = 8
    DASH_WAVE_COLOR = (224, 245, 255)
    LANDING_DUST_THRESHOLD_TILES = 5.0
    LANDING_DUST_BASE_COUNT = 10
    LANDING_DUST_MAX_COUNT = 16
    LANDING_DUST_LIFETIME_MS = (230.0, 360.0)
    HEAVY_DUST_BASE_COUNT = 48
    HEAVY_DUST_MAX_COUNT = 72
    HEAVY_DUST_LIFETIME_MS = (520.0, 780.0)

    LANDING_DUST_PALETTES = {
        "dirt": ((112, 70, 39), (145, 96, 55), (176, 125, 76)),
        "grass": ((105, 143, 73), (151, 174, 104), (190, 199, 137)),
        "stone": ((105, 108, 116), (143, 145, 150), (177, 178, 177)),
        "bedrock": ((65, 65, 73), (95, 93, 98), (125, 121, 119)),
    }

    def __init__(self, landing_threshold_tiles=LANDING_DUST_THRESHOLD_TILES):
        self.particles = []
        self._rng = random.Random()
        self._layer = None
        self.landing_threshold_tiles = float(landing_threshold_tiles)
        self.shockwaves = []
        self._dash_frames = None

    def emit_dash(self, origin, direction):
        """A fixed world-space pressure ring; cached frames keep drawing cheap."""
        if self._dash_frames is None:
            self._dash_frames = self._make_dash_frames()
        self.shockwaves.append(DashShockwave(
            *origin, 1 if direction >= 0 else -1, self.DASH_WAVE_LIFETIME_MS))
        del self.shockwaves[:-self.DASH_WAVE_MAX_COUNT]

    def _make_dash_frames(self):
        right_frames = []
        for index in range(self.DASH_WAVE_FRAMES):
            t = index / (self.DASH_WAVE_FRAMES - 1)
            # Draw on a small pixel grid, then enlarge without smoothing.
            image = pygame.Surface((40, 40), pygame.SRCALPHA)
            radius = 3 + 12 * (1 - (1 - t) ** 2)
            alpha = round(205 * (1 - t) ** 1.3)
            color = (*self.DASH_WAVE_COLOR, alpha)
            for start, stop in ((10, 100), (130, 220), (250, 340)):
                points = []
                for angle in range(start, stop + 1, 6):
                    radians = math.radians(angle + 10 * t)
                    points.append((round(20 + math.cos(radians) * radius),
                                   round(20 + math.sin(radians) * radius)))
                pygame.draw.lines(image, color, False, points, 1)
            for offset, shift in ((-7, 0), (0, 3), (7, -2)):
                head = round(23 + 12 * t + shift)
                tail = head - round(4 + 3 * (1 - t))
                pygame.draw.line(image, (*self.DASH_WAVE_COLOR, round(alpha * .65)),
                                 (tail, 20 + offset), (head, 20 + offset))
            right_frames.append(pygame.transform.scale(image, (80, 80)))
        return {1: tuple(right_frames),
                -1: tuple(pygame.transform.flip(frame, True, False)
                          for frame in right_frames)}

    def emit(self, center, material_color, kind="hit"):
        rng = self._rng
        puff_count = {"hit": 5, "break": 9, "place": 6}[kind]
        chip_count = 7 if kind == "break" else 3
        for i in range(puff_count + chip_count):
            angle = rng.uniform(0.0, math.tau)
            puff = i < puff_count
            speed = rng.uniform(50.0, 100.0) if puff else rng.uniform(55.0, 110.0)
            self.particles.append(ImpactParticle(
                center[0] + rng.uniform(-10.0, 10.0),
                center[1] + rng.uniform(-10.0, 10.0),
                math.cos(angle) * speed,
                math.sin(angle) * speed - (12.0 if puff else 32.0),
                rng.uniform(7.0, 12.0) if puff else rng.uniform(2.0, 4.0),
                rng.uniform(120.0, 230.0) if puff else rng.uniform(180.0, 320.0),
                (245, 249, 255) if puff else material_color,
                0.0 if puff else 240.0,
            ))
        del self.particles[:-self.MAX_PARTICLES]

    def emit_landing(self, center, material="dirt", fall_distance_tiles=0.0):
        """Emit a brief world-space dust burst for a sufficiently hard landing.

        ``center`` is the point on the tile surface between the player's feet.
        Returns whether an effect was emitted, which also makes the threshold
        behavior straightforward to verify without coupling it to physics.
        """
        if fall_distance_tiles < self.landing_threshold_tiles:
            return False

        rng = self._rng
        palette = self.LANDING_DUST_PALETTES.get(
            material, self.LANDING_DUST_PALETTES["dirt"])
        extra = int(max(0.0, fall_distance_tiles - self.landing_threshold_tiles))
        count = min(self.LANDING_DUST_MAX_COUNT,
                    self.LANDING_DUST_BASE_COUNT + extra)

        # Paired outward flecks create a low, grounded impact while a few
        # slower center particles provide the small upward puff.
        for index in range(count):
            direction = -1 if index % 2 == 0 else 1
            puff = index < 3
            self.particles.append(ImpactParticle(
                center[0] + (rng.uniform(-3.0, 3.0) if puff else
                             direction * rng.uniform(2.0, 11.0)),
                center[1] - rng.uniform(1.0, 4.0),
                rng.uniform(-10.0, 10.0) if puff else
                    direction * rng.uniform(24.0, 66.0),
                -rng.uniform(26.0, 48.0) if puff else -rng.uniform(13.0, 34.0),
                rng.uniform(3.0, 5.0) if puff else rng.uniform(2.0, 4.0),
                rng.uniform(*self.LANDING_DUST_LIFETIME_MS),
                rng.choice(palette),
                rng.uniform(80.0, 145.0),
            ))
        del self.particles[:-self.MAX_PARTICLES]
        return True

    def emit_heavy_landing(self, center, material="dirt", fall_distance_tiles=11.0):
        """Dense outward dust fronts, rising puffs and small ground fragments."""
        rng = self._rng
        palette = self.LANDING_DUST_PALETTES.get(material, self.LANDING_DUST_PALETTES["dirt"])
        count = min(self.HEAVY_DUST_MAX_COUNT, self.HEAVY_DUST_BASE_COUNT +
                    int(max(0, fall_distance_tiles - 10) * 2))
        for index in range(count):
            direction = -1 if index % 2 == 0 else 1
            front = index < count // 3
            puff = index < count * .75
            size = rng.uniform(12, 24) if puff else rng.uniform(2, 5)
            speed = rng.uniform(210, 310) if front else rng.uniform(65, 190)
            self.particles.append(ImpactParticle(
                center[0] + direction * rng.uniform(0, 12),
                center[1] - size / 2 - rng.uniform(0, 5),
                direction * speed,
                -rng.uniform(8, 23) if front else -rng.uniform(28, 80),
                size, rng.uniform(*self.HEAVY_DUST_LIFETIME_MS),
                rng.choice(palette), 65.0 if puff else 210.0,
                ground_y=center[1], puff=puff,
            ))
        del self.particles[:-self.MAX_PARTICLES]

    def update(self, dt):
        for wave in self.shockwaves:
            wave.age_ms += max(0.0, dt)
        self.shockwaves = [wave for wave in self.shockwaves
                           if wave.age_ms < wave.lifetime_ms]
        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.age_ms < p.lifetime_ms]

    def draw(self, surface, cam_x, cam_y):
        for wave in self.shockwaves:
            index = min(self.DASH_WAVE_FRAMES - 1,
                        int(wave.age_ms / wave.lifetime_ms * self.DASH_WAVE_FRAMES))
            frame = self._dash_frames[wave.direction][index]
            surface.blit(frame, frame.get_rect(center=(round(wave.x - cam_x),
                                                        round(wave.y - cam_y))))
        if not self.particles:
            return

        # Punch particles occupy a small area around their block. Keep the
        # alpha-compositing buffer local instead of clearing and blitting a
        # full-window surface on every frame that an impact is visible.
        visible = []
        bounds = None
        clip_rect = surface.get_rect()
        for particle in self.particles:
            remaining = max(0.0, 1.0 - particle.age_ms / particle.lifetime_ms)
            size = max(1, round(particle.size * (0.5 + 0.5 * remaining)))
            rect = pygame.Rect(0, 0, size, size)
            rect.center = (round(particle.x - cam_x), round(particle.y - cam_y))
            rect = rect.clip(clip_rect)
            if not rect:
                continue
            visible.append((particle, remaining, rect))
            bounds = rect.copy() if bounds is None else bounds.union(rect)

        if bounds is None:
            return
        if self._layer is None or self._layer.get_size() != bounds.size:
            self._layer = pygame.Surface(bounds.size, pygame.SRCALPHA)
        self._layer.fill((0, 0, 0, 0))
        for particle, remaining, screen_rect in visible:
            local_rect = screen_rect.move(-bounds.x, -bounds.y)
            color = (*particle.color, round(255 * remaining))
            if particle.puff and local_rect.width >= 5:
                x, y, w, h = local_rect
                cut = max(1, min(w, h) // 4)
                pygame.draw.polygon(self._layer, color,
                    ((x + cut, y), (x + w - cut, y), (x + w, y + cut),
                     (x + w, y + h - cut), (x + w - cut, y + h),
                     (x + cut, y + h), (x, y + h - cut), (x, y + cut)))
            else:
                pygame.draw.rect(self._layer, color, local_rect)
        surface.blit(self._layer, bounds.topleft)


class PunchStretchEffect:
    """Cached pixel-art arm frames stretched from the punch origin to its target."""

    def __init__(self, asset_manager, path="effects/punch-stretch.png",
                 frame_size=(543, 724), frame_count=4, height=18):
        if height <= 0:
            raise ValueError("Punch effect height must be positive")
        self.height = int(height)
        self.frames = []
        for frame in asset_manager.load_frames(path, frame_size=frame_size, count=frame_count):
            bounds = frame.get_bounding_rect(min_alpha=16)
            self.frames.append(frame.subsurface(bounds).copy() if bounds.width and bounds.height else None)
        self._scaled = {}

    def draw(self, surface, origin, target, progress):
        if not self.frames:
            return None
        index = min(len(self.frames) - 1, max(0, int(progress * len(self.frames))))
        frame = self.frames[index]
        if frame is None:
            return None

        dx, dy = target[0] - origin[0], target[1] - origin[1]
        distance = math.hypot(dx, dy)
        height = self.height
        natural_width = round(frame.get_width() * height / frame.get_height())
        width = max(natural_width, round(distance))
        key = index, width, height
        if key not in self._scaled:
            self._scaled[key] = pygame.transform.scale(frame, (width, height))
        image = self._scaled[key]

        right_facing = dx >= 0
        if not right_facing:
            image = pygame.transform.flip(image, True, False)
        desired_angle = math.atan2(dy, dx) if distance else (0.0 if right_facing else math.pi)
        base_angle = 0.0 if right_facing else math.pi
        rotation = round(math.degrees(base_angle - desired_angle))
        if rotation:
            image = pygame.transform.rotate(image, rotation)

        # Rotate around the wrist, keeping that edge fixed at the player's origin.
        anchor_x = 0.0 if right_facing else float(width)
        offset_x = anchor_x - width / 2
        radians = math.radians(rotation)
        rotated_x = math.cos(radians) * offset_x
        rotated_y = -math.sin(radians) * offset_x
        rect = image.get_rect(center=(round(origin[0] - rotated_x),
                                     round(origin[1] - rotated_y)))
        surface.blit(image, rect)
        return rect


def draw_fist_icon(surface, center, size, color=(245, 245, 245)):
    """A small original drawn fist, independent of system emoji fonts."""
    palm = pygame.Rect(0, 0, size, max(6, round(size * 0.72)))
    palm.center = (round(center[0]), round(center[1]))
    outline = (20, 20, 30)
    pygame.draw.rect(surface, color, palm, border_radius=3)
    pygame.draw.rect(surface, outline, palm, width=2, border_radius=3)
    for fraction in (0.3, 0.5, 0.7):
        x = palm.left + round(palm.width * fraction)
        pygame.draw.line(surface, outline, (x, palm.top + 2), (x, palm.top + palm.height // 3))
    thumb = pygame.Rect(palm.left + 2, palm.centery, max(4, size // 3), max(4, size // 3))
    pygame.draw.rect(surface, color, thumb, border_radius=2)
    pygame.draw.line(surface, outline, thumb.topleft, thumb.topright)
