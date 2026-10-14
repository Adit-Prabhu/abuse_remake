"""A conservative tile-graph model of where the runner can go, for map checks and dev tools.

Nodes are tiles the runner's feet can rest in. Edges are walking, crawling, falling, jumping
(rise up to 4 tiles; 7 with the boots), climbing ladders, dropping through ledges, elevator
rides and teleporter pads. Switch doors open once their switch is reachable, keycard gates
once their key is, and the boots apply once they are picked up. Movement is modelled
conservatively (the real physics can jump further), but doors are optimistic: a timed door is
treated as staying open once its switch is reachable, so the Hive's 10-second door is checked by
the autopilot test, not by this model.
"""

from __future__ import annotations

from collections import deque

from .tilemap import BREAK, DOOR, LADDER, ONEWAY, OPAQUE, SOLID, MapData

PASS = frozenset(range(8)) - OPAQUE


class NavGrid:
    def __init__(self, data: MapData, open_groups: set[str] = frozenset(), boots: bool = False):
        self.data = data
        self.w, self.h = data.width, data.height
        self.cells = bytearray(data.tiles)
        for g in open_groups:
            for tx, ty in data.doors.get(g, ()):
                self.cells[ty * self.w + tx] = 0
        self.boots = boots
        self.extra_support: set[tuple[int, int]] = set()
        self.links: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self._elevators_and_pads()

    def at(self, tx: int, ty: int) -> int:
        if 0 <= tx < self.w and 0 <= ty < self.h:
            return self.cells[ty * self.w + tx]
        return SOLID

    def free(self, tx: int, ty: int) -> bool:
        return self.at(tx, ty) not in OPAQUE

    def support(self, tx: int, ty: int) -> bool:
        """Can feet rest on top of tile (tx, ty)?"""
        c = self.at(tx, ty)
        return c in (SOLID, BREAK, DOOR, ONEWAY) or (c == LADDER and self.at(tx, ty - 1) != LADDER) \
            or (tx, ty) in self.extra_support

    def node(self, tx: int, ty: int) -> bool:
        """A place the runner can be: standing (3 free tiles), crouching (2) or on a ladder."""
        if not (self.free(tx, ty) and self.free(tx, ty - 1)):
            return False
        return self.support(tx, ty + 1) or self.on_ladder(tx, ty)

    def on_ladder(self, tx: int, ty: int) -> bool:
        return self.at(tx, ty) == LADDER or self.at(tx, ty - 1) == LADDER

    def tall(self, tx: int, ty: int) -> bool:
        return self.free(tx, ty - 2)

    def _elevators_and_pads(self) -> None:
        d = self.data
        for e in d.entities_of("elevator"):
            up = down = e.ty
            while self.at(e.tx, up - 1) == 7:
                up -= 1
            while self.at(e.tx, down + 1) == 7:
                down += 1
            ends = []
            for row in {up, down, e.ty}:
                for c in (e.tx - 1, e.tx, e.tx + 1):
                    self.extra_support.add((c, row + 1))
                ends.append((e.tx, row))
            for a in ends:
                for b in ends:
                    if a != b:
                        self.links.setdefault(a, []).append(b)
        pads: dict[str, list] = {}
        for e in d.entities_of("teleport"):
            pads.setdefault(e.args[0], []).append((e.tx, e.ty))
        for group in pads.values():
            for a in group:
                for b in group:
                    if a != b:
                        self.links.setdefault(a, []).append(b)

    def fall(self, tx: int, ty: int) -> tuple[int, int] | None:
        y = ty
        while y < self.h:
            if not self.free(tx, y):
                return None
            if self.support(tx, y + 1) or self.at(tx, y) == LADDER:
                return tx, y
            y += 1
        return None

    def clear_column(self, tx: int, top: int, bottom: int) -> bool:
        return all(self.free(tx, r) for r in range(top, bottom + 1))

    def neighbours(self, tx: int, ty: int):
        tall = self.tall(tx, ty)
        # walk / crawl, or step off an edge and fall
        for d in (-1, 1):
            nx = tx + d
            if self.free(nx, ty) and self.free(nx, ty - 1):
                if self.node(nx, ty):
                    yield nx, ty
                else:
                    for drift in (0, d, 2 * d):
                        cols = range(nx, nx + drift + d, d) if drift else (nx,)
                        if all(self.clear_column(c, ty - 1, ty + 1 if c != nx + drift else ty) for c in cols):
                            got = self.fall(nx + drift, ty)
                            if got:
                                yield got
        # drop through a ledge or ladder top
        below = self.at(tx, ty + 1)
        if below in (ONEWAY, LADDER) or (tx, ty + 1) in self.extra_support:
            got = self.fall(tx, ty + 2) if self.free(tx, ty + 2) or self.at(tx, ty + 2) == LADDER else None
            if got:
                yield got
            if below == LADDER:
                yield tx, ty + 1
        # ladders
        if self.on_ladder(tx, ty):
            for dy in (-1, 1):
                if self.node(tx, ty + dy) or self.on_ladder(tx, ty + dy) and self.free(tx, ty + dy):
                    yield tx, ty + dy
        if self.at(tx, ty + 1) == LADDER:
            yield tx, ty + 1
        # jumps (standing or from a ladder)
        if tall and (self.support(tx, ty + 1) or self.on_ladder(tx, ty)):
            yield from self._jumps(tx, ty)
        yield from self.links.get((tx, ty), ())

    def _jumps(self, tx: int, ty: int):
        max_rise = 7 if self.boots else 4
        head = 0
        while head < max_rise and self.free(tx, ty - 3 - head):
            head += 1
        for rise in range(-6, head + 1):
            ny = ty - rise
            reach = (6 if self.boots else 5) if rise <= 1 else (4 if rise <= 3 else 3)
            if self.boots and rise > 4:
                reach = 3
            for dx in range(-reach, reach + 1):
                nx = tx + dx
                if (dx == 0 and rise <= 0) or not self.node(nx, ny) or not self.tall(nx, ny):
                    continue
                if self._arc_clear(tx, ty, nx, ny, max(rise, 0)):
                    yield nx, ny

    def _arc_clear(self, tx, ty, nx, ny, rise) -> bool:
        apex = min(ty, ny) - (1 if rise > 0 else 0)
        step = 1 if nx >= tx else -1
        for c in range(tx, nx + step, step):
            if not self.clear_column(c, apex - 2, apex):
                return False
        # the landing must be where a fall from the apex really stops (ledges and ladder tops catch you)
        return self.clear_column(nx, apex - 2, ny) and self.fall(nx, apex) == (nx, ny)


