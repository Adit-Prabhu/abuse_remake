"""Horde: Remastered-only arenas where waves of enemies attack. A new rule set, so never in
Classic mode; every rule here is Remastered design unless a line says otherwise.

Arenas. The level's own objects are removed; only the map and its lights stay.
- ``prison``: the longest flat floor in Level 1 with room above it (tile columns 56 to 79, row
  109: x 1680 to 2400). The original Horde arena, and still the default.
- ``rooftop``: the long ledge at the top of Level 2 (x 2040 to 2600), with high headroom.
- ``pit``: Level 2's raised Juggernaut floor (x 1180 to 1580), where the level keeps two.
Each arena is a room cut out of a real level, and the ladders and lifts that lead out of it are
objects, which Horde removes. So each arena is sealed when it loads (``SEALS``): walls and floors
built from the level's own tiles close every drop and every way out, so that nobody can fall,
walk, dash or fly out of it, and every enemy can reach the player.

Waves. Wave n has 2 + 2n enemies, released one every 18 ticks at the arena's ends. Waves 1 and 2
are ants only, as in the first Horde. From wave 3 each slot is drawn from a growing roster:
flyers from wave 3, cleaner robots from wave 4, Juggernauts from wave 6, green flyers from wave 7.
Every fifth wave is a boss wave: an elite Juggernaut with a few ants. The engine caps health at 200
(``world.max_hp``, as the C does), so the boss has extra lives instead: one more 200-health life
per boss wave so far (two lives at wave 5, three at wave 10), and each life lost puts it back on
its feet. The enemies run their ported AI (ant.c, flyer.lsp, jugger.lsp). Ants are set running
and jumping toward the player (``run_jump``, aistate 6) as the original's wall cracks release
them (``ant.lsp:524-551``), at 12 px per tick rather than 20.

Between waves. Health and ammo drop onto the floor, 40 to 140 px to one side of the player, and
three upgrade cards are offered. The next wave waits until one is chosen (``choose``). Speed,
flight and ultra health give that power until the end of the next wave; when ultra health ends,
health above the normal cap of 100 goes with it. The dash card shortens the dash's recharge down
to 10 ticks, then is no longer offered: below that the recharge would beat the 7 ticks of
invulnerability and the player could never be hurt.
Invisibility is not offered: in the original it only changes how the player is drawn.

Score. A kill by the player (the last hit was the player's, or the player's shot or grenade)
scores its enemy's points times the combo, which grows by one (up to 5) for each such kill within
45 ticks of the last. A cleared wave adds 200 per wave number, and 300 more per wave number if the
player took no damage in it. The run ends when the player dies.

While the cards are up, play holds still: ``Game.step`` passes the player only the aim (``hold``),
so the arrows and the mouse choose a card instead of walking or firing, and a dash is refused.

All state is in ``world.globals["horde"]``, except the sealed cells, which are in the world's own
tile map; snapshots carry both, and ``Game.state_hash`` covers both. Horde draws its random numbers
from its own generator seeded from the game seed, so it never moves the original random table more
than the enemies themselves do.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .behaviors.lispfns import set_aistate
from .behaviors.player import FAST_POWER, FLY_POWER, HEALTH_POWER, NO_POWER, give_player_health
from .remastered import DASH_COOLDOWN, DASH_IFRAMES


@dataclass(frozen=True)
class Arena:
    key: str
    level: str
    title: str
    x1: int
    x2: int
    floor_y: int
    fly: int  # flyers are released fly to fly + 19 px above the floor (tests: never into a ceiling)


ARENAS = {
    "prison": Arena("prison", "level01", "Prison floor (Level 1)", 1680, 2400, 1640, 24),  # ceiling ~77 px up
    # tile columns 68 to 86 above row 32, and 39 to 52 above row 87 once sealed (30x15 tiles); found
    # by scanning Level 2's map for long flat floors with headroom (tests/test_horde2.py lands on them)
    "rooftop": Arena("rooftop", "level02", "Rooftop (Level 2)", 2040, 2600, 481, 120),  # ceiling ~223 px up
    "pit": Arena("pit", "level02", "Juggernaut floor (Level 2)", 1180, 1580, 1306, 40),  # ~103 px at its ends
}
# Cells (tile x1..x2, y1..y2, inclusive) set to a tile when the arena loads, in order. The tiles
# are the levels' own beveled-block set: 10 and 11 the right and left faces of a wall, 12 and 13
# the joints where a floor meets a wall on its left and right, 26 a floor's top, 28 solid fill,
# 67 an underside, 44 an underside's right corner.
SEALS: dict[str, tuple[tuple[int, int, int, int, int], ...]] = {
    # a lid on the lift shaft in the top-left corner (column 56), which flight could climb
    "prison": ((56, 57, 103, 103, 67),),
    # a pillar from the roof to the corridor floor at the ledge's left end, over the 60 px gap
    # (columns 66-67) that dropped into the corridor under the roof
    "rooftop": ((66, 66, 17, 41, 11), (67, 67, 17, 41, 10), (67, 67, 32, 32, 12), (68, 68, 32, 32, 26)),
    # a pillar from the ceiling to the lower floor at the platform's left end (columns 37-38), and
    # the platform carried on over the right-hand gap (columns 50-52, rewriting 49-53) to the room's
    # right wall
    "pit": ((38, 38, 71, 92, 10), (37, 37, 72, 92, 11), (38, 38, 87, 87, 12), (39, 39, 87, 87, 26),
            (39, 39, 88, 88, 28), (39, 39, 89, 89, 67),
            (49, 52, 87, 87, 26), (49, 53, 88, 88, 28), (49, 52, 89, 89, 67), (53, 53, 89, 89, 44),
            (53, 53, 87, 87, 13)),
}
ARENA_X1, ARENA_X2 = ARENAS["prison"].x1, ARENAS["prison"].x2  # the original arena's names
ARENA_FLOOR_Y = ARENAS["prison"].floor_y
START_X = (ARENA_X1 + ARENA_X2) // 2
FIRST_BREAK = 45  # ticks before wave 1
START_AMMO = ((0, 100), (1, 6))  # (weapon index, rounds): laser and grenades, so wave 1 is fair
BREAK_TICKS = 90  # ticks between waves, once a card is chosen
SPAWN_EVERY = 18  # ticks between enemies within a wave
DROPS = ("HEALTH", "MBULLET_ICON20", "GRENADE_ICON10", "ROCKET_ICON5", "FBOMB_ICON5")
BOSS_EVERY = 5
VERSION = 3  # human traces name it: 2 added cards and arenas, 3 sealed the arenas and moved drops
COMBO_TICKS = 45
MAX_COMBO = 5
POINTS = {"ANT_ROOF": 100, "FLYER": 150, "GREEN_FLYER": 200, "ROB1": 250, "JUGGER": 400, "BOSS": 2500}
BOSS_LIFE = 200  # world.max_hp: add_hp never lets health above it (objects.c:337-346)
DASH_FLOOR = DASH_IFRAMES + 3  # 10: always at least 3 ticks a dash can be hurt in
DASH_STEP = 4
# (kind, first wave, weight) for the slots of waves 3 onward
ROSTER = (("ANT_ROOF", 1, 6), ("FLYER", 3, 2), ("ROB1", 4, 1), ("JUGGER", 6, 1), ("GREEN_FLYER", 7, 1))
CARDS = {
    "speed": "Speed power until the next wave ends",
    "flight": "Flight power until the next wave ends",
    "ultra_health": "Ultra health until the next wave ends: health cap 200, and a heal of 100 scaled by difficulty",
    "medkit": "Full health",
    "ammo": "+10 grenades and +5 firebombs",
    "rockets": "Rocket launcher and +10 rockets",
    "dash": "Dash recharges 4 ticks sooner (down to 10)",
}
CARD_POWER = {"speed": FAST_POWER, "flight": FLY_POWER, "ultra_health": HEALTH_POWER}


def keep_for_horde(obj) -> bool:
    """The level object filter: keep only the player's start."""
    return obj.type_name == "START"


