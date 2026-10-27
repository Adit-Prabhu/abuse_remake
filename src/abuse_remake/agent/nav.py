"""Navigation over the tiles the player has seen: the search part of the motor skills.

The original keeps an automap of the tiles the player has seen (``abuse/src/automap.c``).
The skills plan only over those tiles, never over unseen parts of the level, so they know
no more than a human looking at the automap. Planning is A* over "standable" cells: an open
cell for the feet, an open cell above for the head, and something to stand on. Edges are walks
(with steps of one cell), falls, and jumps sized to the player's real jump: ``jump_yvel`` -15
with the original gravity rises about 4 cells, and running jumps clear about 4 cells across.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from ..engine.cmath import cdiv
from ..engine.geometry import FORE_H, FORE_W
from .observation import tile_class

OPEN = {"."}
FEET_OK = {".", "/", "\\", "_"}
SUPPORT = {"#", "/", "\\", "_", "+", "^"}
JUMP_UP = 4
JUMP_ACROSS = 4
MAX_FALL = 25


@dataclass
class KnownMap:
    seen: set[tuple[int, int]] = field(default_factory=set)
    # cells seen covered by a hidden wall that imitates a ledge, floor or pillar: remembered as
    # solid, like any wall, until seen without it
    solid: set[tuple[int, int]] = field(default_factory=set)

    def remember_solid(self, x0: int, y0: int, w: int, h: int, cells: set[tuple[int, int]]) -> None:
        view = {(c, r) for r in range(cdiv(y0, FORE_H), cdiv(y0 + h - 1, FORE_H) + 1)
                for c in range(cdiv(x0, FORE_W), cdiv(x0 + w - 1, FORE_W) + 1)}
        self.solid = (self.solid - view) | (cells & view)

    def reveal(self, x0: int, y0: int, w: int, h: int) -> None:
        for r in range(cdiv(y0, FORE_H), cdiv(y0 + h - 1, FORE_H) + 1):
            for c in range(cdiv(x0, FORE_W), cdiv(x0 + w - 1, FORE_W) + 1):
                self.seen.add((c, r))


def cell_of(x: int, y: int) -> tuple[int, int]:
    return cdiv(x, FORE_W), cdiv(y - 1, FORE_H)


class Navigator:
    def __init__(self, tilemap, known: KnownMap, blocked: set[tuple[int, int]] | None = None):
        self.tm = tilemap
        self.known = known
        self.blocked = blocked or set()  # cells covered by visible blocking objects (walls, doors)

    def cls(self, c: int, r: int) -> str | None:
        if (c, r) not in self.known.seen:
            return None
        if (c, r) in self.blocked or (c, r) in self.known.solid:
            return "#"
        return tile_class(self.tm, self.tm.get(c, r))

    def passable(self, c: int, r: int) -> bool:
        return self.cls(c, r) in FEET_OK and self.cls(c, r - 1) in OPEN

    def standable(self, c: int, r: int) -> bool:
        if not self.passable(c, r):
            return False
        feet = self.cls(c, r)
        if feet in ("/", "\\", "_"):
            return True
        return self.cls(c, r + 1) in SUPPORT

    def nearest_standable(self, c: int, r: int, radius: int = 3):
        best, best_d = None, 1e9
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if self.standable(c + dc, r + dr):
                    d = abs(dc) * 1.0 + abs(dr) * 1.5
                    if d < best_d:
                        best, best_d = (c + dc, r + dr), d
        return best

    def edges(self, node):
        c, r = node
        for dc in (-1, 1):
            for dr in (-1, 0, 1):
                if self.standable(c + dc, r + dr):
                    yield (c + dc, r + dr), 1.0 + 0.3 * abs(dr), "walk"
            nc = c + dc
            if self.passable(nc, r) and not self.standable(nc, r):  # step off and fall
                for k in range(1, MAX_FALL):
                    if not self.passable(nc, r + k):
                        break
                    if self.standable(nc, r + k):
                        yield (nc, r + k), 1.0 + 0.15 * k, "fall"
                        break
        for dr in range(1, JUMP_UP + 1):  # jumps up, possibly sideways
            if not all(self.cls(c, r - 1 - k) in OPEN for k in range(1, dr + 1)):
                break
            for dc in range(-2, 3):
                if self.standable(c + dc, r - dr) and (dc != 0 or dr > 1):
                    yield (c + dc, r - dr), 2.0 + 0.4 * dr + 0.3 * abs(dc), "jump"
        for dc in range(-JUMP_ACROSS, JUMP_ACROSS + 1):  # jumps across gaps
            if abs(dc) < 2:
                continue
            step = 1 if dc > 0 else -1
            if not all(self.cls(c + k * step, r - 2) in OPEN and self.cls(c + k * step, r - 1) in FEET_OK
                       for k in range(1, abs(dc) + 1)):
                continue
            for dr in (-1, 0, 1, 2):
                if self.standable(c + dc, r + dr):
                    yield (c + dc, r + dr), 2.0 + 0.5 * abs(dc), "jump"
                    break

    def plan(self, start, goal_fn, max_nodes: int = 6000):
        """A* from ``start`` to the first node where ``goal_fn(node)`` is a number (heuristic
        target); ``goal_fn`` returns 0 at a goal. Returns [(node, edge kind), ...] or None."""
        if start is None:
            return None
        h0 = goal_fn(start)
        frontier = [(h0, 0.0, start)]
        came = {start: (None, None)}
        cost = {start: 0.0}
        seen = 0
        while frontier and seen < max_nodes:
            _, g, node = heapq.heappop(frontier)
            seen += 1
            if goal_fn(node) == 0:
                path = []
                while node is not None:
                    prev, kind = came[node]
                    path.append((node, kind))
                    node = prev
                return list(reversed(path))
            for nxt, w, kind in self.edges(node):
                ng = g + w
                if ng < cost.get(nxt, 1e18):
                    cost[nxt] = ng
                    came[nxt] = (node, kind)
                    heapq.heappush(frontier, (ng + goal_fn(nxt), ng, nxt))
        return None

    def reachable(self, start, limit: int = 4000) -> dict:
        """Dijkstra costs to every reachable node (for exploration targets)."""
        if start is None:
            return {}
        dist = {start: 0.0}
        q = [(0.0, start)]
        while q and len(dist) < limit:
            d, node = heapq.heappop(q)
            if d > dist.get(node, 1e18):
                continue
            for nxt, w, _ in self.edges(node):
                nd = d + w
                if nd < dist.get(nxt, 1e18):
                    dist[nxt] = nd
                    heapq.heappush(q, (nd, nxt))
        return dist

    def is_frontier(self, node) -> bool:
        c, r = node
        return any((c + dc, r + dr) not in self.known.seen for dc in (-2, -1, 1, 2) for dr in (-2, -1, 0, 1))


def blocked_cells(objects) -> set[tuple[int, int]]:
    """Cells covered by visible objects that stop the player: closed doors and active force
    fields. Taken from the observation, so it uses only what is on screen. (Hidden walls drawn as
    scenery, cracked or not, are solid in ``KnownMap.solid``: ``observation.scenery_cells``.)"""
    out = set()
    for o in objects:
        kind = o["kind"]
        if kind == "door" and o.get("state") in ("closed", "closing"):
            c, r = cell_of(o["x"], o["y"])
            for dr in range(0, 3):
                out.add((c, r - dr))
        elif kind == "force_field":
            c, r = cell_of(o["x"], o["y"])
            for dr in range(0, 8):
                out.add((c, r + dr))
    return out
