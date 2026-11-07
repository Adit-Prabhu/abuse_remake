"""Find an input route that finishes a Remastered campaign level, by searching the engine.

    uv run python scripts/route_search.py --level level00 --goal level01 --out evidence/routes/level00.json

A development tool, not a player: it reads the World object freely. It runs a best-first search
over short input "macros" (run, jump, climb, press down, wait), from engine snapshots, keyed by
the player's coarse position and the state of the level's switches, walls and doors. While it
moves it fires at the nearest enemy, hidden wall or switch ball in sight. When an exit leading to
``--goal`` ends the level, it writes the route as run-length rows of
``[ticks, x, y, b1, b2, pointer dx, pointer dy]`` (the pointer is relative to the player), which
``replay_route`` plays back exactly. The route is evidence that the level can be finished under
the ported rules; tests/test_campaign_routes.py replays every saved route.
"""

from __future__ import annotations

import argparse
import heapq
import itertools
import json
import sys
import time
from pathlib import Path

from abuse_remake.engine import campaign
from abuse_remake.engine.game import Game
from abuse_remake.engine.view import Inputs

MACROS = {  # name: (x, y, special)
    "R": (1, 0, 0), "L": (-1, 0, 0), "RJ": (1, -1, 0), "LJ": (-1, -1, 0), "U": (0, -1, 0),
    "D": (0, 1, 0), "W": (0, 0, 0), "RD": (1, 1, 0), "LD": (-1, 1, 0),
}
TARGETS = ("HIDDEN_WALL", "SWITCH_BALL", "ANT_ROOF", "WHO", "FLYER", "GREEN_FLYER", "JUGGER", "ROB1",
           "TRACK_GUN", "SPRAY_GUN", "BOLDER")
STATEFUL = ("SWITCH", "SWITCH_ONCE", "SWITCH_BALL", "SWITCH_DOOR", "TRAP_DOOR2", "TRAP_DOOR3",
            "FORCE_FIELD", "TP_DOOR", "STEP", "BLOCK", "PUSHER")


def aim(g) -> tuple[int, int, int]:
    """Fire at the nearest target in sight within 260 px, else aim ahead without firing."""
    p = g.player
    best, best_d = None, 260 * 260
    for o in g.world.active:
        if o.deleted or not o.ctype.name.startswith(TARGETS) or o.hp <= 0 and not o.ctype.name.startswith("HIDDEN"):
            continue
        d = (o.x - p.x) ** 2 + (o.y - p.y) ** 2
        if d < best_d:
            best, best_d = o, d
    if best is None:
        return 0, 100 * (1 if p.direction > 0 else -1), -20
    h = best.picture_height() // 2 if best.ctype.name != "SWITCH_BALL" else 4
    return 1, best.x - p.x, best.y - h - (p.y - 20)


def tick(g, x, y, special, rows) -> None:
    fire, dx, dy = aim(g)
    p = g.player
    row = [1, x, y, special, fire, dx, dy]
    g.step(Inputs(x=x, y=y, b1=special, b2=fire, pointer_x=p.x + dx, pointer_y=p.y - 20 + dy))
    if rows and rows[-1][1:] == row[1:]:
        rows[-1][0] += 1
    else:
        rows.append(row)


MOVING = ("SMART_PLAT", "SWITCH_MOVER", "TELE", "TP_DOOR", "OBJ_MOVER")


