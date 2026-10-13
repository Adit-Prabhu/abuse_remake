"""Replay a human session trace (``abuse-remake --record`` or ``--playtest``) through the engine.

    uv run abuse-replay --human-trace playtests/raw/session-....jsonl

A trace (format ``human-trace-1``) is a header and then, for each game in the session:
- a ``new_game`` row (seed, difficulty, rules, horde);
- one ``input`` row per tick (the original controls, weapon keys and Remastered dash requests);
- ``restore`` rows (to the last console save or the level start);
- ``check`` rows holding the state hash at deaths, the level's end, restores and the session's end.

The replay makes the same console saves the game made (the engine calls the save hook at the
same moment), so restores land in the same place. Every ``check`` must match. Each game is
scored with the evaluator's progress measure (``agent/progress.py``), so a human playtest can be
set next to the agents' results. Unlike an agent episode, a human may die and restart.
No pygame is needed.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..agent.progress import ProgressTracker
from ..engine.game import Game, WeaponCommand
from ..engine.view import Inputs


class _Session:
    def __init__(self, row: dict):
        self.rules = row.get("rules", "classic")
        self.horde = bool(row.get("horde"))
        self.game = Game(seed=row["seed"], difficulty=row.get("difficulty", "hard"),
                         remastered=self.rules == "remastered", horde=self.horde)
        self.game.world.globals["save_hook"] = self._save
        self.level_start = self.game.snapshot()
        self.checkpoint = self.level_start
        p = self.game.player
        self.tracker = None if self.horde else ProgressTracker(p.x, p.y)
        self.ticks = 0
        self.deaths = 0
        self.dead = False
        self.saves = 0
        self.won = False
        self.seed = row["seed"]

    def _save(self, console) -> None:
        self.checkpoint = self.game.snapshot()
        self.saves += 1

    def step(self, row: dict) -> None:
        g = self.game
        if row.get("dash") and g.remastered is not None:
            g.remastered.request_dash(row.get("x", 0))
        w = row.get("weapon")
        weapon = WeaponCommand(select=w.get("select"), cycle=w.get("cycle", 0)) if w else None
        g.step(Inputs(x=row["x"], y=row["y"], b1=row["b1"], b2=row["b2"], pointer_x=row["px"], pointer_y=row["py"]),
               weapon)
        self.ticks += 1
        if self.tracker is not None:
            self.tracker.update(g.player.x, g.player.y)
        if g.player.aistate >= 3 and not self.dead:
            self.deaths += 1
            self.dead = True
        if g.world.globals.get("level_complete"):
            self.won = True

    def restore(self, to: str) -> None:
        self.game.restore(self.level_start if to == "level_start" else self.checkpoint)
        if to == "level_start":
            self.checkpoint = self.level_start
        self.dead = False

    def summary(self) -> dict:
        out = {"seed": self.seed, "rules": self.rules, "horde": self.horde, "ticks": self.ticks,
               "deaths": self.deaths, "console_saves": self.saves, "reached_exit": self.won}
        if self.tracker is not None:
            out["progress"] = round(self.tracker.value(self.won), 4)
        return out


class _NeonSession:
    """Replay Neon Protocol (``neon-trace-2``), without Classic route scoring or pygame.

    A save console and the start of every campaign sector are checkpoints, as in the game, and
    the start of the current sector is where "restart sector" (``level_start``) goes.
    """

    def __init__(self, row):
        from ..engine.neon import NeonGame

        if "sector" not in row:
            raise SystemExit("a Neon Protocol v1 game in this trace; v1 was replaced, so it cannot be replayed")
        self.game = NeonGame(row["seed"], row["variant"], row.get("difficulty", "hard"), row.get("sector", 0))
        self.level_start = self.game.snapshot()
        self.checkpoint = self.level_start
        self.ticks, self.deaths, self.saves = 0, 0, 0
        self.won = False

    def step(self, row):
        from ..engine.neon import NeonInput

        g = self.game
        g.step(NeonInput(x=row["x"], y=row["y"], jump=bool(row.get("jump")), fire=bool(row.get("fire")),
                         dash=bool(row.get("dash")), interact=bool(row.get("interact")),
                         px=row["px"], py=row["py"]),
               select=row.get("select"), cycle=row.get("cycle", 0), upgrade=row.get("upgrade"))
        self.ticks += 1
        for e in g.events:
            if e["kind"] in ("checkpoint", "sector_start"):
                self.checkpoint = g.snapshot()
                self.saves += e["kind"] == "checkpoint"
            if e["kind"] == "sector_start":
                self.level_start = self.checkpoint
        self.deaths += int(g.status == "dead")
        self.won |= g.status == "won"

    def restore(self, to):
        self.game.restore(self.level_start if to == "level_start" else self.checkpoint)
        if to == "level_start":
            self.checkpoint = self.level_start

    def summary(self):
        g = self.game
        return {"rules": "neon", "seed": g.seed, "variant": g.variant, "ticks": self.ticks,
                "deaths": self.deaths, "console_saves": self.saves, "reached_exit": self.won,
                "sector": g.sector, "kills": g.kills,
                "waves_cleared": g.horde.cleared if g.horde is not None else 0}


def replay_human(path: Path) -> dict:
    rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    if rows and rows[0].get("format") == "neon-trace-1":
        raise SystemExit(f"{path}: a Neon Protocol v1 trace; v1 was replaced, so it cannot be replayed")
    if (not rows or rows[0].get("kind") != "header"
            or rows[0].get("format") not in ("human-trace-1", "neon-trace-2")):
        raise SystemExit(f"{path}: not a human trace (format human-trace-1 or neon-trace-2)")
    games: list[dict] = []
    session: _Session | _NeonSession | None = None
    checks = mismatches = 0
    for row in rows[1:]:
        kind = row.get("kind")
        if kind == "new_game":
            if session is not None and session.ticks:
                games.append(session.summary())
            session = _NeonSession(row) if row.get("rules") == "neon" else _Session(row)
        elif session is None:
            continue
        elif kind == "input":
            session.step(row)
        elif kind == "restore":
            session.restore(row.get("to", "checkpoint"))
        elif kind == "check":
            checks += 1
            mismatches += int(session.game.state_hash() != row.get("state_hash"))
    if session is not None and session.ticks:
        games.append(session.summary())
    return {"games": games, "checks": checks, "mismatches": mismatches}
