"""Replay a human session trace (``abuse-remake --record`` or ``--playtest``) through the engine.

    uv run abuse-replay --human-trace playtests/raw/session-....jsonl

A trace (format ``human-trace-1``) is a header and then, for each game in the session:
- a ``new_game`` row (seed, difficulty, rules, horde and, for Remastered's campaign, the level);
- one ``input`` row per tick (the original controls, weapon keys and Remastered dash requests);
- ``restore`` rows (to the last console save or the level start);
- a ``level`` row when Remastered's campaign goes on into the next level, keeping the player
  (``Game(carry=...)``); each level is reported as its own game. The replay checks that the
  level before really ended at an exit leading there; a level row that does not follow such an
  exit is counted in ``unverified_level_changes`` and fails the replay like a mismatch;
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
from ..engine import campaign
from ..engine.game import Game, WeaponCommand
from ..engine.view import Inputs


class _Session:
    def __init__(self, row: dict, carry: Game | None = None):
        self.row = row
        self.rules = row.get("rules", "classic")
        self.horde = bool(row.get("horde"))
        self.level = row.get("level", "level01")
        self.game = Game(seed=row["seed"], difficulty=row.get("difficulty", "hard"), level=self.level,
                         remastered=self.rules == "remastered", horde=self.horde, carry=carry)
        self.game.world.globals["save_hook"] = self._save
        self.level_start = self.game.snapshot()
        self.checkpoint = self.level_start
        p = self.game.player
        # the evaluator's progress measure is defined on a fresh start of Level 1 only
        fresh_level01 = not self.horde and self.level == "level01" and carry is None
        self.tracker = ProgressTracker(p.x, p.y) if fresh_level01 else None
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

    def next_level(self, name: str) -> _Session:
        return _Session({**self.row, "level": name}, carry=self.game)

    def restore(self, to: str) -> None:
        snap = self.level_start if to == "level_start" else self.checkpoint
        self.game.restore(snap)
        if snap is self.level_start:
            campaign.restart_health(self.game)
        if to == "level_start":
            self.checkpoint = self.level_start
        self.dead = False

    def summary(self) -> dict:
        out = {"seed": self.seed, "rules": self.rules, "horde": self.horde, "level": self.level, "ticks": self.ticks,
               "deaths": self.deaths, "console_saves": self.saves, "reached_exit": self.won}
        if self.tracker is not None:
            out["progress"] = round(self.tracker.value(self.won), 4)
        return out


def replay_human(path: Path) -> dict:
    rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    if not rows or rows[0].get("kind") != "header" or rows[0].get("format") != "human-trace-1":
        raise SystemExit(f"{path}: not a human trace (format human-trace-1)")
    games: list[dict] = []
    session: _Session | None = None
    checks = mismatches = unverified = 0
    for row in rows[1:]:
        kind = row.get("kind")
        if kind == "new_game":
            if session is not None and session.ticks:
                games.append(session.summary())
            session = _Session(row)
        elif session is None:
            continue
        elif kind == "input":
            session.step(row)
        elif kind == "level":
            w = session.game.world
            unverified += int(not (session.won and w.globals.get("next_level") == row["level"]))
            games.append(session.summary())
            session = session.next_level(row["level"])
        elif kind == "restore":
            session.restore(row.get("to", "checkpoint"))
        elif kind == "check":
            checks += 1
            mismatches += int(session.game.state_hash() != row.get("state_hash"))
    if session is not None and session.ticks:
        games.append(session.summary())
    return {"games": games, "checks": checks, "mismatches": mismatches, "unverified_level_changes": unverified}
