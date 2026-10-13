"""The playing agent's interface: five operations over one Level 1 episode.

A player uses ``observe``, ``legal_actions`` and ``step``. The runner uses ``reset`` and
``outcome`` and holds the episode. Players normally run in a separate process
(``agent/protocol.py``) and receive only JSON, so they cannot reach the World object, the
level files, the rule map, the random table or credentials.

Actions (docs/action-interface.md) are strings taken from ``legal_actions()``:

    wait                      hold still for 8 ticks
    move left | move right    run for 6 ticks
    jump | jump left | jump right
    explore left | explore right    walk toward the unexplored edge of the automap (<= 15 ticks)
    goto <ID>                 walk to a visible object using the automap (<= 15 ticks)
    use <ID>                  walk to a switch, console, teleporter, lift or the exit and press down
    attack <ID>               aim at a visible target and fire (<= 12 ticks)
    weapon <name>             switch weapon (1 tick)

Each action runs a deterministic controller that turns it into the original's inputs (left,
right, up, down, fire, aim) for up to 15 ticks. It stops early when the player is hurt or a
new threat appears, so the agent can react. Every player gets exactly the same controllers.

Invalid actions: anything not in ``legal_actions()`` (unparsable, unknown, a target not on
screen, a weapon without ammo, or a reply that is not a string) is refused. The game does not
advance, the refusal is counted, one decision is spent, and the reason goes back in
``last_result``. Nothing is repaired and nothing is substituted.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass

from ..engine.cmath import cdiv
from ..engine.game import Game, WeaponCommand
from ..engine.view import Inputs
from ..scope import FULL_LEVEL_TICK_LIMIT, SEGMENT_TICK_LIMIT
from .nav import KnownMap, Navigator, blocked_cells, cell_of
from .observation import WEAPON_NAMES, IdMap, build_observation, view_rect

PLAYER_ID = "player"
INTERACTIVE = {"switch", "console", "teleporter", "door_teleporter", "exit", "lift"}
TARGETABLE = {"alien", "turret", "boulder", "wall_block", "nest"}
THREATS = {"alien", "turret", "boulder", "rock", "projectile"}
GOTO_KINDS = {"health", "ammo_laser", "ammo_grenade", "ammo_rocket", "ammo_firebomb", "switch", "console",
              "teleporter", "door_teleporter", "exit", "lift", "door", "wall_block", "alien", "turret", "nest"}


@dataclass
class Budgets:
    max_ticks: int = FULL_LEVEL_TICK_LIMIT
    max_decisions: int = 600
    max_action_ticks: int = 15


@dataclass(frozen=True)
class Scenario:
    name: str
    start: tuple[int, int] | None  # None = the level's START; otherwise a restart console position
    max_ticks: int


SCENARIOS = {
    "level01": Scenario("level01", None, FULL_LEVEL_TICK_LIMIT),
    "level01-cp1": Scenario("level01-cp1", (81, 111), SEGMENT_TICK_LIMIT),
    "level01-cp2": Scenario("level01-cp2", (841, 828), SEGMENT_TICK_LIMIT),
    "level01-cp3": Scenario("level01-cp3", (1413, 639), SEGMENT_TICK_LIMIT),
}


class AbuseEpisode:
    def __init__(self, scenario: str = "level01", seed: int = 0, difficulty: str = "hard",
                 budgets: Budgets | None = None):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIOS)}")
        self.scenario = SCENARIOS[scenario]
        self.difficulty = difficulty
        self.budgets = budgets or Budgets(max_ticks=self.scenario.max_ticks)
        self.reset(seed)

    # --- runner operations -------------------------------------------------------------
    def reset(self, seed: int | None = None) -> dict:
        self.seed = self.seed if seed is None else seed
        self._game = Game(seed=self.seed, difficulty=self.difficulty)
        if self.scenario.start is not None:
            p = self._game.player
            p.x, p.y = self.scenario.start
            p.last_x, p.last_y = p.x, p.y
            v = self._game.view
            v.last_x, v.last_y, v.last_last_x, v.last_last_y = p.x, p.y, p.x, p.y
        self._ids = IdMap()
        self._known = KnownMap()
        self.ticks = 0
        self.decisions = 0
        self.invalid_actions = 0
        self.events: list = []
        self.counters = {"kills": 0, "damage_taken": 0, "pickups": 0, "walls": 0, "checkpoints": 0,
                         "shots_fired": 0, "teleports": 0}
        self._last_result = {"accepted": True, "action": None, "error": None}
        self._pending_events: list = []
        self._reveal()
        return self.observe(PLAYER_ID)

    def outcome(self) -> dict:
        status, reason = self._status()
        return {"status": "terminal" if status != "playing" else "ongoing", "reason": reason,
                "score": 1 if status == "won" else 0, "ticks": self.ticks, "decisions": self.decisions,
                "invalid_actions": self.invalid_actions, "hp": self._game.player.hp,
                "x": self._game.player.x, "y": self._game.player.y, **self.counters}

    # --- player operations -------------------------------------------------------------
    def observe(self, player_id: str) -> dict:
        _check_player(player_id)
        status, _ = self._status()
        obs = build_observation(self._game, self._ids, self._pending_events, self.ticks,
                                self.budgets.max_ticks - self.ticks, status, self._last_result)
        return json.loads(json.dumps(obs))  # a detached copy: no references into the game

    def legal_actions(self, player_id: str) -> list[str]:
        _check_player(player_id)
        if self._status()[0] != "playing":
            return []
        obs = build_observation(self._game, self._ids, [], self.ticks, 0, "playing", None)
        acts = ["wait", "move left", "move right", "jump", "jump left", "jump right",
                "explore left", "explore right"]
        v = self._game.view
        for i, name in enumerate(WEAPON_NAMES[: v.total_weapons]):
            if i != v.current_weapon and v.weapons[i] != -1 and (i == 0 or v.weapons[i] > 0):
                acts.append(f"weapon {name}")
        for o in obs["objects"]:
            if o["kind"] in TARGETABLE:
                acts.append(f"attack {o['id']}")
            if o["kind"] in GOTO_KINDS:
                acts.append(f"goto {o['id']}")
            if o["kind"] in INTERACTIVE:
                acts.append(f"use {o['id']}")
        return acts

    def step(self, player_id: str, action: object) -> dict:
        _check_player(player_id)
        if self._status()[0] != "playing":
            return {"accepted": False, "error": "episode is over", "ticks": 0,
                    "observation": self.observe(player_id)}
        if self.decisions >= self.budgets.max_decisions:
            return {"accepted": False, "error": "decision budget exhausted", "ticks": 0,
                    "observation": self.observe(player_id)}
        self.decisions += 1
        if not isinstance(action, str):
            return self._refuse(f"<not text: {type(action).__name__}>", "action must be a string")
        action = " ".join(action.strip().lower().split())
        legal = self.legal_actions(player_id)
        legal_lc = {a.lower(): a for a in legal}
        if action not in legal_lc:
            reason = "not in legal_actions" if action else "empty action"
            return self._refuse(action, reason)
        canonical = legal_lc[action]
        self._pending_events = []
        ticks = self._execute(canonical)
        self._last_result = {"accepted": True, "action": canonical, "error": None, "ticks": ticks}
        return {"accepted": True, "error": None, "ticks": ticks, "observation": self.observe(player_id)}

    # --- internals ---------------------------------------------------------------------
    def _refuse(self, action: str, reason: str) -> dict:
        self.invalid_actions += 1
        self._last_result = {"accepted": False, "action": action[:200], "error": reason, "ticks": 0}
        return {"accepted": False, "error": reason, "ticks": 0, "observation": self.observe(PLAYER_ID)}

    def _status(self) -> tuple[str, str]:
        g = self._game
        if g.world.globals.get("level_complete"):
            return "won", "reached the exit"
        if g.player.aistate >= 2 or g.player.hp == 0:
            return "dead", "player died"
        if self.ticks >= self.budgets.max_ticks:
            return "timeout", "tick limit"
        if self.decisions >= self.budgets.max_decisions:
            return "budget", "decision budget exhausted"
        return "playing", ""

    def _reveal(self) -> None:
        self._known.reveal(*view_rect(self._game))

    def _visible(self) -> dict:
        x0, y0, w, h = view_rect(self._game)
        from .observation import visible_objects

        return {o["id"]: o for o in visible_objects(self._game, self._ids, x0, y0, w, h)}

    def _tick(self, inputs: Inputs, weapon: WeaponCommand | None = None) -> None:
        g = self._game
        hp = g.player.hp
        g.step(inputs, weapon)
        self.ticks += 1
        self._reveal()
        for e in g.world.events:
            self._pending_events.append(e)
            k = e.kind
            if k == "enemy_killed":
                self.counters["kills"] += 1
            elif k == "pickup":
                self.counters["pickups"] += 1
            elif k == "wall_destroyed":
                self.counters["walls"] += 1
            elif k == "checkpoint_saved":
                self.counters["checkpoints"] += 1
            elif k == "teleported":
                self.counters["teleports"] += 1
            elif k == "sound" and e.data["name"] == "ZAP_SND":
                self.counters["shots_fired"] += 1
        self.counters["damage_taken"] += max(0, hp - g.player.hp)

    def _aim_forward(self) -> tuple[int, int]:
        p = self._game.player
        return p.x + (100 if p.direction > 0 else -100), p.y - 20

    def _execute(self, action: str) -> int:
        parts = action.split()
        verb = parts[0]
        arg = parts[1] if len(parts) > 1 else None
        start_ticks = self.ticks
        limit = self.budgets.max_action_ticks
        visible_before = {k for k, o in self._visible().items() if o["kind"] in THREATS}
        if verb == "weapon":
            idx = WEAPON_NAMES.index(arg)
            px, py = self._aim_forward()
            self._tick(Inputs(pointer_x=px, pointer_y=py), WeaponCommand(select=idx) if idx else WeaponCommand(cycle=0))
            if idx == 0:
                self._game.view.pending_weapon = 0
            return self.ticks - start_ticks
        controller = {"wait": self._c_wait, "move": self._c_move, "jump": self._c_jump,
                      "explore": self._c_explore, "goto": self._c_goto, "use": self._c_use,
                      "attack": self._c_attack}[verb]
        gen = controller(arg)
        hp0 = self._game.player.hp
        for _ in range(limit):
            if self._status()[0] != "playing":
                break
            try:
                inp = next(gen)
            except StopIteration:
                break
            self._tick(inp)
            if self._game.player.hp < hp0:
                break  # hurt: give control back
            threats = {k for k, o in self._visible().items() if o["kind"] in THREATS}
            if threats - visible_before and verb not in ("attack",):
                break  # something new and dangerous came into view
        if self.ticks == start_ticks and self._status()[0] == "playing":
            px, py = self._aim_forward()
            self._tick(Inputs(pointer_x=px, pointer_y=py))  # every accepted action takes at least a tick
        return self.ticks - start_ticks

    # --- controllers (generators of Inputs) ------------------------------------------------
    def _c_wait(self, _):
        for _ in range(8):
            px, py = self._aim_forward()
            yield Inputs(pointer_x=px, pointer_y=py)

    def _c_move(self, d):
        x = 1 if d == "right" else -1
        for _ in range(6):
            p = self._game.player
            yield Inputs(x=x, pointer_x=p.x + 100 * x, pointer_y=p.y - 20)

    def _c_jump(self, d):
        x = {"left": -1, "right": 1}.get(d, 0)
        p = self._game.player
        yield Inputs(x=x, y=-1, pointer_x=p.x + 100 * (x or p.direction), pointer_y=p.y - 20)
        for _ in range(14):
            p = self._game.player
            if not p.gravity():
                return
            yield Inputs(x=x, pointer_x=p.x + 100 * (x or p.direction), pointer_y=p.y - 20)

    def _nav(self) -> Navigator:
        return Navigator(self._game.world.tiles, self._known, blocked_cells(self._visible().values()))

    def _follow(self, goal_cell, press_at_end: bool = False, close_px: int = 8, target_x: int | None = None):
        """Walk along an A* path over the automap toward goal_cell (and target_x, if given)."""
        for _ in range(self.budgets.max_action_ticks):
            p = self._game.player
            nav = self._nav()
            start = nav.nearest_standable(*cell_of(p.x, p.y))
            gc, gr = goal_cell
            goal = nav.nearest_standable(gc, gr, radius=4)
            if start is None or goal is None:
                return
            path = nav.plan(start, lambda n, g=goal: 0 if n == g else abs(n[0] - g[0]) + abs(n[1] - g[1]))
            if path is None:
                return
            tx_goal = target_x if target_x is not None else goal[0] * 30 + 15
            near_row = cell_of(p.x, p.y)[1] in (goal[1] - 1, goal[1], goal[1] + 1)
            if len(path) == 1 or (len(path) <= 2 and near_row):
                if abs(p.x - tx_goal) > close_px and not p.gravity():
                    x = 1 if tx_goal > p.x else -1
                    yield Inputs(x=x, pointer_x=p.x + 100 * x, pointer_y=p.y - 20)
                    continue
                if press_at_end:
                    for _ in range(2):
                        yield Inputs(y=1, pointer_x=p.x + 100 * p.direction, pointer_y=p.y - 20)
                    yield Inputs(pointer_x=p.x + 100 * p.direction, pointer_y=p.y - 20)
                return
            # aim for the first node ahead that needs a horizontal move (slopes step up a row
            # while staying in the same column), and jump if any edge on the way is a jump
            i = 1
            while i < len(path) - 1 and abs(path[i][0][0] * 30 + 15 - p.x) < 6 and path[i][1] != "jump":
                i += 1
            (nc, nr), kind = path[i]
            tx = nc * 30 + 15
            dx = tx - p.x
            x = 0 if abs(dx) < 4 else (1 if dx > 0 else -1)
            y = 0
            if kind == "jump" and not p.gravity():
                y = -1
                if x == 0:
                    x = 1 if nc > start[0] else (-1 if nc < start[0] else 0)
            elif x == 0 and nr < cell_of(p.x, p.y)[1] - 1 and not p.gravity():
                y = -1  # the next node is above us: hop up
            yield Inputs(x=x, y=y, pointer_x=p.x + 100 * (x or p.direction), pointer_y=p.y - 20)

    def _c_goto(self, oid):
        o = self._visible().get(oid)
        if o is None:
            return
        yield from self._follow(cell_of(o["x"], o["y"]), target_x=o["x"])

    def _c_use(self, oid):
        o = self._visible().get(oid)
        if o is None:
            return
        yield from self._follow(cell_of(o["x"], o["y"]), press_at_end=True, close_px=10, target_x=o["x"])

    def _c_explore(self, d):
        nav = self._nav()
        p = self._game.player
        start = nav.nearest_standable(*cell_of(p.x, p.y))
        reach = nav.reachable(start)
        if not reach:
            return
        sign = 1 if d == "right" else -1
        frontier = [n for n in reach if nav.is_frontier(n)]
        pool = frontier or list(reach)
        best = max(pool, key=lambda n: (sign * n[0], -reach[n]))
        if sign * (best[0] - (start[0] if start else 0)) <= 0:
            # nothing further that way: just run in that direction
            yield from self._c_move(d)
            return
        yield from self._follow(best)

    def _c_attack(self, oid):
        for _ in range(12):
            o = self._visible().get(oid)
            if o is None:
                return
            p = self._game.player
            g = self._game.world
            tgt = next((t for t in g.objects if self._ids.labels.get(t.uid) == oid and not t.deleted), None)
            if tgt is None:
                return
            ty = tgt.y - cdiv(tgt.picture_height(), 2)
            face = 1 if tgt.x > p.x else -1
            x = face if p.direction != face else 0  # turn to face the target, then stand still
            yield Inputs(x=x, b2=1, pointer_x=tgt.x, pointer_y=ty)

    # --- traces ------------------------------------------------------------------------
    def snapshot_for_trace(self) -> dict:
        return {"seed": self.seed, "scenario": self.scenario.name, "difficulty": self.difficulty,
                "budgets": asdict(self.budgets)}


def _check_player(player_id: str) -> None:
    if player_id != PLAYER_ID:
        raise ValueError(f"Abuse Level 1 has one player, {PLAYER_ID!r}.")


__all__ = ["AbuseEpisode", "Budgets", "SCENARIOS", "PLAYER_ID", "copy"]
