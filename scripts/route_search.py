"""Find an input route that finishes a campaign level, by searching the engine.

    uv run python scripts/route_search.py --level level00 --goal level01 --out evidence/routes/level00.json
    uv run python scripts/route_search.py --mode classic --level level01 --goal level02 --out F

With ``--mode classic`` the search and the replay run Classic rules (the graded Level 1), and
the route is finished when the level ends; otherwise they run Remastered's campaign rules.

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

MACROS = {  # name: (x, y, special, ticks or None for --ticks)
    "R": (1, 0, 0, None), "L": (-1, 0, 0, None), "RJ": (1, -1, 0, None), "LJ": (-1, -1, 0, None),
    "U": (0, -1, 0, None), "D": (0, 1, 0, None), "W": (0, 0, 0, None), "RD": (1, 1, 0, None),
    "LD": (-1, 1, 0, None),
    "r": (1, 0, 0, 2), "l": (-1, 0, 0, 2),  # nudges, to stand on a ladder or a platform's sweet spot
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
    riding one counts as progress even while the player's own cell stays the same; and the
    enemies' health, so that a fight in place does too."""
    w = g.world
    states = tuple((o.ctype.name, o.aistate) for o in w.objects
                   if o.ctype.name.startswith(STATEFUL) and not o.deleted)
    moving = tuple((o.ctype.name, o.aistate, o.x // 16, o.y // 16) for o in w.objects
                   if o.ctype.name.startswith(MOVING) and not o.deleted)
    walls = sum(1 for o in w.objects if o.ctype.name.startswith("HIDDEN_WALL") and not o.deleted)
    # the health of active enemies, so that standing and shooting counts as progress
    foes = sum(o.hp for o in w.active if not o.deleted and o.ctype.name.startswith(TARGETS[2:]))
    return states, moving, walls, foes // 10


def key(g, cell: int) -> tuple:
    p = g.player
    return p.x // (cell // 2), p.y // cell, p.state == "climbing", signature(g)


def search(level: str, goal: str, seed: int, difficulty: str, budget: int, cell: int, ticks: int,
           to: tuple[int, int] | None = None, via: list[tuple[int, int]] | None = None,
           prefix: list[list[int]] | None = None, mode: str = "remastered",
           start: tuple[int, int] | None = None):
    """Search for inputs that end the level through an exit to ``goal``, or, with ``to``, that
    bring the player within 24 px of that point. ``via`` gives waypoints to pass in order on
    the way (a hint for big looping levels; the route is still checked only at its end).
    ``prefix``: saved rows to play first; the search continues from where they leave off, so a
    long level can be found segment by segment."""
    via = list(via or [])
    g = Game(seed=seed, difficulty=difficulty, level=level, remastered=mode == "remastered")
    if start is not None:
        place(g, start)
    if to is not None:
        points = [to]
    else:
        points = [(o.x, o.y) for o in g.world.objects if o.ctype.name == "NEXT_LEVEL"
                  and campaign.exit_level(o.aistate) == goal]
        if not points:
            raise SystemExit(f"{level} has no exit to {goal}")

    def h(game, wi: int = len(via)) -> int:
        p = game.player
        if wi < len(via):  # the next waypoint, then the rest of the way
            rest = [via[wi], *via[wi + 1:]]
            d = abs(p.x - rest[0][0]) + abs(p.y - rest[0][1])
            for (ax, ay), (bx, by) in zip(rest, rest[1:], strict=False):
                d += abs(ax - bx) + abs(ay - by)
            return d + min(abs(rest[-1][0] - x) + abs(rest[-1][1] - y) for x, y in points)
        return min(abs(p.x - x) + abs(p.y - y) for x, y in points)

    def advance(game, wi: int) -> int:
        p = game.player
        while wi < len(via) and abs(p.x - via[wi][0]) <= 32 and abs(p.y - via[wi][1]) <= 40:
            wi += 1
        return wi

    def done(game) -> bool:
        if to is not None:
            p = game.player
            return abs(p.x - to[0]) <= 24 and abs(p.y - to[1]) <= 24
        return finished(game, goal, mode)

    counter = itertools.count()
    start_rows: list = []
    if prefix:
        for n, x, y, special, fire, dx, dy in prefix:
            for _ in range(n):
                p = g.player
                g.step(Inputs(x=x, y=y, b1=special, b2=fire, pointer_x=p.x + dx, pointer_y=p.y - 20 + dy))
        start_rows = [list(r) for r in prefix]
    else:
        for _ in range(3):
            tick(g, 0, 0, 0, start_rows)
    frontier = [(h(g, 0), next(counter), g.snapshot(), start_rows, 0)]
    seen = {(key(g, cell), 0)}
    expanded = 0
    t0 = time.time()
    while frontier and expanded < budget:
        _, _, snap, rows, wi0 = heapq.heappop(frontier)
        expanded += 1
        for x, y, special, n in MACROS.values():
            g.restore(snap)
            new_rows = [r[:] for r in rows]
            hp0 = g.player.hp
            for _ in range(n or ticks):
                tick(g, x, y, special, new_rows)
                if done(g):
                    return new_rows, expanded, time.time() - t0
                if g.player_dead or g.world.globals.get("level_complete"):
                    break  # dead, or the level ended at another exit (the game would stop here)
            if g.world.globals.get("level_complete"):
                continue
            if g.player_dead or g.player.hp < min(hp0, 25):
                continue
            wi = advance(g, wi0)
            k = (key(g, cell), wi)
            if k in seen:
                continue
            seen.add(k)
            depth = sum(r[0] for r in new_rows)
            heapq.heappush(frontier, (h(g, wi) + depth // 4, next(counter), g.snapshot(), new_rows, wi))
        if expanded % 200 == 0:
            p = g.player
            print(f"  expanded {expanded}, frontier {len(frontier)}, seen {len(seen)}, "
                  f"last at ({p.x},{p.y}), {time.time() - t0:.0f}s", file=sys.stderr)
    return None, expanded, time.time() - t0


def finished(game, goal: str, mode: str = "remastered") -> bool:
    """The level ended at an exit to ``goal``: the next level is ``goal``, or, when ``goal``
    cannot be played (Level 2's exit to Level 3), the campaign ended there. In Classic, which
    has no campaign, the level ending is the finish."""
    w = game.world
    if not w.globals.get("level_complete"):
        return False
    if mode == "classic":
        return True
    return w.globals.get("next_level") == goal if campaign.playable(goal) else "next_level" not in w.globals


def place(g, start: tuple[int, int]) -> None:
    """Start at a restart console the way the agents' checkpoint scenarios do
    (``AbuseEpisode.reset``): a fresh level with the player and the camera moved there."""
    p, v = g.player, g.view
    p.x, p.y = start
    p.last_x, p.last_y = p.x, p.y
    v.last_x, v.last_y, v.last_last_x, v.last_last_y = p.x, p.y, p.x, p.y


def replay_route(route: dict) -> Game:
    """Play a saved route as the app would: it stops at the first tick that ends the level.
    Returns the game at that point (or after the last input)."""
    g = Game(seed=route["seed"], difficulty=route["difficulty"], level=route["level"],
             remastered=route.get("mode", "remastered") == "remastered")
    if route.get("start"):
        place(g, tuple(route["start"]))
    for n, x, y, special, fire, dx, dy in route["inputs"]:
        for _ in range(n):
            p = g.player
            g.step(Inputs(x=x, y=y, b1=special, b2=fire, pointer_x=p.x + dx, pointer_y=p.y - 20 + dy))
            if g.world.globals.get("level_complete"):
                return g
    return g


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--level", required=True, choices=campaign.LEVELS)
    ap.add_argument("--mode", choices=("remastered", "classic"), default="remastered")
    ap.add_argument("--goal", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", default="hard")
    ap.add_argument("--budget", type=int, default=20000, help="nodes to expand at most")
    ap.add_argument("--cell", type=int, default=24, help="position grid for novelty, in pixels")
    ap.add_argument("--ticks", type=int, default=6, help="ticks per macro")
    ap.add_argument("--to", help="X,Y: reach this point instead of an exit (to check a spot is reachable)")
    ap.add_argument("--via", help="X,Y;X,Y;...: waypoints to pass in order (a hint for looping levels)")
    ap.add_argument("--start", help="X,Y: start at this restart console, as a checkpoint scenario does")
    ap.add_argument("--prefix", type=Path, help="a saved route or reach file whose inputs are played first")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    to = tuple(int(v) for v in args.to.split(",")) if args.to else None
    via = [tuple(int(v) for v in p.split(",")) for p in args.via.split(";")] if args.via else None
    prefix = json.loads(args.prefix.read_text())["inputs"] if args.prefix else None
    start = tuple(int(v) for v in args.start.split(",")) if args.start else None
    rows, expanded, secs = search(args.level, args.goal, args.seed, args.difficulty, args.budget,
                                  args.cell, args.ticks, to, via, prefix, args.mode, start)
    if rows is None:
        print(f"no route found after {expanded} nodes ({secs:.0f}s)")
        return 1
    route = {"format": "campaign-route-1", "level": args.level, "goal": args.goal, "seed": args.seed,
             "difficulty": args.difficulty, "ticks": sum(r[0] for r in rows), "inputs": rows}
    if args.mode == "classic":
        route["mode"] = "classic"
    if start is not None:
        route["start"] = list(start)
    if via:
        route["via"] = [list(v) for v in via]
    if to is not None:
        route["format"], route["to"] = "campaign-reach-1", list(to)
    g = replay_route(route)
    if to is None:
        assert finished(g, args.goal, args.mode)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(route, separators=(",", ":")) + "\n")
    print(f"route found: {route['ticks']} ticks, {len(rows)} rows, {expanded} nodes, {secs:.0f}s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
