"""Remastered-only mechanics. They change rules, so they live behind ``--mode remastered``.

Classic mode never creates this object, and no fidelity test or evaluation runs with it
(AGENTS.md). The one hook into the Classic code is a flag in ``world.globals`` that is never set
in Classic mode: ``bottom_damage`` ignores damage while ``player_iframes`` is above zero.

The dash: a short burst along the ground or through the air in the direction you face (or are
pressing). It moves with the engine's own collision (``try_move`` with feet and head checks), so
it never passes through walls. The player cannot be hurt during the dash and for a few ticks
after it. It has a cooldown, so it is a dodge, not a faster way to run.

All state is in ``world.globals["remastered"]``, so snapshots and restarts carry it.
"""

from __future__ import annotations

DASH_TICKS = 4  # ticks of movement
DASH_SPEED = 13  # pixels per tick; running speed is about 6 to 7
DASH_IFRAMES = 7  # ticks without damage, counted from the start of the dash
DASH_COOLDOWN = 18  # ticks from the start of one dash to the next
NORMAL_PLAY = 1  # the cop's aistate in play (people.lsp; behaviors/player.py)


def _state(world) -> dict:
    st = world.globals.get("remastered")
    if st is None:
        st = world.globals["remastered"] = {"dash_left": 0, "dash_dir": 1, "iframes": 0, "cooldown": 0,
                                            "dashes": 0}
    return st


class Remastered:
    def __init__(self, game):
        self.game = game
        _state(game.world)

    @property
    def state(self) -> dict:
        return _state(self.game.world)

    def can_dash(self) -> bool:
        p = self.game.player
        return self.state["cooldown"] == 0 and p.aistate == NORMAL_PLAY and p.state not in ("dieing", "dead") \
            and not p.lvars.get("is_teleporting")

    def request_dash(self, direction: int = 0) -> bool:
        """Start a dash toward ``direction`` (-1 or 1), or the way the player faces if 0."""
        if not self.can_dash():
            return False
        st = self.state
        st["dash_dir"] = direction if direction in (-1, 1) else (1 if self.game.player.direction > 0 else -1)
        st["dash_left"] = DASH_TICKS
        st["iframes"] = DASH_IFRAMES
        st["cooldown"] = DASH_COOLDOWN
        st["dashes"] += 1
        p = self.game.player
        self.game.world.emit("dash", x=p.x, y=p.y, direction=st["dash_dir"])
        return True

    def before_step(self) -> None:
        self.game.world.globals["player_iframes"] = self.state["iframes"]

    def after_step(self) -> None:
        st = self.state
        p = self.game.player
        if st["dash_left"] > 0 and p.aistate == NORMAL_PLAY:
            _, xv, _ = p.try_move(p.x, p.y, DASH_SPEED * st["dash_dir"], 0, 3)
            p.x += xv
            p.direction = st["dash_dir"]
            st["dash_left"] -= 1
            if st["dash_left"] == 0 or xv == 0:
                st["dash_left"] = 0
                p.xvel = 0  # stop cleanly, without sliding
        st["iframes"] = max(0, st["iframes"] - 1)
        st["cooldown"] = max(0, st["cooldown"] - 1)
        self.game.world.globals["player_iframes"] = st["iframes"]
