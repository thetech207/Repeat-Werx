"""Periodic (tileable) Perlin gradient noise.

The gradient lattice wraps every `period` cells, so sampling over one
tile in [0, 1)^2 yields a field whose left/right and top/bottom edges
match exactly -- essential for seamless repeats.
"""

from __future__ import annotations

import math
import random


def _fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


class PeriodicPerlin:
    def __init__(self, period: int, seed: int = 0):
        self.period = max(1, int(period))
        rng = random.Random(seed)
        p = self.period
        self._grad = [[None] * p for _ in range(p)]
        for i in range(p):
            for j in range(p):
                a = rng.random() * math.tau
                self._grad[i][j] = (math.cos(a), math.sin(a))

    def __call__(self, x: float, y: float) -> float:
        """Noise at lattice coords (x, y); roughly in [-0.71, 0.71]."""
        p = self.period
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        x0 %= p
        y0 %= p
        x1, y1 = (x0 + 1) % p, (y0 + 1) % p
        g = self._grad

        def dot(ix, iy, dx, dy):
            gx, gy = g[ix][iy]
            return gx * dx + gy * dy

        n00 = dot(x0, y0, fx, fy)
        n10 = dot(x1, y0, fx - 1, fy)
        n01 = dot(x0, y1, fx, fy - 1)
        n11 = dot(x1, y1, fx - 1, fy - 1)
        u, v = _fade(fx), _fade(fy)
        nx0 = n00 + u * (n10 - n00)
        nx1 = n01 + u * (n11 - n01)
        return nx0 + v * (nx1 - nx0)


class TileableField:
    """Fractal (fBm) periodic noise sampled in tile-fraction coords."""

    def __init__(self, period: int = 3, octaves: int = 3, seed: int = 0):
        self.octaves = max(1, int(octaves))
        self.layers = [PeriodicPerlin(period * (2 ** o), seed * 131 + o)
                       for o in range(self.octaves)]

    def __call__(self, u: float, v: float) -> float:
        """u, v in tile fractions (any real; wraps at 1). Returns 0..1."""
        total, amp, norm = 0.0, 1.0, 0.0
        for lay in self.layers:
            total += amp * lay(u * lay.period, v * lay.period)
            norm += amp
            amp *= 0.5
        val = 0.5 + (total / norm) * 0.75
        return min(1.0, max(0.0, val))

    def angle(self, u: float, v: float) -> float:
        """Flow direction (degrees) from the field's gradient."""
        e = 1e-3
        dx = self(u + e, v) - self(u - e, v)
        dy = self(u, v + e) - self(u, v - e)
        # perpendicular to the gradient follows the field's contours
        return math.degrees(math.atan2(dx, -dy))
