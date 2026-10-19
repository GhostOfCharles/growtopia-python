"""Presentation-only fall zoom layered over the existing world camera."""

import math


class FallingCamera:
    def __init__(self, trigger_distance=192.0, strength=1.10, return_ms=1000.0):
        self.trigger_distance = trigger_distance
        self.strength = strength
        self.return_ms = return_ms
        self.reset()

    def reset(self):
        self.zoom = 1.0
        self._return_elapsed = None
        self._return_start = 1.0

    def update(self, dt, *, fall_distance, descending, impact=False, recovering=False,
               alive=True):
        if not alive:
            self.reset()
            return
        if impact:
            self._return_elapsed = 0.0
            self._return_start = self.zoom
        if self._return_elapsed is not None:
            if not impact:
                self._return_elapsed += dt
            t = min(1.0, self._return_elapsed / self.return_ms)
            eased = t * t * (3 - 2 * t)
            self.zoom = self._return_start + (1.0 - self._return_start) * eased
            if t >= 1:
                self.reset()
            return
        target = self.strength if descending and fall_distance > self.trigger_distance else 1.0
        self.zoom += (target - self.zoom) * (1 - math.exp(-dt / 150.0))
        if abs(self.zoom - 1.0) < .0001:
            self.zoom = 1.0