def start_of(data: MapData) -> tuple[int, int]:
    p = data.entities_of("player")[0]
    return p.tx, p.ty


def explore(data: MapData, open_groups=frozenset(), boots=False, start=None) -> set[tuple[int, int]]:
    g = NavGrid(data, set(open_groups), boots)
    s = start or start_of(data)
    seen = {s}
    q = deque([s])
    while q:
        cur = q.popleft()
        for n in g.neighbours(*cur):
            if n not in seen:
                seen.add(n)
                q.append(n)
    return seen


def near(seen, tx: int, ty: int, slack: int = 1) -> bool:
    return any((tx + dx, ty + dy) in seen for dx in range(-slack, slack + 1) for dy in range(-1, 2))


def solve(data: MapData) -> tuple[set, set[str], bool]:
    """Explore, opening doors and taking boots as soon as they are reachable."""
    groups: set[str] = set()
    boots = False
    while True:
        seen = explore(data, groups, boots)
        new = set(groups)
        for e in data.entities_of("switch"):
            if near(seen, e.tx, e.ty):
                new.add(e.args[0])
        for e in data.entities_of("pickup"):
            if e.args[0].startswith("key_") and near(seen, e.tx, e.ty):
                new.add("key:" + e.args[0][4:])
        got_boots = boots or any(e.args[0] == "boots" and near(seen, e.tx, e.ty)
                                 for e in data.entities_of("pickup"))
        if new == groups and got_boots == boots:
            return seen, groups, boots
        groups, boots = new, got_boots
