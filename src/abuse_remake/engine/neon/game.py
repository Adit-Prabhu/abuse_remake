"""NeonGame: one Neon Protocol run (a campaign, a Horde run, training or a custom map).

The simulation runs at 30 ticks a second with integer positions and a local seeded RNG.
Each tick, in order:
1. weapon switching;
2. elevators, carrying their riders;
3. the player;
4. firing and interaction;
5. enemies near the player;
6. shots;
7. pickups, doors, teleporters and hazards;
8. Horde or training progress.

Presentation only reads this state and the per-tick ``events``. Snapshots copy every
moving part, including the random generator.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import fields, is_dataclass

from . import horde as horde_mod
from . import training as training_mod
from .enemies import DROP_CHANCE, SCORE, make_enemy
from .fixed import dist
from .horde import HordeState
from .objects import (
    Console,
    DoorGroup,
    Elevator,
    Pad,
    Pickup,
    Switch,
    call_elevator,
    open_door,
    update_doors,
    update_elevators,
    update_hazards,
    update_pads,
    update_pickups,
)
from .player import DYING_TICKS, STAND_H, WIDTH, NeonInput, Player
from .tilemap import EMPTY, HAZARD, RAIL, Grid, MapData, load_map, parse_map
from .weapons import WEAPONS, fire, update_shots

VARIANTS = ("campaign", "horde", "training", "custom")
DIFFICULTIES = ("easy", "medium", "hard", "extreme")
SECTORS = ("transit", "reactor", "hive", "core")
DAMAGE_SCALE = {"easy": 50, "medium": 75, "hard": 100, "extreme": 140}
ENEMY_HP_SCALE = {"easy": 80, "medium": 90, "hard": 100, "extreme": 125}
TRANSITION = 50
TICK_RATE = 30
ACTIVE_X, ACTIVE_Y, ALERT_RANGE = 820, 560, 1250


class NeonGame:
    def __init__(self, seed: int = 0, variant: str = "campaign", difficulty: str = "hard", sector: int = 0,
                 map_text: str | None = None):
        if variant not in VARIANTS:
            raise ValueError(f"unknown Neon Protocol variant {variant!r}")
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"unknown difficulty {difficulty!r}")
        if variant == "custom" and map_text is None:
            raise ValueError("a custom Neon game needs map_text")
        self.seed, self.variant, self.difficulty = seed, variant, difficulty
        self.rng = random.Random(seed)
        self.frames = 0
        self.status = "running"
        self.events: list[dict] = []
        self.damage_scale = DAMAGE_SCALE[difficulty]
        self.enemy_hp_scale = ENEMY_HP_SCALE[difficulty]
        self.kills = self.shots_fired = self.damage_taken = self.dashes = self.secrets = self.score = 0
        self.weapon = 0
        self.owned = [True, False, False, False, False]
        self.ammo = [-1, 0, 0, 0, 0]
        self.ammo_cap = [w.ammo_max for w in WEAPONS]
        self.fire_cd = 0
        self.upgrades: dict[str, int] = {}
        self.transition = 0
        self.locked_at = -100
        self.pad_cd = 0
        self.boss_dead = False
        self.sector = sector if variant == "campaign" else 0
        self.lesson = 0
        self.targets_killed = 0
        self.next_uid = 1
        self.player = Player(x=0, y=0, w=WIDTH, h=STAND_H)
        self.horde = HordeState() if variant == "horde" else None
        if variant == "horde":
            self.owned[1] = True
            self.ammo[1] = WEAPONS[1].ammo_start
        self._map_text = map_text
        self._load(self._map_name())

    # ------------------------------------------------------------ loading
    def _map_name(self) -> str:
        if self.variant == "campaign":
            return SECTORS[self.sector]
        return {"horde": "horde", "training": "training"}.get(self.variant, "custom")

    def _load(self, name: str) -> None:
        data: MapData = parse_map(self._map_text, "custom") if self.variant == "custom" else load_map(name)
        self.map = data
        self.grid = Grid(data)
        self.enemies, self.shots, self.pickups = [], [], []
        self.consoles, self.switches, self.elevators, self.pads = [], [], [], []
        self.lamps, self.markers, self.flyer_spawns, self.supply_spots = [], [], [], []
        self.exit: tuple[int, int] | None = None
        self.doors = [DoorGroup(g, list(tiles), key=g[4:] if g.startswith("key:") else "")
                      for g, tiles in sorted(data.doors.items())]
        self.hazards = HAZARD in data.tiles
        p = self.player
        for ent in data.entities:
            x, y = ent.tx * 16 + 8, (ent.ty + 1) * 16
            k = ent.kind
            if k == "player":
                p.x, p.y = x - p.w // 2, y - p.h
            elif k == "console":
                self.consoles.append(Console(x, y))
            elif k == "exit":
                self.exit = (x, y)
            elif k == "switch":
                timer = int(ent.args[1]) if len(ent.args) > 1 else 0
                self.switches.append(Switch(ent.args[0], x, y, timer=timer))
            elif k == "elevator":
                self.elevators.append(self._elevator(ent.tx, ent.ty))
            elif k == "teleport":
                self.pads.append(Pad(x, y, ent.args[0]))
            elif k in ("enemy", "nest"):
                kind = ent.args[0] if k == "enemy" else "nest"
                args = ent.args[1:] if k == "enemy" else ent.args
                e = make_enemy(self, kind, ent.tx, ent.ty, self._uid(), args)
                if kind == "nest" and self.variant == "horde":
                    e.spawn_point = True
                self.enemies.append(e)
            elif k == "spawn":
                self.flyer_spawns.append((x, y - 8))
            elif k == "marker":
                self.markers.append((x, y))
            elif k == "lamp":
                self.lamps.append((x, ent.ty * 16 + 8))
            elif k == "pickup":
                self.pickups.append(Pickup(ent.args[0], x, y, placed=True, spot=len(self.supply_spots)))
                self.supply_spots.append((ent.args[0], x, y))
        self.markers.sort()
        self.player.vx = self.player.vy = 0

    def _elevator(self, tx: int, ty: int) -> Elevator:
        g = self.grid
        up = down = ty
        while g.at(tx, up - 1) == RAIL:
            up -= 1
        while g.at(tx, down + 1) == RAIL:
            down += 1
        # L marks the cell just above the platform, so a platform resting at the bottom of a room
        # is flush with its floor; the track's top rail is the cell above the top stop
        return Elevator(x=tx * 16 - 16, y=(ty + 1) * 16, top=(up + 1) * 16, bottom=(down + 1) * 16,
                        home=(ty + 1) * 16)

    def _uid(self) -> int:
        self.next_uid += 1
        return self.next_uid - 1

    # ------------------------------------------------------------ helpers the parts call
    @property
    def width(self) -> int:
        return self.map.width * 16

    @property
    def height(self) -> int:
        return self.map.height * 16

    @property
    def sector_name(self) -> str:
        return self.map.title

    def emit(self, event: str, x: int, y: int, **data) -> None:
        self.events.append({**data, "kind": event, "x": x, "y": y})

    def upgrade_pct(self, what: str) -> int:
        n = self.upgrades.get({"fire_cd": "rapid", "dash_cd": "coils"}[what], 0)
        pct = 100
        for _ in range(n):
            pct = pct * (85 if what == "fire_cd" else 70) // 100
        return pct

    def wave_damage_pct(self) -> int:
        return horde_mod.damage_pct(self.horde.wave) if self.horde is not None else 100

    def player_damage(self, base: int) -> int:
        dmg = base * (200 if self.player.overcharge else 100) // 100
        return dmg * (100 + 20 * self.upgrades.get("amp", 0)) // 100

    def noise(self, x: int, y: int, radius: int) -> None:
        for e in self.enemies:
            if e.dead:
                continue
            d = dist(e.cx - x, e.cy - y)
            if d <= radius and (d <= radius // 2 or self.grid.line_clear(x, y, e.cx, e.cy)):
                e.heard(self, x, y)

    def alert_near(self, x: int, y: int, radius: int, source: int) -> None:
        """A scream: nearby enemies wake (without screaming again, so it does not chain)."""
        for e in self.enemies:
            if e.uid != source and not e.dead and not e.alerted and e.kind not in ("nest", "warden") \
                    and dist(e.cx - x, e.cy - y) <= radius:
                e.alerted = True
                if e.state == "hang":
                    e.state = "ceil"
                elif e.state in ("idle", "patrol") and e.kind in ("crawler", "strider"):
                    e.state = "chase" if e.kind == "crawler" else "stalk"
                elif e.kind == "stinger" and e.state == "idle":
                    e.state = "stalk"

    def alarm(self, x: int, y: int, radius: int = 420) -> None:
        for e in self.enemies:
            if e.dead:
                continue
            d = dist(e.cx - x, e.cy - y)
            if e.kind == "nest" and d <= radius:
                e.activate(self)
            elif d <= radius * 6 // 7:
                e.alert(self, scream=False)

    def spawn_enemy(self, kind: str, x: int, bottom: int, args: tuple = ()):
        e = make_enemy(self, kind, x >> 4, (bottom - 1) >> 4, self._uid(), args)
        e.x = x - e.w // 2
        e.y = bottom - e.h
        e.surface = "floor" if kind in ("crawler", "strider") else e.surface
        if kind == "crawler":
            e.state = "drop"
        self.enemies.append(e)
        return e

    def spawn_from_nest(self, nest, kind: str) -> None:
        e = self.spawn_enemy(kind, nest.cx, nest.bottom)
        e.owner = nest.uid
        e.alerted = True
        e.state = "drop"
        self.emit("nest_spawn", nest.cx, nest.cy, uid=e.uid)

    def kill(self, e, sx: int, sy: int) -> None:
        e.dead = True
        if e.kind != "target":
            self.kills += 1
            self.score += SCORE[e.kind]
        else:
            self.targets_killed += 1
        self.emit("kill", e.cx, e.cy, enemy=e.kind, uid=e.uid, dir=1 if e.cx >= sx else -1, w=e.w, h=e.h,
                  surface=e.surface)
        if e.kind == "warden":
            self.boss_dead = True
            self.emit("boss_dead", e.cx, e.cy)
        roll = self.rng.randrange(100)
        if roll < DROP_CHANCE[e.kind]:
            if e.kind == "strider":
                kinds = ("ammo", self.rng.choice(("shield", "overcharge", "haste", "health")))
            else:
                kinds = ("health" if self.rng.randrange(5) < 2 else "ammo",)
            for i, kind in enumerate(kinds):
                self.pickups.append(Pickup(kind, e.cx + i * 14 - (len(kinds) - 1) * 7, e.bottom - 1, life=900))

    def break_tile(self, tx: int, ty: int) -> None:
        self.grid.set(tx, ty, EMPTY)
        self.emit("break", tx * 16 + 8, ty * 16 + 8)
        self.secrets += 1

    def respawn_supplies(self) -> None:
        present = {item.spot for item in self.pickups if item.spot >= 0}
        for i, (kind, x, y) in enumerate(self.supply_spots):
            if i not in present:
                self.pickups.append(Pickup(kind, x, y, placed=True, spot=i))

    def collect(self, item: Pickup) -> bool:
        p, k = self.player, item.kind
        if k == "health":
            if p.hp >= p.max_hp:
                return False
            p.hp = min(p.max_hp, p.hp + 30)
        elif k == "ammo":
            room = [i for i in range(1, 5) if self.owned[i] and self.ammo[i] < self.ammo_cap[i]]
            if not room:
                return False
            for i in room:
                self.ammo[i] = min(self.ammo_cap[i], self.ammo[i] + WEAPONS[i].ammo_pickup)
        elif k.startswith("weapon"):
            slot = int(k[6:])
            if not self.owned[slot]:
                self.owned[slot] = True
                self.ammo[slot] = min(self.ammo_cap[slot], WEAPONS[slot].ammo_start)
                self.weapon = slot
            elif self.ammo[slot] >= self.ammo_cap[slot]:
                return False
            else:
                self.ammo[slot] = min(self.ammo_cap[slot], self.ammo[slot] + WEAPONS[slot].ammo_pickup * 2)
        elif k == "shield":
            p.shield, p.shield_t = 50, 600
        elif k == "overcharge":
            p.overcharge = 300
        elif k == "haste":
            p.haste = 360
        elif k == "phase":
            p.phase = 450
        elif k == "boots":
            p.boots = True
            p.air_jumps = 1
        elif k.startswith("key_"):
            p.keys.append(k[4:])
        else:
            return False
        return True

    # ------------------------------------------------------------ the tick
    def step(self, inp: NeonInput | None = None, select: int | None = None, cycle: int = 0,
             upgrade: int | None = None) -> None:
        if self.status != "running":
            return
        self.events = []
        self.frames += 1
        p = self.player
        if inp is None:
            sx, sy = p.shoulder()
            inp = NeonInput(px=sx + 120 * p.facing, py=sy)
        else:  # normalise, so any truthy value gives the same hashed state as a bool
            inp = NeonInput(int(inp.x), int(inp.y), bool(inp.jump), bool(inp.fire), bool(inp.dash),
                            bool(inp.interact), int(inp.px), int(inp.py))
        if upgrade is not None and self.horde is not None:
            horde_mod.choose(self, upgrade)
        if self.transition:
            self.transition -= 1
            if self.transition == 0:
                self._finish_transition()
            return
        self._switch_weapon(select, cycle)
        if self.fire_cd:
            self.fire_cd -= 1
        update_elevators(self)
        acts = p.update(self, inp)
        if p.dying:
            if p.dying > DYING_TICKS:
                self.status = "dead"
                self.emit("dead", p.cx, p.cy)
                return
        else:
            if acts["fire"] and self.fire_cd == 0:
                fire(self, p)
            if acts["interact"]:
                self._interact()
            nano = self.upgrades.get("nano", 0)
            if nano and p.hp < p.max_hp and self.frames % (60 // nano) == 0:
                p.hp += 1  # 1 integrity every 2 s, 1 s, 0.67 s with 1, 2, 3 stacks
        self._update_enemies()
        update_shots(self)
        if any(e.dead for e in self.enemies):
            self.enemies = [e for e in self.enemies if not e.dead]
        update_pickups(self)
        update_doors(self)
        update_pads(self)
        if self.hazards:
            update_hazards(self)
        if self.horde is not None:
            horde_mod.tick(self)
        elif self.variant == "training":
            training_mod.tick(self)

    def _switch_weapon(self, select: int | None, cycle: int) -> None:
        if select is not None:
            if 0 <= select < 5 and self.owned[select] and select != self.weapon:
                self.weapon = select
                self.emit("switch", self.player.cx, self.player.cy, weapon=select)
        elif cycle:
            n = len(self.owned)
            w = self.weapon
            for _ in range(n):
                w = (w + (1 if cycle > 0 else -1)) % n
                if self.owned[w]:
                    break
            if w != self.weapon:
                self.weapon = w
                self.emit("switch", self.player.cx, self.player.cy, weapon=w)

    def _update_enemies(self) -> None:
        p = self.player
        for e in list(self.enemies):
            if e.dead:
                continue
            dx, dy = abs(e.cx - p.cx), abs(e.cy - p.cy)
            if self.horde is not None or (dx < ACTIVE_X and dy < ACTIVE_Y) or \
                    (e.alerted and dx < ALERT_RANGE and dy < ALERT_RANGE):
                e.update(self)
                if e.y > self.height + 64:
                    e.dead = True

    def _interact(self) -> None:
        p = self.player
        for c in self.consoles:
            if abs(p.cx - c.x) < 26 and abs(p.bottom - c.y) < 24:
                c.used = True
                p.hp = max(p.hp, p.max_hp)
                for i in range(1, 5):
                    if self.owned[i]:
                        self.ammo[i] = max(self.ammo[i], WEAPONS[i].ammo_start)
                self.emit("checkpoint", c.x, c.y)
                return
        for s in self.switches:
            if abs(p.cx - s.x) < 24 and abs(p.cy - (s.y - 16)) < 32:
                door = next((d for d in self.doors if d.group == s.group), None)
                s.on = True
                self.emit("switch_on", s.x, s.y - 16, group=s.group)
                if door is not None:
                    open_door(self, door, s.timer)
                return
        if self.exit is not None and abs(p.cx - self.exit[0]) < 28 and abs(p.bottom - self.exit[1]) < 24:
            if self.variant == "campaign" and self.sector == len(SECTORS) - 1 and not self.boss_dead:
                self.emit("locked", p.cx, p.y, why="boss")
                return
            self._sector_clear()
            return
        call_elevator(self, p)

    def _sector_clear(self) -> None:
        p = self.player
        self.emit("sector_clear", p.cx, p.cy, sector=self.sector, title=self.map.title)
        if self.variant != "campaign" or self.sector >= len(SECTORS) - 1:
            self.status = "won"
            self.emit("won", p.cx, p.cy)
            return
        self.transition = TRANSITION

    def _finish_transition(self) -> None:
        p = self.player
        self.sector += 1
        p.keys = []
        p.climbing = p.crouching = False
        p.h = STAND_H
        p.hp = max(p.hp, p.max_hp * 3 // 4)
        p.dash_t = 0
        self._load(SECTORS[self.sector])
        self.emit("sector_start", p.cx, p.cy, sector=self.sector, title=self.map.title)

    # ------------------------------------------------------------ saves and hashes
    def snapshot(self) -> dict:
        return copy.deepcopy(self.__dict__, {id(self.map): self.map})

    def restore(self, snap: dict) -> None:
        self.__dict__ = copy.deepcopy(snap, {id(snap["map"]): snap["map"]})

    def state_hash(self) -> str:
        state = {k: v for k, v in self.__dict__.items() if k not in ("events", "map", "rng", "_map_text")}
        state["rng"] = self.rng.getstate()
        state["map"] = self.map.name
        return hashlib.sha256(json.dumps(_canon(state), sort_keys=True).encode()).hexdigest()


def _canon(v):
    if is_dataclass(v):
        return {"_": type(v).__name__, **{f.name: _canon(getattr(v, f.name)) for f in fields(v)}}
    if isinstance(v, dict):
        return {str(k): _canon(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_canon(x) for x in v]
    if isinstance(v, (bytes, bytearray)):
        return hashlib.sha256(bytes(v)).hexdigest()
    if isinstance(v, set):
        return sorted(_canon(x) for x in v)
    if hasattr(v, "__dict__"):
        return {"_": type(v).__name__, **{k: _canon(x) for k, x in vars(v).items()}}
    return v
