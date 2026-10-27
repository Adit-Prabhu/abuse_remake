"""Remastered-only mechanics. They change rules, so they live behind ``--mode remastered``.

Classic mode never creates this object, and no fidelity test or evaluation runs with it
(AGENTS.md). It touches the Classic code in two places, both through ``world.globals``:
``bottom_damage`` ignores damage while ``player_iframes`` is above zero, and the campaign
(``_follow_exits``) may keep a level going after its exit sets ``level_complete``, when that exit
leads to a level that cannot be played and another exit can. Level 1's exit is never kept shut.
Horde (``horde.py``) adds a third: ``World.activate_for_views`` also activates
``world.globals["awake_area"]``, the whole arena, which only Horde sets.

The dash: a short burst along the ground or through the air in the direction you face (or are
pressing). It moves with the engine's own collision (``try_move`` with feet and head checks), so
it never passes through walls. The player cannot be hurt during the dash and for a few ticks
after it. It has a cooldown, so it is a dodge, not a faster way to run.

Developer test mode (``Game(dev=True)``, the student's testing tool; the app unlocks it only
with a local key, ``game/devmode.py``): with ``dev["health"]`` the player takes no damage (the
same ``player_iframes`` check as the dash) and health stays at its cap; with ``dev["ammo"]`` guns
1-4 (laser, grenades, rockets, napalm) are owned and kept at ``MAX_AMMO``. Both are refilled before
and after every tick. The later add-on weapons in slots 5-7 are not ported, so they are never
given.

All state is in ``world.globals["remastered"]``, so snapshots and restarts carry it.
"""

from __future__ import annotations

DASH_TICKS = 4  # ticks of movement
DASH_SPEED = 13  # pixels per tick; running speed is about 6 to 7
DASH_IFRAMES = 7  # ticks without damage, counted from the start of the dash
DASH_COOLDOWN = 18  # ticks from the start of one dash to the next
NORMAL_PLAY = 1  # the cop's aistate in play (people.lsp; behaviors/player.py)
DEV_GUNS = 4  # the laser, grenades, rockets and napalm: the weapons Level 1 has


def _state(world) -> dict:
    st = world.globals.get("remastered")
    if st is None:
        st = world.globals["remastered"] = {"dash_left": 0, "dash_dir": 1, "iframes": 0, "cooldown": 0,
                                            "dashes": 0}
    return st


class Remastered:
    def __init__(self, game, dev: bool = False):
        self.game = game
        st = _state(game.world)
        if dev:
            st["dev"] = {"health": True, "ammo": True}
        # Built once per Game, on its freshly loaded level (restores copy the world instead);
        # a Horde arena keeps only the map, so it gets no campaign extras
        from .campaign import EXTRA_OBJECTS

        if getattr(game, "horde_arena", None) is None:
            for kind, x, y in EXTRA_OBJECTS.get(getattr(game, "level", None), ()):
                game.world.spawn(kind, x, y)

    @property
    def state(self) -> dict:
        return _state(self.game.world)

    @property
    def dev(self) -> dict | None:
        """Developer test mode's switches, or None in a normal game."""
        return self.state.get("dev")

    def dev_supplies(self) -> None:
        dev = self.dev
        if not dev:
            return
        from .behaviors.player import HEALTH_POWER
        from .view import MAX_AMMO

        p, v = self.game.player, self.game.view
        if dev["health"]:
            self.game.world.globals["player_iframes"] = 1  # bottom_damage ignores every hit
            if p.aistate == NORMAL_PLAY:
                p.set_hp(200 if p.lvars.get("special_power") == HEALTH_POWER else 100)
        if dev["ammo"]:
            for wtype in range(DEV_GUNS):
                v.give_weapon(wtype)
                v.add_ammo(wtype, MAX_AMMO)

    def dev_power(self, power: int) -> None:
        """Developer test mode's menu: carry ``power`` (0 drops it), as a power-up pickup gives one
        (``campaign_objects._take_power``), from a fresh start."""
        from .behaviors.player import HEALTH_POWER, give_player_health

        p = self.game.player
        p.lvars["special_power"] = power
        p.lvars["used_special_power"] = 0
        if power == HEALTH_POWER:
            give_player_health(p, 100)

    def can_dash(self) -> bool:
        p = self.game.player
        cards = self.game.world.globals.get("horde", {}).get("cards")  # Horde's cards hold play still
        return self.state["cooldown"] == 0 and p.aistate == NORMAL_PLAY and p.state not in ("dieing", "dead") \
            and not p.lvars.get("is_teleporting") and not cards

    def request_dash(self, direction: int = 0) -> bool:
        """Start a dash toward ``direction`` (-1 or 1), or the way the player faces if 0."""
        if not self.can_dash():
            return False
        st = self.state
        st["dash_dir"] = direction if direction in (-1, 1) else (1 if self.game.player.direction > 0 else -1)
        st["dash_left"] = DASH_TICKS
        st["iframes"] = DASH_IFRAMES
        st["cooldown"] = st.get("cooldown_max", DASH_COOLDOWN)  # Horde's dash card can shorten it
        st["dashes"] += 1
        st["announce"] = True  # emitted after the next step: World.step clears events at its start
        return True

    def _follow_exits(self) -> None:
        """The campaign (``engine/campaign.py``): an exit to a playable level ends the level and
        names the next one in ``world.globals["next_level"]``; an exit that ends the campaign
        ends the level with no next one; a locked exit stays shut, so the level goes on. If
        exits of different kinds are touched in the same tick, an open one wins."""
        from . import campaign

        w = self.game.world
        found = [(campaign.exit_result(self.game.level, e.data["next_level"]),
                  campaign.exit_level(e.data["next_level"]))
                 for e in w.events if e.kind == "level_complete"]
        if not found:
            return
        w.globals.pop("next_level", None)
        results = {r for r, _ in found}
        if "open" in results:
            w.globals["next_level"] = next(t for r, t in found if r == "open")
        elif "end" not in results:
            w.globals["level_complete"] = False
            for _, target in found:
                w.emit("level_locked", level=target)

    def before_step(self) -> None:
        self.game.world.globals["player_iframes"] = self.state["iframes"]
        self.dev_supplies()

    def after_step(self) -> None:
        self._follow_exits()
        st = self.state
        p = self.game.player
        if st.pop("announce", False):
            self.game.world.emit("dash", x=p.x, y=p.y, direction=st["dash_dir"])
        cards = self.game.world.globals.get("horde", {}).get("cards")
        if st["dash_left"] > 0 and (p.aistate != NORMAL_PLAY or p.lvars.get("is_teleporting") or cards):
            st["dash_left"] = 0  # a teleport, death or Horde's upgrade cards cancel the rest of the dash
        if st["dash_left"] > 0:
            _, xv, _ = p.try_move(p.x, p.y, DASH_SPEED * st["dash_dir"], 0, 3)
            p.x += xv
            top = p.objs[0] if p.objs else None
            if top is not None and not top.deleted:
                top.x += xv  # cop_ai placed the top half before this move; keep the two together
            p.direction = st["dash_dir"]
            st["dash_left"] -= 1
            if st["dash_left"] == 0 or xv == 0:
                st["dash_left"] = 0
                p.xvel = 0  # stop cleanly, without sliding
        st["iframes"] = max(0, st["iframes"] - 1)
        st["cooldown"] = max(0, st["cooldown"] - 1)
        self.game.world.globals["player_iframes"] = st["iframes"]
        self.dev_supplies()
