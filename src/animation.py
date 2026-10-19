"""Original temporary player poses; presentation never changes physics state."""

import math

import pygame


# Original temporary timings, not measured reference animation rates.
FRAME_DURATIONS_MS = {
    "idle": (600, 600),
    "walking": (90, 90, 90, 90),
    "sprinting": (1000/14,) * 6,
    "jumping": (100, 100),
    "falling": (120, 120),
    "dashing": (80,) * 4,
    "heavy_landing": (1000 / 6,) * 6,
}

# The world tiles are 32 px tall; render character art about two tiles high.
PLAYER_ART_HEIGHT = 64


class PlayerAnimation:
    def __init__(self, frame_durations=None, sprite_clips=None,
                 sprite_height=PLAYER_ART_HEIGHT, preserve_canvas=False):
        if not math.isfinite(sprite_height) or sprite_height <= 0:
            raise ValueError("Sprite height must be positive and finite")
        self.sprite_height = float(sprite_height)
        self.preserve_canvas = preserve_canvas
        self.frame_durations = dict(FRAME_DURATIONS_MS)
        if frame_durations:
            self.frame_durations.update(frame_durations)
        self.sprite_clips = {}
        self._preserve_canvas_states = set()
        self._render_scales = {}
        for state, clip in (sprite_clips or {}).items():
            if state == "punch":
                frames = tuple(clip.get("frames", ()))
                if frames:
                    self.sprite_clips[state] = frames
                continue
            frames = tuple(clip.get("frames", ()))
            if not frames:
                continue
            if clip.get("preserve_canvas", False):
                self._preserve_canvas_states.add(state)
            render_scale = float(clip.get("render_scale", 1.0))
            if not math.isfinite(render_scale) or render_scale <= 0:
                raise ValueError(f"Invalid render scale for {state}")
            self._render_scales[state] = render_scale
            durations = tuple(clip.get("durations_ms", self.frame_durations.get(state, (100,) * len(frames))))
            if len(durations) != len(frames):
                raise ValueError(f"Frame and duration counts differ for {state}")
            self.frame_durations[state] = durations
            self.sprite_clips[state] = frames
        for state, durations in self.frame_durations.items():
            if not durations or any(not math.isfinite(d) or d <= 0 for d in durations):
                raise ValueError(f"Invalid frame durations for {state}")
            self.frame_durations[state] = tuple(durations)
        # Frames from the same source canvas share a crop. Cropping each pose
        # independently enlarges crouches and makes the sprite jump sideways.
        self._clip_bounds = {}
        grouped = {}
        for state, frames in self.sprite_clips.items():
            if self.preserve_canvas or state in self._preserve_canvas_states:
                continue
            if len({frame.get_size() for frame in frames}) != 1:
                continue
            grouped.setdefault(frames[0].get_size(), []).append(state)
        for states in grouped.values():
            bounds = None
            for state in states:
                for frame in self.sprite_clips[state]:
                    frame_bounds = frame.get_bounding_rect(min_alpha=16)
                    if frame_bounds.width and frame_bounds.height:
                        bounds = frame_bounds if bounds is None else bounds.union(frame_bounds)
            if bounds is not None:
                for state in states:
                    self._clip_bounds[state] = bounds
        self.state = "idle"
        self.elapsed_ms = 0.0
        self._trimmed_frames = {}
        self._cropped_frames = {}
        self._scaled_frames = {}
        self._flash_masks = {}
        self._flash_tinted_frames = {}

    def update(self, dt, *, grounded, vx, vy, sprinting=False, dashing=False,
               heavy_landing=False, recovery_elapsed_ms=None):
        state = (("sprinting" if sprinting else "walking")
                 if abs(vx) > 1e-6 else "idle") if grounded else (
            "jumping" if vy < 0 else "falling")
        if dashing:
            state = "dashing"
        if heavy_landing:
            state = "heavy_landing"
        if state != self.state:
            self.state = state
            self.elapsed_ms = 0.0
        self.elapsed_ms += max(0.0, dt)
        if heavy_landing and recovery_elapsed_ms is not None:
            self.elapsed_ms = max(0.0, recovery_elapsed_ms)

    @property
    def frame(self):
        durations = self.frame_durations[self.state]
        elapsed = self.elapsed_ms + 1e-8
        if self.state in ("jumping", "heavy_landing"):
            elapsed = min(elapsed, sum(durations) - 1e-8)
        else:
            elapsed %= sum(durations)
        for index, duration in enumerate(durations):
            if elapsed < duration:
                return index
            elapsed -= duration
        return len(durations) - 1

    def draw(self, surface, x, y, width, height, facing, head, body, outline,
             punch_progress=None, flash_ratio=0.0, full_body_state=None,
             full_body_elapsed_ms=0.0):
        """Draw the active pose, anchored to the collider's bottom center."""
        action = self.sprite_clips.get(full_body_state)
        if action:
            durations = self.frame_durations[full_body_state]
            elapsed = min(max(0, full_body_elapsed_ms), sum(durations)-1e-8)
            index = 0
            while elapsed >= durations[index] and index < len(action)-1:
                elapsed -= durations[index]
                index += 1
            self._draw_sprite(surface, action[index], x, y, width, height,
                              facing, flash_ratio,
                              preserve_canvas=(self.preserve_canvas or full_body_state in self._preserve_canvas_states),
                              crop_bounds=self._clip_bounds.get(full_body_state),
                              render_scale=self._render_scales.get(full_body_state, 1.0))
            return
        frame = self.frame
        punch_frames = self.sprite_clips.get("punch")
        if punch_progress is not None and punch_frames and self.state not in ("dashing", "heavy_landing"):
            punch_index = min(len(punch_frames) - 1, int(punch_progress * len(punch_frames)))
            self._draw_sprite(surface, punch_frames[punch_index], x, y, width, height,
                              facing, flash_ratio, crop_bounds=self._clip_bounds.get("punch"))
            return
        clip = self.sprite_clips.get(self.state)
        if clip:
            image = clip[frame % len(clip)]
            self._draw_sprite(surface, image, x, y, width, height, facing, flash_ratio,
                              preserve_canvas=(self.preserve_canvas or self.state in self._preserve_canvas_states),
                              crop_bounds=self._clip_bounds.get(self.state),
                              render_scale=self._render_scales.get(self.state, 1.0))
            return
        bob, stride, lift, arm_raise = 0, 0, 0, 0
        if self.state == "idle":
            bob = frame % 2
        elif self.state in ("walking", "sprinting"):
            stride_scale = 1.5 if self.state == "sprinting" else 1.0
            stride = round((-4, 0, 4, 0)[frame % 4] * stride_scale)
            bob = frame % 2
        elif self.state == "jumping":
            lift, stride, arm_raise = 5 + frame % 2, 3, -3
        elif self.state == "dashing":
            lift, stride, arm_raise = 3, 4, -10
        else:
            stride, arm_raise = 2 + frame % 2, -7
        punching = punch_progress is not None
        lean = round(2 * math.sin(math.pi * punch_progress)) if punching else 0
        visual_scale = self.sprite_height / height
        cx = x + width / 2
        visual_top = y + height - self.sprite_height
        scale_x = width * visual_scale / 28
        scale_y = self.sprite_height / 56

        def point(dx, dy):
            return (round(cx + dx * facing * scale_x),
                    round(visual_top + dy * scale_y))

        def limb(start, end, color, thickness=6):
            thickness = max(1, round(thickness * visual_scale))
            pygame.draw.line(surface, outline, point(*start), point(*end), thickness + 2)
            pygame.draw.line(surface, color, point(*start), point(*end), thickness)

        # Independent legs keep stepping during a punch or air action.
        limb((-5, 40), (-6 - stride, 53 - lift), body)
        limb((5, 40), (6 + stride, 53 - lift), body)
        for dx in (-6 - stride, 6 + stride):
            foot = pygame.Rect(0, 0, max(4, round(9 * scale_x)), max(3, round(4 * scale_y)))
            foot.midbottom = point(dx, 56 - lift)
            pygame.draw.rect(surface, outline, foot)

        limb((-8, 29 + bob), (-11 + stride, 39 + arm_raise + bob), body, 5)
        torso = pygame.Rect(0, 0, round(20 * scale_x), round(17 * scale_y))
        torso.midtop = point(lean, 25 + bob)
        pygame.draw.rect(surface, body, torso)
        pygame.draw.rect(surface, outline, torso, max(1, round(2 * visual_scale)))
        if not punching:
            limb((8, 29 + bob), (11 - stride, 39 + arm_raise + bob), body, 5)

        head_rect = pygame.Rect(0, 0, round(26 * scale_x), round(26 * scale_y))
        head_rect.midtop = point(lean, bob)
        pygame.draw.rect(surface, head, head_rect, border_radius=3)
        pygame.draw.rect(surface, outline, head_rect, max(1, round(2 * visual_scale)),
                         border_radius=max(1, round(3 * visual_scale)))
        eye = point(lean + 5, 11 + bob)
        pygame.draw.rect(surface, outline, (eye[0] - 2, eye[1] - 2, 4, 5))
        mouth = point(lean + 4, 20 + bob)
        pygame.draw.line(surface, outline, mouth, (mouth[0] + 4 * facing, mouth[1]), 1)

    def _draw_sprite(self, surface, image, x, y, width, height, facing,
                     flash_ratio=0.0, preserve_canvas=None, crop_bounds=None,
                     render_scale=1.0):
        if preserve_canvas is None:
            preserve_canvas = self.preserve_canvas
        if not preserve_canvas:
            image = self._cropped(image, crop_bounds) if crop_bounds else self._trimmed(image)
        if image is None:
            return
        draw_height = max(1, round(self.sprite_height * render_scale))
        draw_width = max(1, round(image.get_width() * draw_height / image.get_height()))
        image = self._scaled(image, (draw_width, draw_height))
        if facing < 0:
            image = self._scaled(image, (draw_width, draw_height), flipped=True)
        if flash_ratio > 0:
            image = self._flash_tint(image, flash_ratio)
        surface.blit(image, image.get_rect(midbottom=(round(x + width / 2), round(y + height))))

    def _flash_tint(self, image, ratio):
        """Return a cached red-tinted frame without rebuilding masks per draw."""
        ratio = max(0.0, min(1.0, ratio))
        if ratio <= 0:
            return image
        # Quantization bounds the cache while keeping the brief damage flash
        # visually smooth at normal frame rates.
        level = round(ratio * 8)
        if level <= 0:
            return image
        key = id(image), level
        cached = self._flash_tinted_frames.get(key)
        if cached is not None:
            return cached

        mask = self._flash_masks.get(id(image))
        if mask is None:
            mask = pygame.mask.from_surface(image, threshold=1).to_surface(
                setcolor=(255, 0, 0, 255), unsetcolor=(0, 0, 0, 0))
            self._flash_masks[id(image)] = mask
        tinted = image.copy()
        mask.set_alpha(round(230 * level / 8))
        tinted.blit(mask, (0, 0))
        self._flash_tinted_frames[key] = tinted
        return tinted

    def _trimmed(self, image):
        key = id(image)
        if key not in self._trimmed_frames:
            bounds = image.get_bounding_rect(min_alpha=16)
            self._trimmed_frames[key] = image.subsurface(bounds).copy() if bounds.width and bounds.height else None
        return self._trimmed_frames[key]

    def _cropped(self, image, bounds):
        key = id(image), tuple(bounds)
        if key not in self._cropped_frames:
            self._cropped_frames[key] = image.subsurface(bounds).copy()
        return self._cropped_frames[key]

    def _scaled(self, image, size, flipped=False):
        key = id(image), size, flipped
        if key not in self._scaled_frames:
            scaled = pygame.transform.scale(image, size)
            self._scaled_frames[key] = pygame.transform.flip(scaled, True, False) if flipped else scaled
        return self._scaled_frames[key]


class PunchAnim:
    """Independent extend/retract overlay; retained curve and default duration."""

    def __init__(self, duration=180):
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Punch duration must be positive and finite")
        self.active = False
        self.t = 0.0
        self.duration = duration
        self.origin = (0.0, 0.0)
        self.target = (0.0, 0.0)

    def start(self, origin, target):
        self.active = True
        self.t = 0.0
        self.origin = origin
        self.target = target

    def update(self, dt):
        if self.active:
            self.t = min(self.duration, self.t + max(0.0, dt))
            if self.t >= self.duration:
                self.active = False

    def progress(self):
        return min(1.0, self.t / self.duration) if self.active else 1.0

    def current_pos(self, origin=None):
        p = self.progress()
        e = (p / 0.5) ** 0.5 if p < 0.5 else 1.0 - ((p - 0.5) / 0.5) ** 0.5
        ox, oy = self.origin if origin is None else origin
        tx, ty = self.target
        return ox + (tx - ox) * e, oy + (ty - oy) * e
