"""Memory conditions for the model-driven player, for the memory/history comparison.

- ``M0``: the current observation only.
- ``M1``: M0 plus the last 8 turns (action, result, health, position, events).
- ``M2``: M1 plus the model's own notes (at most 600 characters) and an automap summary.

Everything here is built from observations the player already received, so no condition
sees more of the game than the observations did. The automap summary is the text form of the
original's automap (``abuse/src/automap.c``): how far the player has seen, plus the objects it
saw that are now off screen, with their last known state.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .prompts import describe_event

CONDITIONS = ("M0", "M1", "M2")
HISTORY_TURNS = 8
NOTES_MAX = 600
REMEMBERED_MAX = 15


@dataclass
class Turn:
    tick: int
    action: object
    result: str = ""
    hp: int = 0
    x: int = 0
    y: int = 0
    events: str = ""


@dataclass
class Automap:
    x_min: int | None = None
    x_max: int | None = None
    y_min: int | None = None
    y_max: int | None = None
    objects: dict[str, dict] = field(default_factory=dict)

    def update(self, obs: dict) -> None:
        v = obs["view"]
        x0, y0, x1, y1 = v["x"], v["y"], v["x"] + v["w"] - 1, v["y"] + v["h"] - 1
        self.x_min = x0 if self.x_min is None else min(self.x_min, x0)
        self.x_max = x1 if self.x_max is None else max(self.x_max, x1)
        self.y_min = y0 if self.y_min is None else min(self.y_min, y0)
        self.y_max = y1 if self.y_max is None else max(self.y_max, y1)
        shown = {o["id"] for o in obs["objects"]}
        for oid in [k for k, o in self.objects.items() if k not in shown]:
            o = self.objects[oid]
            if x0 <= o["x"] <= x1 and y0 <= o["y"] <= y1:
                del self.objects[oid]  # its spot is on screen and it is gone: killed, picked up or moved
        for o in obs["objects"]:
            if o["kind"] == "projectile":
                continue
            self.objects[o["id"]] = {"kind": o["kind"], "x": o["x"], "y": o["y"], "state": o.get("state"),
                                     "tick": obs["tick"]}

    def render(self, obs: dict) -> str:
        p = obs["player"]
        shown = {o["id"] for o in obs["objects"]}
        away = [(k, o) for k, o in self.objects.items() if k not in shown]
        away.sort(key=lambda kv: abs(kv[1]["x"] - p["x"]) + abs(kv[1]["y"] - p["y"]))
        lines = [f"AUTOMAP (from what you have seen): explored x {self.x_min}..{self.x_max}, "
                 f"y {self.y_min}..{self.y_max}."]
        if away:
            lines.append("Objects you saw that are now off screen (nearest first; dx, dy from you now):")
            for k, o in away[:REMEMBERED_MAX]:
                state = f" {o['state']}" if o["state"] else ""
                lines.append(f"  {k} {o['kind']}{state} dx {o['x'] - p['x']:+d} dy {o['y'] - p['y']:+d} "
                             f"(seen at tick {o['tick']})")
            if len(away) > REMEMBERED_MAX:
                lines.append(f"  ... and {len(away) - REMEMBERED_MAX} more further away")
        return "\n".join(lines)


class Memory:
    def __init__(self, condition: str = "M1"):
        if condition not in CONDITIONS:
            raise ValueError(f"memory condition must be one of {CONDITIONS}")
        self.condition = condition
        self.turns: deque[Turn] = deque(maxlen=HISTORY_TURNS)
        self.pending: Turn | None = None
        self.notes = ""
        self.notes_truncated = 0
        self.automap = Automap()
        self._obs: dict | None = None

    @property
    def keeps_notes(self) -> bool:
        return self.condition == "M2"

    def observe(self, obs: dict) -> None:
        """Called with each new observation: closes the previous turn with its result."""
        if self.pending is not None:
            t = self.pending
            last = obs["last_result"]
            t.result = f"done, {last.get('ticks', 0)} ticks" if last.get("accepted") else \
                f"REFUSED ({last.get('error')})"
            t.hp, t.x, t.y = obs["player"]["hp"], obs["player"]["x"], obs["player"]["y"]
            t.events = "; ".join(describe_event(e) for e in obs["events"])
            self.turns.append(t)
            self.pending = None
        if self.condition == "M2":
            self.automap.update(obs)
        self._obs = obs

    def record(self, tick: int, action: object, notes: object = None) -> None:
        self.pending = Turn(tick=tick, action=action)
        if self.keeps_notes and isinstance(notes, str):
            self.notes_truncated += int(len(notes) > NOTES_MAX)
            self.notes = notes[:NOTES_MAX]

    def render(self) -> str:
        if self.condition == "M0" or self._obs is None:
            return ""
        parts = []
        if self.turns:
            lines = [f"YOUR LAST {len(self.turns)} TURNS (oldest first):"]
            for t in self.turns:
                act = t.action if isinstance(t.action, str) else f"<no valid action: {t.action!r}>"
                line = f"  tick {t.tick}: {act} -> {t.result}; then health {t.hp} at x {t.x} y {t.y}"
                if t.events:
                    line += f"; {t.events}"
                lines.append(line)
            parts.append("\n".join(lines))
        if self.condition == "M2":
            parts.append(self.automap.render(self._obs))
            parts.append("YOUR NOTES: " + (self.notes or "(empty)"))
        return "\n".join(parts)
