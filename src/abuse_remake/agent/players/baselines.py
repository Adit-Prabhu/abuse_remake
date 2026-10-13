"""Baseline players: a random floor and the scripted baseline.

Both use only the observation and the legal actions; they import nothing from the engine.

Scripted baseline: priority rules over the legal actions, with the automap search (A*) inside
the ``goto``, ``use`` and ``explore`` skills providing the search part.
1. Fight: attack the nearest visible threat (an alien not hanging, an active turret, or a
   boulder) within 220 px.
2. Heal: below 50 HP, go to visible health.
3. Exit: use the exit if it is on screen.
4. Save: use a restart console once.
5. Switches: use each visible switch that is off, once.
6. Supplies: pick up ammo within 250 px.
7. Break through: attack a wall block that is close ahead, or when stuck.
8. Teleport: use a teleporter not used recently, when stuck.
9. Otherwise explore in the current direction, turning around when no progress is made.
"""

from __future__ import annotations

import random
import sys

from ..protocol import serve

THREAT_KINDS = {"alien", "turret", "boulder"}


class RandomPlayer:
    """Uniform choice among the legal actions: the floor every player should beat."""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def start(self, info: dict) -> None:
        self.rng = random.Random(info.get("seed", 0))

    def decide(self, observation: dict, legal_actions: list[str]) -> dict:
        return {"action": self.rng.choice(legal_actions) if legal_actions else "wait"}

    def end(self, outcome: dict) -> None:
        pass


class ScriptedPlayer:
    def __init__(self):
        self.used: set[str] = set()
        self.direction = "right"
        self.history: list[int] = []
        self.stuck = 0
        self.teleported_at = -10_000
        self.attacks: dict[str, int] = {}  # consecutive attacks on a target that did not change it
        self.last_attack: tuple[str, bool] | None = None
        self.approach: dict[str, tuple[int, int]] = {}  # target -> (best distance, tries without improving)
        self.given_up: set[str] = set()

    def start(self, info: dict) -> None:
        self.__init__()

    def end(self, outcome: dict) -> None:
        pass

    def decide(self, obs: dict, legal: list[str]) -> dict:
        legal_set = set(legal)
        p = obs["player"]
        objs = obs["objects"]
        self.history.append(p["x"])
        moved = abs(self.history[-1] - self.history[-5]) if len(self.history) >= 5 else 999
        self.stuck = self.stuck + 1 if moved < 20 else 0

        seen = {o["id"]: o for o in objs}
        if self.last_attack is not None:
            tid, damaged_before = self.last_attack
            o = seen.get(tid)
            if o is not None and o.get("damaged", False) == damaged_before:
                self.attacks[tid] = self.attacks.get(tid, 0) + 1
            else:
                self.attacks.pop(tid, None)
            self.last_attack = None

        def reachable(o) -> bool:
            if o["id"] in self.given_up:
                return False
            best, tries = self.approach.get(o["id"], (10**9, 0))
            if o["dist"] < best - 4:
                self.approach[o["id"]] = (o["dist"], 0)
            elif tries >= 3:
                self.given_up.add(o["id"])
                return False
            return True

        def pick(action, why):
            verb, _, tid = action.partition(" ")
            if verb in ("goto", "use") and tid:
                best, tries = self.approach.get(tid, (seen.get(tid, {}).get("dist", 10**9), 0))
                self.approach[tid] = (min(best, seen.get(tid, {}).get("dist", best)), tries + 1)
            if action.startswith("attack "):
                tid = action.split()[1]
                self.last_attack = (tid, seen.get(tid, {}).get("damaged", False))
            return {"action": action, "note": why}

        def can_attack(o):
            limit = 3 if o["kind"] == "wall_block" else 6
            return f"attack {o['id']}" in legal_set and self.attacks.get(o["id"], 0) < limit

        # 1. fight
        threats = [o for o in objs if o["kind"] in THREAT_KINDS and o["dist"] < 220
                   and o.get("state") not in ("hanging", "folded", "dying")]
        for o in threats:
            if can_attack(o):
                return pick(f"attack {o['id']}", f"threat {o['kind']} at {o['dist']} px")
        # 2. heal
        if p["hp"] < 50:
            for o in objs:
                if o["kind"] == "health" and f"goto {o['id']}" in legal_set and reachable(o):
                    return pick(f"goto {o['id']}", "low health")
        # 3. exit
        for o in objs:
            if o["kind"] == "exit" and f"use {o['id']}" in legal_set and reachable(o):
                return pick(f"use {o['id']}", "exit in sight")
        # 4. save once
        for o in objs:
            if o["kind"] == "console" and o["id"] not in self.used and f"use {o['id']}" in legal_set \
                    and reachable(o):
                self.used.add(o["id"])
                return pick(f"use {o['id']}", "save at console")
        # 5. switches
        for o in objs:
            if o["kind"] == "switch" and o.get("state") == "off" and o["id"] not in self.used \
                    and f"use {o['id']}" in legal_set and reachable(o):
                self.used.add(o["id"])
                return pick(f"use {o['id']}", "try switch")
        # 6. supplies
        for o in objs:
            if o["kind"].startswith("ammo") and o["dist"] < 250 and f"goto {o['id']}" in legal_set \
                    and reachable(o):
                return pick(f"goto {o['id']}", "pick up ammo")
        # 7. break through walls ahead or when stuck
        sign = 1 if self.direction == "right" else -1
        walls = [o for o in objs if o["kind"] == "wall_block" and abs(o["dy"]) < 50
                 and (o["dx"] * sign > 0 or self.stuck >= 2) and o["dist"] < (90 if self.stuck < 2 else 200)]
        for o in walls:
            if can_attack(o):
                return pick(f"attack {o['id']}", "break through")
        # 8. teleport when stuck
        if self.stuck >= 3 and obs["tick"] - self.teleported_at > 600:
            for o in objs:
                if o["kind"] in ("teleporter", "door_teleporter") and f"use {o['id']}" in legal_set \
                        and reachable(o):
                    self.teleported_at = obs["tick"]
                    self.stuck = 0
                    return pick(f"use {o['id']}", "stuck: try teleporter")
        # 9. explore, turning around when stuck
        if self.stuck >= 4:
            self.direction = "left" if self.direction == "right" else "right"
            self.stuck = 0
            return pick(f"jump {self.direction}", "stuck: turn around")
        if self.stuck >= 2:
            return pick(f"jump {self.direction}", "stuck: jump")
        return pick(f"explore {self.direction}", "explore")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    kind = argv[0] if argv else "scripted"
    policy = RandomPlayer() if kind == "random" else ScriptedPlayer()
    return serve(policy)


if __name__ == "__main__":
    sys.exit(main())
