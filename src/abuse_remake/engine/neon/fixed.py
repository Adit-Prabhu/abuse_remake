"""Integer maths for the Neon simulation: sub-pixel units, angle tables and helpers.

Positions are whole pixels; velocities are in 1/256 pixel per tick (``SUB``). Angles are
integers on a 1024-step circle with screen axes (0 points right, 256 points down). The tables
are built once from ``math`` and rounded to integers, so every step afterwards is integer-only
and identical on every platform.
"""

from __future__ import annotations

import math
from bisect import bisect_left

SUB = 256  # sub-pixels per pixel
ANG = 1024  # angle steps in a full turn
ONE = 1024  # fixed-point 1.0 for the trig tables

COS = tuple(round(math.cos(2 * math.pi * i / ANG) * ONE) for i in range(ANG))
SIN = tuple(round(math.sin(2 * math.pi * i / ANG) * ONE) for i in range(ANG))
_OCT = ANG // 8
_TAN = tuple(round(math.tan(math.pi / 4 * i / _OCT) * 65536) for i in range(_OCT + 1))


def px(v: float) -> int:
    """Pixels per tick to sub-pixels per tick (constants only)."""
    return round(v * SUB)


def rdiv(n: int, d: int) -> int:
    """Integer division rounded half away from zero (symmetric for negative values)."""
    if n >= 0:
        return (n + d // 2) // d
    return -((-n + d // 2) // d)


def sign(v: int) -> int:
    return (v > 0) - (v < 0)


def approach(v: int, target: int, step: int) -> int:
    if v < target:
        return min(target, v + step)
    return max(target, v - step)


def iatan2(dy: int, dx: int) -> int:
    """The angle of (dx, dy) on the 1024-step circle, integer-only."""
    if dx == 0 and dy == 0:
        return 0
    ax, ay = abs(dx), abs(dy)
    if ax >= ay:
        t = ay * 65536 // ax
        a = _nearest(t)
    else:
        t = ax * 65536 // ay
        a = 2 * _OCT - _nearest(t)
    if dx < 0:
        a = ANG // 2 - a
    if dy < 0:
        a = -a
    return a % ANG


def _nearest(t: int) -> int:
    i = bisect_left(_TAN, t)
    if i > _OCT:
        return _OCT
    if i > 0 and t - _TAN[i - 1] < _TAN[i] - t:
        return i - 1
    return i


def vec(angle: int, speed: int) -> tuple[int, int]:
    """A velocity of ``speed`` (any unit) along ``angle``."""
    a = angle % ANG
    return rdiv(speed * COS[a], ONE), rdiv(speed * SIN[a], ONE)


def angle_diff(a: int, b: int) -> int:
    """Signed shortest turn from a to b, in -512..511."""
    return (b - a + ANG // 2) % ANG - ANG // 2


def turn_toward(a: int, b: int, step: int) -> int:
    d = angle_diff(a, b)
    if abs(d) <= step:
        return b % ANG
    return (a + (step if d > 0 else -step)) % ANG


def dist(dx: int, dy: int) -> int:
    return math.isqrt(dx * dx + dy * dy)
