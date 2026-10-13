"""Bodies and pixel-stepped movement against the tile grid and the elevators.

A body moves one pixel at a time, so nothing tunnels through a wall at dash or falling speed.
One-way ledges (``=``) and the tops of ladders hold a body only while it moves down onto them
and is not dropping through. Elevators are one-way platforms that carry their riders.
"""

from __future__ import annotations

from dataclasses import dataclass

from .fixed import SUB
from .tilemap import LADDER, ONEWAY, OPAQUE, SHIFT

GRAVITY = 154  # 0.6 px/tick^2
MAX_FALL = 2560  # 10 px/tick


@dataclass
class Body:
    x: int
    y: int
    w: int
    h: int
    vx: int = 0
    vy: int = 0
    rx: int = 0
    ry: int = 0
    grounded: bool = False
    riding: int = -1  # index of the elevator under the feet, or -1
    drop: int = 0  # ticks left ignoring one-way floors

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def overlaps(self, o) -> bool:
        return self.x < o.x + o.w and self.x + self.w > o.x and self.y < o.y + o.h and self.y + self.h > o.y

    def contains(self, x: int, y: int, pad: int = 0) -> bool:
        return self.x - pad <= x < self.x + self.w + pad and self.y - pad <= y < self.y + self.h + pad


def wall_at(game, b: Body, nx: int) -> bool:
    """Would the body hit a wall standing at x = nx?"""
    col = nx + b.w - 1 if nx > b.x else nx
    tx = col >> SHIFT
    g = game.grid
    for ty in range(b.y >> SHIFT, ((b.y + b.h - 1) >> SHIFT) + 1):
        if g.at(tx, ty) in OPAQUE:
            return True
    return False


def floor_at(game, b: Body, ny: int, down: bool, oneway: bool = True) -> bool:
    """Would the body hit a floor (down) or ceiling (up) standing at y = ny?"""
    row = ny + b.h - 1 if down else ny
    ty = row >> SHIFT
    g = game.grid
    top_row = (row & 15) == 0
    for tx in range(b.x >> SHIFT, ((b.x + b.w - 1) >> SHIFT) + 1):
        c = g.at(tx, ty)
        if c in OPAQUE:
            return True
        if down and oneway and top_row and b.drop == 0 and (c == ONEWAY or (c == LADDER and g.ladder_top(tx, ty))):
            return True
    if down and oneway and b.drop == 0:
        for i, e in enumerate(game.elevators):
            if row == e.y and b.x < e.x + e.w and b.x + b.w > e.x:
                b.riding = i
                return True
    return False


def step_x(game, b: Body, dx: int) -> bool:
    """Move dx pixels; True if a wall stopped the body."""
    s = 1 if dx > 0 else -1
    for _ in range(abs(dx)):
        if wall_at(game, b, b.x + s):
            return True
        b.x += s
    return False


def step_y(game, b: Body, dy: int, oneway: bool = True) -> bool:
    """Move dy pixels; True if a floor or ceiling stopped the body."""
    s = 1 if dy > 0 else -1
    for _ in range(abs(dy)):
        if floor_at(game, b, b.y + s, s > 0, oneway):
            return True
        b.y += s
    return False


def integrate(game, b: Body, gravity: int = GRAVITY, max_fall: int = MAX_FALL, oneway: bool = True):
    """Apply gravity and velocity with collision. Returns (hit_wall, hit_floor_or_ceiling)."""
    if gravity:
        b.vy = min(max_fall, b.vy + gravity)
    b.rx += b.vx
    dx = b.rx // SUB
    b.rx -= dx * SUB
    b.ry += b.vy
    dy = b.ry // SUB
    b.ry -= dy * SUB
    hit_x = step_x(game, b, dx) if dx else False
    if hit_x:
        b.vx, b.rx = 0, 0
    b.riding = -1
    hit_y = step_y(game, b, dy, oneway) if dy else False
    if hit_y:
        b.vy, b.ry = 0, 0
    b.riding = -1
    b.grounded = b.vy >= 0 and floor_at(game, b, b.y + 1, True, oneway)
    if b.grounded and b.vy > 0:
        b.vy, b.ry = 0, 0
    if b.drop:
        b.drop -= 1
    return hit_x, hit_y


def on_ceiling(game, b: Body) -> bool:
    return floor_at(game, b, b.y - 1, False)


def free_at(game, b: Body, x: int, y: int, h: int | None = None) -> bool:
    """True if the box (x, y, b.w, h) overlaps no opaque tile."""
    return not game.grid.rect_hits(x, y, b.w, b.h if h is None else h, OPAQUE)
