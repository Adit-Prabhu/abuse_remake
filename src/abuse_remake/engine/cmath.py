"""C-compatible integer arithmetic, fixed-point trig and the original random table.

Python's ``//`` and ``%`` floor; C (and so the original engine) truncates toward zero.
Every division in the port goes through :func:`cdiv` / :func:`cmod` so results match.

Sources (historicalsource/abuse@01cce80):
- lisp_cos / lisp_sin / lisp_atan2: abuse/src/lisp.c:676-775
- random table: imlib/jrand.c and imlib/include/jrand.hpp
"""

from __future__ import annotations

from .tables import ATAN_TABLE, SIN_TABLE

FIXED_TRIG_SIZE = 360
TBS = 1662
RAND_TABLE_SIZE = 1024


def cdiv(a: int, b: int) -> int:
    """C integer division: truncates toward zero."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def cmod(a: int, b: int) -> int:
    """C remainder: takes the sign of the dividend."""
    return a - cdiv(a, b) * b


def u8(v: int) -> int:
    return v & 0xFF


def s8(v: int) -> int:
    v &= 0xFF
    return v - 0x100 if v & 0x80 else v


def u16(v: int) -> int:
    return v & 0xFFFF


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def s32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def lisp_cos(x: int) -> int:
    x = cmod(x + FIXED_TRIG_SIZE // 4, FIXED_TRIG_SIZE)
    return SIN_TABLE[FIXED_TRIG_SIZE + x] if x < 0 else SIN_TABLE[x]


def lisp_sin(x: int) -> int:
    x = cmod(x, FIXED_TRIG_SIZE)
    return SIN_TABLE[FIXED_TRIG_SIZE + x] if x < 0 else SIN_TABLE[x]


def lisp_atan2(dy: int, dx: int) -> int:
    """Port of lisp_atan2, including its quirk of returning 260 (not 270) for steep
    down-right angles. Angles are degrees, 0 = right, 90 = up (screen y is flipped
    by the callers)."""
    if dy == 0:
        return 0 if dx > 0 else 180
    if dx == 0:
        return 90 if dy > 0 else 270
    if dx > 0:
        if dy > 0:
            if abs(dx) > abs(dy):
                a = cdiv(dx * 29, dy)
                return 0 if a >= TBS else 45 - ATAN_TABLE[a]
            a = cdiv(dy * 29, dx)
            return 90 if a >= TBS else 45 + ATAN_TABLE[a]
        if abs(dx) > abs(dy):
            a = cdiv(dx * 29, abs(dy))
            return 0 if a >= TBS else 315 + ATAN_TABLE[a]
        a = cdiv(abs(dy) * 29, dx)
        return 260 if a >= TBS else 315 - ATAN_TABLE[a]
    if dy > 0:
        if abs(dx) > abs(dy):
            a = cdiv(-dx * 29, dy)
            return 135 + 45 if a >= TBS else 135 + ATAN_TABLE[a]
        a = cdiv(dy * 29, -dx)
        return 135 - 45 if a >= TBS else 135 - ATAN_TABLE[a]
    if abs(dx) > abs(dy):
        a = cdiv(-dx * 29, abs(dy))
        return 225 - 45 if a >= TBS else 225 - ATAN_TABLE[a]
    a = cdiv(abs(dy) * 29, abs(dx))
    return 225 + 45 if a >= TBS else 225 + ATAN_TABLE[a]


def _make_rand_table() -> tuple[int, ...]:
    # jrand_init: the table is always the same; only the start index is random.
    rseed = (ord("F") << 24) | (ord("U") << 16) | (ord("C") << 8) | ord("K")
    out = []
    for _ in range(RAND_TABLE_SIZE):
        rseed = (rseed * 0x41C64E6D + 12345) & 0xFFFFFFFF
        out.append((rseed >> 16) & 0xFFFF)
    return tuple(out)


RAND_TABLE = _make_rand_table()


class JRand:
    """The engine's only randomness. The original seeds ``rand_on`` from the clock
    (``time(NULL) % 1024``); an episode seed sets it explicitly instead."""

    __slots__ = ("rand_on",)

    def __init__(self, seed: int = 0):
        self.rand_on = seed % RAND_TABLE_SIZE

    def jrand(self) -> int:
        v = RAND_TABLE[self.rand_on & (RAND_TABLE_SIZE - 1)]
        self.rand_on = (self.rand_on + 1) & 0xFFFF
        return v

    def jrandom(self, n: int) -> int:
        return self.jrand() % n

    def shift(self, amount: int) -> None:
        """``shift_rand_table`` (clisp.c case 237): ``rand_on += amount``."""
        self.rand_on = (self.rand_on + amount) & 0xFFFF
