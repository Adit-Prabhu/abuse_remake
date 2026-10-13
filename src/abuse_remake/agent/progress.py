"""Evaluator-only progress: how close a player got to the exit.

This uses privileged knowledge (the whole map and the teleporter links) and lives on the runner
side. Players never receive it. Progress is ``1 - d_best / d_start``, where ``d`` is the A*
cost to the exit over the full tile graph plus teleporter links, sampled on every tick. Doors,
hidden walls and force fields are ignored and teleporters always work, which makes ``d``
optimistic; lifts are not modelled, which makes it pessimistic where a lift is the only way.
A win counts as 1.0.
"""

from __future__ import annotations

import heapq
from functools import cache

from ..engine.game import Game
from .nav import KnownMap, Navigator, cell_of


@cache
def _distance_field() -> dict:
    g = Game(seed=0)
    tm = g.world.tiles
    km = KnownMap({(c, r) for c in range(tm.width) for r in range(tm.height)})
    nav = Navigator(tm, km)
    nodes = [(c, r) for c in range(tm.width) for r in range(tm.height) if nav.standable(c, r)]
    rev: dict = {}
    for n in nodes:
        for m, w, _ in nav.edges(n):
            rev.setdefault(m, []).append((n, w))
    for o in g.world.objects:  # teleporters: TELE2 -> its destination; TP_DOOR -> the other door
        if o.ctype.name in ("TELE2", "TP_DOOR") and o.objs:
            a = nav.nearest_standable(*cell_of(o.x, o.y), radius=4)
            b = nav.nearest_standable(*cell_of(o.objs[0].x, o.objs[0].y), radius=4)
            if a and b:
                rev.setdefault(b, []).append((a, 3.0))
    exit_obj = g.world.find_type("NEXT_LEVEL")
    goal = nav.nearest_standable(*cell_of(exit_obj.x, exit_obj.y), radius=4)
    dist = {goal: 0.0}
    q = [(0.0, goal)]
    while q:
        d, n = heapq.heappop(q)
        if d > dist.get(n, 1e18):
            continue
        for m, w in rev.get(n, ()):
            nd = d + w
            if nd < dist.get(m, 1e18):
                dist[m] = nd
                heapq.heappush(q, (nd, m))
    return dist


def distance_to_exit(x: int, y: int) -> float | None:
    dist = _distance_field()
    c, r = cell_of(x, y)
    best = None
    for dr in range(-3, 4):
        for dc in range(-3, 4):
            d = dist.get((c + dc, r + dr))
            if d is not None and (best is None or d < best):
                best = d
    return best


class ProgressTracker:
    def __init__(self, x: int, y: int):
        self.start = distance_to_exit(x, y)
        self.best = self.start

    def update(self, x: int, y: int) -> None:
        d = distance_to_exit(x, y)
        if d is not None and (self.best is None or d < self.best):
            self.best = d

    def value(self, won: bool) -> float:
        if won:
            return 1.0
        if not self.start or self.best is None:
            return 0.0
        return max(0.0, min(1.0, 1.0 - self.best / self.start))
