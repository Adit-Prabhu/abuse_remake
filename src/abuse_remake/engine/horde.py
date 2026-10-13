"""Horde: a Remastered-only arena on the Level 1 map. A new rule set, so never in Classic mode.

The arena is the longest flat floor in Level 1 with room above it (tile columns 56 to 79, row
109: x 1680 to 2400). The level's own objects are removed; only the map and its lights stay.
Ants come in waves, set running and jumping (``run_jump``, aistate 6) toward the player as the
original's wall cracks release them (``ant.lsp:524-551``). Unlike a crack, Horde spawns them at
the arena's ends, at the front of the object list, at 12 px per tick rather than 20, and with
its own aitype mix. Those numbers, like the wave sizes, breaks, drops and starting ammo, are
Remastered design, not the original. Each wave is bigger. Between waves there is a short break
with health and ammo drops. The run ends when the player dies; the score is the waves cleared
and the kills.

All state is in ``world.globals["horde"]``, so snapshots carry it. Horde draws its random
numbers from its own generator seeded from the game seed, so it never moves the original random
table more than the ants themselves do.
"""

from __future__ import annotations

import random

ARENA_X1, ARENA_X2 = 1680, 2400
ARENA_FLOOR_Y = 1640
START_X = (ARENA_X1 + ARENA_X2) // 2
FIRST_BREAK = 45  # ticks before wave 1
START_AMMO = ((0, 100), (1, 6))  # (weapon index, rounds): laser and grenades, so wave 1 is fair
BREAK_TICKS = 90  # ticks between waves
SPAWN_EVERY = 18  # ticks between ants within a wave
DROPS = ("HEALTH", "MBULLET_ICON20", "GRENADE_ICON10", "ROCKET_ICON5", "FBOMB_ICON5")


def keep_for_horde(obj) -> bool:
    """The level object filter: keep only the player's start."""
    return obj.type_name == "START"


def wave_size(wave: int) -> int:
    return 2 + 2 * wave


def ant_aitype(wave: int, rng: random.Random) -> int:
    """Tougher ant types appear from wave 3 (ant HP by aitype: ``ant.lsp:398-449``)."""
    if wave < 3:
        return 0
    return rng.choice((0, 0, 2) if wave < 5 else (0, 2, 3, 1))


class Horde:
    def __init__(self, game):
        self.game = game
        w = game.world
        if "horde" not in w.globals:
            w.globals["horde"] = {"wave": 0, "to_spawn": 0, "spawn_in": FIRST_BREAK, "break": True,
                                  "alive": [], "kills": 0, "cleared": 0, "over": False, "rng": game.seed}
            for wtype, n in START_AMMO:
                game.view.give_weapon(wtype)
                game.view.add_ammo(wtype, n)
        p = game.player
        p.x, p.y = START_X, ARENA_FLOOR_Y
        p.last_x, p.last_y = p.x, p.y
        v = game.view
        v.last_x, v.last_y, v.last_last_x, v.last_last_y = p.x, p.y, p.x, p.y

    @property
    def state(self) -> dict:
        return self.game.world.globals["horde"]

    def _rng(self) -> random.Random:
        st = self.state
        r = random.Random(st["rng"])
        st["rng"] = r.getrandbits(32)
        return r

    def after_step(self) -> None:
        st = self.state
        g = self.game
        w = g.world
        if st["over"]:
            return
        if g.player_dead:
            st["over"] = True
            w.emit("horde_over", wave=st["wave"], kills=st["kills"])
            return
        alive = []
        live = {o.uid: o for o in w.objects if not o.deleted}
        for uid in st["alive"]:
            o = live.get(uid)
            if o is not None and o.hp > 0:
                alive.append(uid)
            else:
                st["kills"] += 1
        st["alive"] = alive
        if st["break"]:
            st["spawn_in"] -= 1
            if st["spawn_in"] <= 0:
                st["break"] = False
                st["wave"] += 1
                st["to_spawn"] = wave_size(st["wave"])
                st["spawn_in"] = 0
                w.emit("horde_wave", wave=st["wave"], size=st["to_spawn"])
            return
        if st["to_spawn"] > 0:
            st["spawn_in"] -= 1
            if st["spawn_in"] <= 0:
                self._spawn_ant()
                st["to_spawn"] -= 1
                st["spawn_in"] = SPAWN_EVERY
            return
        if not st["alive"]:
            st["cleared"] = st["wave"]
            st["break"] = True
            st["spawn_in"] = BREAK_TICKS
            self._drops()
            w.emit("horde_cleared", wave=st["wave"])

    def _spawn_ant(self) -> None:
        g, st = self.game, self.state
        r = self._rng()
        p = g.player
        side = r.choice((-1, 1))
        if p.x - ARENA_X1 < 200:
            side = 1
        elif ARENA_X2 - p.x < 200:
            side = -1
        x = ARENA_X1 + 20 if side < 0 else ARENA_X2 - 20
        ant = g.world.spawn("ANT_ROOF", x, ARENA_FLOOR_Y - 30)
        ant.change_aitype(ant_aitype(st["wave"], r))
        d = 1 if p.x > x else -1
        ant.direction = d
        ant.xvel = d * 12
        ant.set_state("run_jump")
        ant.aistate = 6
        ant.aistate_time = 0
        st["alive"].append(ant.uid)
        g.world.emit("enemy_spawned", uid=ant.uid, x=ant.x, y=ant.y)

    def _drops(self) -> None:
        g, st = self.game, self.state
        r = self._rng()
        p = g.player
        n = 2 + st["wave"] // 2  # health, then ammo
        for i in range(n):
            kind = "HEALTH" if i == 0 else r.choice(DROPS[1:])
            x = max(ARENA_X1 + 30, min(ARENA_X2 - 30, p.x + r.randint(-120, 120)))
            g.world.spawn(kind, x, ARENA_FLOOR_Y - 60)