def seal(world, arena: str) -> None:
    """Close the arena's drops and ways out (``SEALS``). The world's tile map is its own copy, so
    the level as loaded elsewhere never changes."""
    for x1, x2, y1, y2, tile in SEALS[arena]:
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                world.tiles.put(x, y, tile)


def wave_size(wave: int) -> int:
    return 2 + 2 * wave


def ant_aitype(wave: int, rng: random.Random) -> int:
    """Tougher ant types appear from wave 3 (ant HP by aitype: ``ant.lsp:398-449``)."""
    if wave < 3:
        return 0
    return rng.choice((0, 0, 2) if wave < 5 else (0, 2, 3, 1))


def roster(wave: int, rng: random.Random) -> list[str]:
    """The kinds of enemy in a wave, in release order."""
    if wave % BOSS_EVERY == 0:
        return ["BOSS"] + ["ANT_ROOF"] * (2 + 2 * (wave // BOSS_EVERY))
    if wave < 3:
        return ["ANT_ROOF"] * wave_size(wave)
    pool = [(kind, weight) for kind, first, weight in ROSTER if wave >= first]
    kinds = [k for k, _ in pool]
    weights = [w for _, w in pool]
    return [rng.choices(kinds, weights)[0] for _ in range(wave_size(wave))]


def boss_lives(wave: int) -> int:
    """Lives of BOSS_LIFE health: two at the first boss wave, one more at each later one."""
    return 1 + wave // BOSS_EVERY


class Horde:
    def __init__(self, game, arena: str = "prison"):
        self.game = game
        w = game.world
        if "horde" not in w.globals:
            w.globals["horde"] = {
                "arena": arena, "wave": 0, "to_spawn": [], "spawn_in": FIRST_BREAK, "break": True,
                "alive": [], "types": {}, "kills": 0, "kills_by": {}, "cleared": 0, "over": False,
                "rng": game.seed, "cards": [], "card_power": None, "boss": None, "boss_max": 0,
                "boss_lives": 0, "score": 0, "combo": 0, "best_combo": 0, "last_kill": -10 ** 6,
                "tick": 0, "wave_hp_lost": 0, "player_hit": {}, "announce": None,
            }
            for wtype, n in START_AMMO:
                game.view.give_weapon(wtype)
                game.view.add_ammo(wtype, n)
        seal(w, self.state["arena"])
        a = self.arena
        p = game.player
        p.x, p.y = (a.x1 + a.x2) // 2, a.floor_y
        p.last_x, p.last_y = p.x, p.y
        v = game.view
        v.last_x, v.last_y, v.last_last_x, v.last_last_y = p.x, p.y, p.x, p.y

    @property
    def state(self) -> dict:
        return self.game.world.globals["horde"]

    @property
    def arena(self) -> Arena:
        return ARENAS[self.state["arena"]]

    def _rng(self) -> random.Random:
        st = self.state
        r = random.Random(st["rng"])
        st["rng"] = r.getrandbits(32)
        return r

    # --- cards ---
    def choose(self, index: int) -> bool:
        """Take card ``index`` of those offered. Called between ticks, like a dash request."""
        st = self.state
        if not 0 <= index < len(st["cards"]) or st["over"]:
            return False
        card = st["cards"][index]
        st["cards"] = []
        g = self.game
        p, v = g.player, g.view
        if card in CARD_POWER:
            p.lvars["special_power"] = CARD_POWER[card]
            st["card_power"] = CARD_POWER[card]
            if card == "ultra_health":
                give_player_health(p, 100)
        elif card == "medkit":
            p.set_hp(max(p.hp, 200 if p.lvars["special_power"] == HEALTH_POWER else 100))
        elif card == "ammo":
            for wtype, n in ((1, 10), (3, 5)):
                v.give_weapon(wtype)
                v.add_ammo(wtype, n)
        elif card == "rockets":
            v.give_weapon(2)
            v.add_ammo(2, 10)
        elif card == "dash" and g.remastered is not None:
            rs = g.remastered.state
            rs["cooldown_max"] = max(DASH_FLOOR, rs.get("cooldown_max", DASH_COOLDOWN) - DASH_STEP)
        st["announce"] = card  # emitted after the next step: World.step clears events at its start
        return True

    def hold(self, inputs):
        """While the cards are up, the player's input keeps only the aim."""
        if not self.state["cards"]:
            return inputs
        from .view import Inputs

        return Inputs(pointer_x=inputs.pointer_x, pointer_y=inputs.pointer_y)

    def card_pool(self) -> list[str]:
        """The cards that can still do something: the dash card stops at its floor."""
        g = self.game
        rs = g.remastered.state if g.remastered is not None else {}
        return [c for c in sorted(CARDS) if c != "dash" or rs.get("cooldown_max", DASH_COOLDOWN) > DASH_FLOOR]

    # --- the tick ---
    def after_step(self) -> None:
        st = self.state
        g = self.game
        w = g.world
        if st["over"]:
            return
        st["tick"] += 1
        if st["announce"] is not None:
            w.emit("horde_card", card=st["announce"])
            st["announce"] = None
        hits = dict(st["player_hit"])
        for e in w.events:  # who hurt whom this tick (output events; they change no rule)
            if e.kind != "damage":
                continue
            if e.data["target"] == g.player.uid:
                st["wave_hp_lost"] += e.data["amount"]
            elif e.data["target"] in st["alive"]:
                hits[str(e.data["target"])] = bool(e.data.get("by_player"))
        st["player_hit"] = hits
        if g.player_dead:
            st["over"] = True
            w.emit("horde_over", wave=st["wave"], kills=st["kills"], score=st["score"])
            return
        self._boss_lives()
        self._count_kills()
        if st["break"]:
            if st["cards"]:
                return  # the next wave waits for a card
            st["spawn_in"] -= 1
            if st["spawn_in"] <= 0:
                st["break"] = False
                st["wave"] += 1
                st["to_spawn"] = roster(st["wave"], self._rng())
                st["spawn_in"] = 0
                st["wave_hp_lost"] = 0
                w.emit("horde_wave", wave=st["wave"], size=len(st["to_spawn"]),
                       boss=st["to_spawn"][0] == "BOSS")
            return
        if st["to_spawn"]:
            st["spawn_in"] -= 1
            if st["spawn_in"] <= 0:
                kind, st["to_spawn"] = st["to_spawn"][0], st["to_spawn"][1:]
                self._spawn(kind)
                st["spawn_in"] = SPAWN_EVERY
            return
        if not st["alive"]:
            self._wave_cleared()

    def _boss_lives(self) -> None:
        """A boss that runs out of health with lives left gets up again at full health."""
        st = self.state
        if st["boss"] is None or st["boss_lives"] <= 0:
            return
        boss = next((o for o in self.game.world.objects if o.uid == st["boss"] and not o.deleted), None)
        if boss is not None and boss.hp <= 0:
            st["boss_lives"] -= 1
            boss.set_hp(BOSS_LIFE)
            boss.set_state("stopped")  # out of its death animation, back to walking (jug_ai state 0)
            set_aistate(boss, 0)
            self.game.world.emit("boss_life", uid=boss.uid, lives=st["boss_lives"])

    def boss_health(self) -> tuple[int, int]:
        """The boss's health over all its lives, and the most it had."""
        st = self.state
        boss = next((o for o in self.game.world.objects if o.uid == st["boss"] and not o.deleted), None)
        if boss is None:
            return 0, st["boss_max"]
        return max(0, boss.hp) + BOSS_LIFE * st["boss_lives"], st["boss_max"]

    def _count_kills(self) -> None:
        """Nested values are replaced, never changed in place, so a shallow copy of the state
        stays a true record of it."""
        st = self.state
        live = {o.uid: o for o in self.game.world.objects if not o.deleted}
        alive = []
        types, kills_by, hits = dict(st["types"]), dict(st["kills_by"]), dict(st["player_hit"])
        for uid in st["alive"]:
            o = live.get(uid)
            if o is not None and o.hp > 0:
                alive.append(uid)
                continue
            kind = types.pop(str(uid), "ANT_ROOF")
            st["kills"] += 1
            kills_by[kind] = kills_by.get(kind, 0) + 1
            if hits.pop(str(uid), False):  # scored only when the player made the kill
                near = st["tick"] - st["last_kill"] <= COMBO_TICKS
                st["combo"] = min(MAX_COMBO, st["combo"] + 1) if near else 1
                st["best_combo"] = max(st["best_combo"], st["combo"])
                st["last_kill"] = st["tick"]
                st["score"] += POINTS[kind] * st["combo"]
            if uid == st["boss"]:
                st["boss"] = None
        st["alive"], st["types"], st["kills_by"], st["player_hit"] = alive, types, kills_by, hits

    def _wave_cleared(self) -> None:
        st = self.state
        g = self.game
        st["cleared"] = st["wave"]
        bonus, clean = 200 * st["wave"], (300 * st["wave"] if st["wave_hp_lost"] == 0 else 0)
        st["score"] += bonus + clean
        st["break"] = True
        st["spawn_in"] = BREAK_TICKS
        p = g.player
        if st["card_power"] is not None:  # a card's power lasts until the end of the next wave
            if p.lvars["special_power"] == st["card_power"]:
                p.lvars["special_power"] = NO_POWER
                if st["card_power"] == HEALTH_POWER and p.hp > 100:
                    p.set_hp(100)  # the cap is 100 again (give_player_health, people.lsp:58-60)
            st["card_power"] = None
        self._drops()
        st["cards"] = self._rng().sample(self.card_pool(), 3)
        g.world.emit("horde_cleared", wave=st["wave"], cards=list(st["cards"]), bonus=bonus, clean=clean)

    # --- spawning ---
    def _end(self, r: random.Random) -> int:
        """Which end of the arena to release from: away from the player if they are near one."""
        a = self.arena
        p = self.game.player
        side = r.choice((-1, 1))
        near = min(200, (a.x2 - a.x1) // 4)  # 100 px in the narrow pit, so both ends stay in play
        if p.x - a.x1 < near:
            side = 1
        elif a.x2 - p.x < near:
            side = -1
        return a.x1 + 20 if side < 0 else a.x2 - 20

    def _spawn(self, kind: str) -> None:
        st = self.state
        g = self.game
        a = self.arena
        r = self._rng()
        p = g.player
        x = self._end(r)
        d = 1 if p.x > x else -1
        w = g.world
        if kind == "ANT_ROOF":
            o = w.spawn("ANT_ROOF", x, a.floor_y - 30)
            o.change_aitype(ant_aitype(st["wave"], r))
            o.direction = d
            o.xvel = d * 12
            o.set_state("run_jump")
            o.aistate = 6
            o.aistate_time = 0
        elif kind in ("FLYER", "GREEN_FLYER"):
            o = w.spawn(kind, x, a.floor_y - a.fly - r.randrange(20))  # flyer_cons: straight rockets
            o.direction = d
            o.set_aistate(1)
            o.set_state("running")
            o.targetable_on = 1
        elif kind == "ROB1":
            o = w.spawn("ROB1", x, a.floor_y)  # rob_cons: 2 px per tick
            o.direction = d
            o.set_aistate(1)
        else:  # JUGGER or BOSS
            o = w.spawn("JUGGER", x, a.floor_y)  # jug_cons: throws every 10 ticks
            o.direction = d
            o.lvars["stationary"] = 0
            if kind == "BOSS":
                o.set_hp(BOSS_LIFE)
                o.lvars["throw_xvel"] = 15
                st["boss"], st["boss_lives"] = o.uid, boss_lives(st["wave"]) - 1
                st["boss_max"] = BOSS_LIFE * boss_lives(st["wave"])
        st["alive"] = st["alive"] + [o.uid]
        st["types"] = {**st["types"], str(o.uid): kind}
        w.emit("enemy_spawned", uid=o.uid, x=o.x, y=o.y, enemy=kind)

    def _drops(self) -> None:
        g, st = self.game, self.state
        a = self.arena
        r = self._rng()
        p = g.player
        n = 2 + st["wave"] // 2  # health, then ammo
        for i in range(n):
            kind = "HEALTH" if i == 0 else r.choice(DROPS[1:])
            side, off = r.choice((-1, 1)), r.randint(40, 140)  # in sight, not under the player
            x = p.x + side * off
            if not a.x1 + 30 <= x <= a.x2 - 30:
                x = p.x - side * off
            x = max(a.x1 + 30, min(a.x2 - 30, x))
            o = g.world.spawn(kind, x, a.floor_y - 60)
            _, _, dy = o.try_move(o.x, o.y, 0, 90, 3)  # onto the floor: a health pack never falls
            o.y += dy
            o.last_y = o.y