def signature(g) -> tuple:
    """Switches, doors and walls by state; platforms and teleporters also by position, so that
    riding one counts as progress even while the player's own cell stays the same."""
    w = g.world
    states = tuple((o.ctype.name, o.aistate) for o in w.objects
                   if o.ctype.name.startswith(STATEFUL) and not o.deleted)
    moving = tuple((o.ctype.name, o.aistate, o.x // 16, o.y // 16) for o in w.objects
                   if o.ctype.name.startswith(MOVING) and not o.deleted)
    walls = sum(1 for o in w.objects if o.ctype.name.startswith("HIDDEN_WALL") and not o.deleted)
    return states, moving, walls


def key(g, cell: int) -> tuple:
    p = g.player
    return p.x // cell, p.y // cell, p.state == "climbing", signature(g)


def search(level: str, goal: str, seed: int, difficulty: str, budget: int, cell: int, ticks: int,
           to: tuple[int, int] | None = None):
    """Search for inputs that end the level through an exit to ``goal``, or, with ``to``, that
    bring the player within 24 px of that point."""
    g = Game(seed=seed, difficulty=difficulty, level=level, remastered=True)
    if to is not None:
        points = [to]
    else:
        points = [(o.x, o.y) for o in g.world.objects if o.ctype.name == "NEXT_LEVEL"
                  and campaign.exit_level(o.aistate) == goal]
        if not points:
            raise SystemExit(f"{level} has no exit to {goal}")

    def h(game) -> int:
        p = game.player
        return min(abs(p.x - x) + abs(p.y - y) for x, y in points)

    def done(game) -> bool:
        if to is not None:
            p = game.player
            return abs(p.x - to[0]) <= 24 and abs(p.y - to[1]) <= 24
        return finished(game, goal)

    counter = itertools.count()
    start_rows: list = []
    for _ in range(3):
        tick(g, 0, 0, 0, start_rows)
    frontier = [(h(g), next(counter), g.snapshot(), start_rows)]
    seen = {key(g, cell)}
    expanded = 0
    t0 = time.time()
    while frontier and expanded < budget:
        _, _, snap, rows = heapq.heappop(frontier)
        expanded += 1
        for x, y, special in MACROS.values():
            g.restore(snap)
            new_rows = [r[:] for r in rows]
            hp0 = g.player.hp
            for _ in range(ticks):
                tick(g, x, y, special, new_rows)
                if done(g):
                    return new_rows, expanded, time.time() - t0
                if g.player_dead:
                    break
            if g.player_dead or g.player.hp < min(hp0, 25):
                continue
            k = key(g, cell)
            if k in seen:
                continue
            seen.add(k)
            depth = sum(r[0] for r in new_rows)
            heapq.heappush(frontier, (h(g) + depth // 4, next(counter), g.snapshot(), new_rows))
        if expanded % 200 == 0:
            p = g.player
            print(f"  expanded {expanded}, frontier {len(frontier)}, seen {len(seen)}, "
                  f"last at ({p.x},{p.y}), {time.time() - t0:.0f}s", file=sys.stderr)
    return None, expanded, time.time() - t0


def finished(game, goal: str) -> bool:
    """The level ended at an exit to ``goal``: the next level is ``goal``, or, when ``goal``
    cannot be played (Level 2's exit to Level 3), the campaign ended there."""
    w = game.world
    if not w.globals.get("level_complete"):
        return False
    return w.globals.get("next_level") == goal if campaign.playable(goal) else "next_level" not in w.globals


def replay_route(route: dict) -> Game:
    """Play a saved route; returns the game after its last tick."""
    g = Game(seed=route["seed"], difficulty=route["difficulty"], level=route["level"], remastered=True)
    for n, x, y, special, fire, dx, dy in route["inputs"]:
        for _ in range(n):
            p = g.player
            g.step(Inputs(x=x, y=y, b1=special, b2=fire, pointer_x=p.x + dx, pointer_y=p.y - 20 + dy))
    return g


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--level", required=True, choices=campaign.LEVELS)
    ap.add_argument("--goal", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", default="hard")
    ap.add_argument("--budget", type=int, default=20000, help="nodes to expand at most")
    ap.add_argument("--cell", type=int, default=24, help="position grid for novelty, in pixels")
    ap.add_argument("--ticks", type=int, default=6, help="ticks per macro")
    ap.add_argument("--to", help="X,Y: reach this point instead of an exit (to check a spot is reachable)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    to = tuple(int(v) for v in args.to.split(",")) if args.to else None
    rows, expanded, secs = search(args.level, args.goal, args.seed, args.difficulty, args.budget,
                                  args.cell, args.ticks, to)
    if rows is None:
        print(f"no route found after {expanded} nodes ({secs:.0f}s)")
        return 1
    route = {"format": "campaign-route-1", "level": args.level, "goal": args.goal, "seed": args.seed,
             "difficulty": args.difficulty, "ticks": sum(r[0] for r in rows), "inputs": rows}
    if to is not None:
        route["format"], route["to"] = "campaign-reach-1", list(to)
    g = replay_route(route)
    if to is None:
        assert finished(g, args.goal)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(route, separators=(",", ":")) + "\n")
    print(f"route found: {route['ticks']} ticks, {len(rows)} rows, {expanded} nodes, {secs:.0f}s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
