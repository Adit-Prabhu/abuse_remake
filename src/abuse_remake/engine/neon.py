"""Neon Protocol: independent optional design, never used by Classic or evaluations.

All gameplay runs here at 15 Hz. Coordinates and velocities are integer pixels; seeded
randomness is local and included in saves. Presentation reads this state without changing it.
Design constants and provenance are recorded in docs/neon-protocol.md and rule-source-map.md.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass, field

from .view import Inputs

FLOOR = 520
WEAPONS = ("PULSE RIFLE", "RAIL LANCE", "VORTEX CASTER")
ENEMY_HP = {"drone": 36, "stalker": 48, "sentry": 80, "titan": 240, "dummy": 120}
LESSONS = (
    ("01 / MOVE", "A / D or arrows  •  Move along the training deck."),
    ("02 / JUMP", "Space / W / Up  •  Jump onto the floating platforms."),
    ("03 / AIM + FIRE", "Mouse to aim • Left click / J to fire • Hit the training target."),
    ("04 / SWITCH WEAPONS", "Press 2 or 3, Q / E, or scroll • Try the rail lance or vortex caster."),
    ("05 / PHASE DASH", "F  •  Dash in your movement direction. Briefly avoids damage."),
    ("06 / POWER-UPS", "Walk through a glowing pickup • Shields, overcharge and speed are temporary."),
    ("07 / INTERACT", "S / Down near the relay at the right end • Activate it to finish training."),
)


@dataclass
class Player:
    x: int = 140
    y: int = FLOOR - 42
    w: int = 22
    h: int = 42
    vx: int = 0
    vy: int = 0
    facing: int = 1
    hp: int = 100
    grounded: bool = True
    iframes: int = 0
    dash: int = 0
    dash_cooldown: int = 0
    dash_dir: int = 1
    shield: int = 0
    shield_time: int = 0
    overcharge: int = 0
    speed: int = 0


@dataclass
class Enemy:
    uid: int
    kind: str
    x: int
    y: int
    hp: int
    w: int = 30
    h: int = 36
    cooldown: int = 30
    windup: int = 0
    facing: int = -1
    vy: int = 0


@dataclass
class Shot:
    x: int
    y: int
    vx: int
    vy: int
    weapon: int
    damage: int
    hostile: bool = False
    life: int = 36
    hit: set[int] = field(default_factory=set)


@dataclass
class Pickup:
    kind: str
    x: int
    y: int
    life: int = 900


@dataclass
class Relay:
    x: int
    y: int = FLOOR - 40
    active: bool = False


def overlap(a, b) -> bool:
    return a.x < b.x + b.w and a.x + a.w > b.x and a.y < b.y + b.h and a.y + a.h > b.y


class NeonGame:
    def __init__(self, seed: int = 0, variant: str = "campaign", difficulty: str = "hard"):
        if variant not in ("campaign", "horde", "tutorial"):
            raise ValueError("unknown Neon Protocol variant")
        if difficulty not in ("easy", "medium", "hard", "extreme"):
            raise ValueError("unknown difficulty")
        self.seed, self.variant, self.difficulty = seed, variant, difficulty
        self.rng = random.Random(seed)
        self.player = Player()
        self.frames = 0
        self.status = "running"
        self.width = 4200 if variant == "campaign" else 1100
        self.weapon, self.ammo, self.fire_cooldown = 0, [-1, 24, 8], 0
        self.enemies: list[Enemy] = []
        self.shots: list[Shot] = []
        self.pickups: list[Pickup] = []
        self.fields: list[dict] = []
        self.events: list[dict] = []
        self.next_uid = 1
        self.kills, self.shots_fired, self.damage_taken, self.dashes = 0, 0, 0, 0
        self.wave, self.cleared, self.break_ticks = 0, 0, 45
        self.lesson, self.start_x = 0, self.player.x
        self.action_held, self.jump_held = False, False
        self.aim = (400, 480)
        self.exit_x = self.width - 150
        self.relays = [Relay(x) for x in (1260, 2600, 3850)] if variant == "campaign" else []
        self.doors = [(1400, 0, 24, FLOOR), (2740, 0, 24, FLOOR)] if variant == "campaign" else []
        self.hazards = [(1850, 130), (3140, 150)] if variant == "campaign" else []
        self.platforms = [(0, FLOOR, self.width, 80)]
        deck = [(340, 425, 160, 18), (580, 340, 180, 18), (860, 425, 170, 18)]
        self.platforms.extend(deck)
        if variant == "campaign":
            self.platforms.extend([(1610, 425, 160, 18), (2000, 360, 180, 18), (2340, 425, 180, 18),
                                   (2940, 425, 160, 18), (3310, 350, 180, 18), (3600, 425, 160, 18)])
            for kind, x, y in [("stalker", 640, 480), ("drone", 880, 290), ("sentry", 1150, 480),
                               ("drone", 1660, 300), ("stalker", 1900, 480), ("stalker", 2170, 480),
                               ("sentry", 2450, 480), ("drone", 3070, 285), ("sentry", 3390, 480),
                               ("stalker", 3530, 480), ("titan", 3740, 462)]:
                self.spawn_enemy(kind, x, y)
            self.pickups = [Pickup("shield", 500, 480), Pickup("overcharge", 680, 310),
                            Pickup("speed", 1700, 390), Pickup("health", 2050, 480),
                            Pickup("ammo", 2390, 390), Pickup("shield", 2870, 480),
                            Pickup("overcharge", 3360, 320), Pickup("health", 3600, 480)]
        elif variant == "tutorial":
            self.relays = [Relay(940)]
            self.spawn_enemy("dummy", 550, 480)
            self.pickups = [Pickup("shield", 790, 480)]
        else:
            self.player.x = 535

    def emit(self, kind: str, x: int, y: int, **data):
        self.events.append({"kind": kind, "x": x, "y": y, **data})

    def spawn_enemy(self, kind: str, x: int, y: int) -> Enemy:
        e = Enemy(self.next_uid, kind, x, y, ENEMY_HP[kind], cooldown=self.rng.randrange(20, 45))
        if kind == "titan":
            e.w, e.h = 48, 58
        elif kind == "drone":
            e.h = 24
        self.next_uid += 1
        self.enemies.append(e)
        return e

    def door_locked(self, index: int) -> bool:
        return not self.relays[index].active

    def solids(self):
        return self.platforms + [d for i, d in enumerate(self.doors) if self.door_locked(i)]

    def _blocked(self, x: int, y: int, w: int, h: int) -> bool:
        return any(x < sx + sw and x + w > sx and y < sy + sh and y + h > sy
                   for sx, sy, sw, sh in self.solids())

    def _move(self, body, dx: int, dy: int) -> tuple[bool, bool]:
        """Pixel stepping prevents fast dashes and falling bodies tunnelling through solids."""
        blocked_x = blocked_y = False
        for _ in range(abs(dx)):
            nx = body.x + (1 if dx > 0 else -1)
            if nx < 0 or nx + body.w > self.width or self._blocked(nx, body.y, body.w, body.h):
                blocked_x = True
                break
            body.x = nx
        for _ in range(abs(dy)):
            ny = body.y + (1 if dy > 0 else -1)
            if ny < 0 or self._blocked(body.x, ny, body.w, body.h):
                blocked_y = True
                break
            body.y = ny
        return blocked_x, blocked_y

    def request_dash(self, direction: int = 0) -> bool:
        p = self.player
        if self.status != "running" or p.hp <= 0 or p.dash_cooldown:
            return False
        p.dash, p.dash_cooldown, p.iframes = 4, 24, max(p.iframes, 6)
        p.dash_dir = (1 if direction > 0 else -1) if direction else p.facing
        self.dashes += 1
        if self.variant == "tutorial" and self.lesson == 4:
            self.lesson = 5
            # Always provide a pickup for this lesson, even if the first was collected earlier.
            self.pickups.append(Pickup("overcharge", min(self.width - 50, p.x + 80), p.y))
        return True

    def step(self, inputs: Inputs | None = None, select: int | None = None, cycle: int = 0):
        if self.status != "running":
            return
        self.events = []
        p = self.player
        if p.hp <= 0:
            self.status = "dead"
            return
        inp = inputs or Inputs(pointer_x=p.x + 150, pointer_y=p.y + 15)
        self.frames += 1
        if select is not None and 0 <= select < 3:
            self.weapon = select
        elif cycle:
            self.weapon = (self.weapon + (1 if cycle > 0 else -1)) % 3
        self.aim = (inp.pointer_x, inp.pointer_y)
        for attr in ("iframes", "dash_cooldown", "overcharge", "speed", "shield_time"):
            setattr(p, attr, max(0, getattr(p, attr) - 1))
        if not p.shield_time:
            p.shield = 0
        self.fire_cooldown = max(0, self.fire_cooldown - 1)
        move = 1 if inp.x > 0 else -1 if inp.x < 0 else 0
        if move:
            p.facing = move
        p.vx = move * (10 if p.speed else 7)
        jumped = inp.y < 0 and not self.jump_held and p.grounded
        if jumped:
            p.vy = -18
            self.emit("jump", p.x, p.y)
        self.jump_held = inp.y < 0
        p.vy = min(18, p.vy + 2)
        dx = p.dash_dir * 24 if p.dash else p.vx
        if p.dash:
            p.dash -= 1
            self.emit("dash", p.x, p.y)
        _, hit_y = self._move(p, dx, p.vy)
        p.grounded = hit_y and p.vy > 0
        if hit_y:
            p.vy = 0
        if inp.b2 and not self.fire_cooldown:
            self._fire(inp.pointer_x, inp.pointer_y)
        self._enemies()
        self._projectiles()
        self._fields()
        self._pickups()
        for x, width in self.hazards:
            if self.hazard_active() and p.x + p.w > x and p.x < x + width and p.y + p.h > FLOOR - 12:
                self.hurt_player(14)
        pressed = inp.y > 0 and not self.action_held
        self.action_held = inp.y > 0
        if pressed:
            self._interact()
        if self.variant == "horde":
            self._horde()
        elif self.variant == "tutorial":
            if self.lesson == 0 and abs(p.x - self.start_x) >= 70:
                self.lesson = 1
            elif self.lesson == 1 and jumped:
                self.lesson = 2
            elif self.lesson == 2 and any(e["kind"] == "hit" for e in self.events):
                self.lesson = 3
            elif self.lesson == 3 and self.weapon != 0:
                self.lesson = 4
        if p.hp <= 0:
            self.status = "dead"

    def hazard_active(self) -> bool:
        return self.frames % 90 >= 60  # 4 seconds safe (last second warning), 2 seconds active

    @staticmethod
    def velocity(x: int, y: int, tx: int, ty: int, speed: int) -> tuple[int, int]:
        d = math.hypot(tx - x, ty - y)
        if not d:
            return speed, 0
        vx, vy = round((tx - x) / d * speed), round((ty - y) / d * speed)
        return vx, vy

    def _fire(self, tx: int, ty: int):
        slot, p = self.weapon, self.player
        if slot and self.ammo[slot] <= 0:
            self.emit("empty", p.x, p.y)
            self.fire_cooldown = 4
            return
        speed, damage, cooldown = ((30, 12, 3), (70, 40, 12), (18, 14, 18))[slot]
        if p.overcharge:
            damage *= 2
        if slot:
            self.ammo[slot] -= 1
        sx, sy = p.x + p.w // 2, p.y + 15
        vx, vy = self.velocity(sx, sy, tx, ty, speed)
        self.shots.append(Shot(sx, sy, vx, vy, slot, damage))
        self.fire_cooldown = cooldown
        self.shots_fired += 1
        self.emit("shot", sx, sy, weapon=slot)

    def hurt_player(self, damage: int):
        p = self.player
        if p.iframes or p.hp <= 0 or self.variant == "tutorial":
            return
        damage = max(1, damage * {"easy": 50, "medium": 75, "hard": 100, "extreme": 150}[self.difficulty] // 100)
        absorbed = min(p.shield, damage)
        p.shield -= absorbed
        damage -= absorbed
        p.hp = max(0, p.hp - damage)
        p.iframes = 8
        self.damage_taken += damage
        self.emit("hurt", p.x, p.y, damage=damage, absorbed=absorbed)

    def _hurt_enemy(self, e: Enemy, damage: int, weapon: int, sx: int):
        if e.kind == "sentry" and weapon == 0 and (sx - e.x) * e.facing > 0:
            damage = max(1, damage // 3)
        e.hp -= damage
        self.emit("hit", e.x + e.w // 2, e.y + e.h // 2, damage=damage, uid=e.uid)
        if e.hp <= 0 and e in self.enemies:
            self.enemies.remove(e)
            self.kills += int(e.kind != "dummy")
            self.emit("kill", e.x, e.y, enemy=e.kind)
            if e.kind == "dummy":
                self.spawn_enemy("dummy", 550, 480)
            elif self.rng.randrange(3) == 0:
                kind = self.rng.choice(("health", "ammo", "shield", "overcharge", "speed"))
                self.pickups.append(Pickup(kind, e.x, min(e.y, FLOOR - 30)))

    def _enemies(self):
        p = self.player
        for e in list(self.enemies):
            if e.kind == "dummy" or abs(e.x - p.x) > 850:
                continue
            e.facing = 1 if p.x > e.x else -1
            e.cooldown = max(0, e.cooldown - 1)
            if e.kind == "drone":
                if abs(e.x - p.x) > 220:
                    self._move(e, e.facing * 3, 0)
                target_y = max(180, min(350, p.y - 100))
                self._move(e, 0, 2 if e.y < target_y else -2 if e.y > target_y else 0)
            elif e.kind in ("stalker", "titan"):
                e.vy = min(18, e.vy + 2)
                speed = 5 if e.kind == "stalker" else 2
                blocked, grounded = self._move(e, e.facing * speed, e.vy)
                if grounded:
                    e.vy = -16 if blocked else 0
                if overlap(e, p):
                    self.hurt_player(12 if e.kind == "stalker" else 22)
            if e.kind == "stalker":
                continue
            if e.cooldown == 0 and e.windup == 0:
                e.windup = 10
            if e.windup:
                e.windup -= 1
                if not e.windup:
                    sx, sy = e.x + e.w // 2, e.y + e.h // 2
                    vx, vy = self.velocity(sx, sy, p.x + p.w // 2, p.y + 18, 9)
                    self.shots.append(Shot(sx, sy, vx, vy, 0, 10 if e.kind != "titan" else 18, True, 100))
                    if e.kind == "titan":
                        self.shots.extend([Shot(sx, sy, vx, vy - 2, 0, 12, True, 100),
                                           Shot(sx, sy, vx, vy + 2, 0, 12, True, 100)])
                    e.cooldown = 35 if e.kind == "drone" else 28 if e.kind == "sentry" else 40
                    self.emit("enemy_shot", sx, sy)

    def _vortex(self, s: Shot):
        self.fields.append({"x": s.x, "y": s.y, "life": 45, "damage": s.damage})
        self.emit("vortex", s.x, s.y)

    def _projectiles(self):
        for s in list(self.shots):
            s.life -= 1
            count = max(abs(s.vx), abs(s.vy), 1)
            ox, oy = s.x, s.y
            stopped = False
            for i in range(1, count + 1):
                s.x, s.y = ox + round(s.vx * i / count), oy + round(s.vy * i / count)
                if s.x < 0 or s.x >= self.width or s.y < 0 or s.y > FLOOR or self._blocked(s.x, s.y, 2, 2):
                    stopped = True
                elif s.hostile:
                    p = self.player
                    if p.x <= s.x <= p.x + p.w and p.y <= s.y <= p.y + p.h:
                        self.hurt_player(s.damage)
                        stopped = True
                else:
                    for e in list(self.enemies):
                        if e.uid not in s.hit and e.x <= s.x <= e.x + e.w and e.y <= s.y <= e.y + e.h:
                            s.hit.add(e.uid)
                            self._hurt_enemy(e, s.damage, s.weapon, ox)
                            if s.weapon != 1:
                                stopped = True
                            break
                if stopped:
                    break
            if stopped or s.life <= 0:
                if s.weapon == 2 and not s.hostile:
                    self._vortex(s)
                if s in self.shots:
                    self.shots.remove(s)
                self.emit("impact", s.x, s.y, hostile=s.hostile)

    def _fields(self):
        for f in list(self.fields):
            f["life"] -= 1
            if f["life"] % 5 == 0:
                for e in list(self.enemies):
                    if math.hypot(e.x + e.w // 2 - f["x"], e.y + e.h // 2 - f["y"]) < 95:
                        self._hurt_enemy(e, f["damage"], 2, f["x"])
            if f["life"] <= 0:
                self.fields.remove(f)

    def _pickups(self):
        p = self.player
        for item in list(self.pickups):
            item.life -= 1
            if item.life <= 0:
                self.pickups.remove(item)
                continue
            if abs(p.x + p.w // 2 - item.x) > 34 or abs(p.y + p.h // 2 - item.y) > 40:
                continue
            if item.kind == "health":
                if p.hp >= 100:
                    continue
                p.hp = min(100, p.hp + 30)
            elif item.kind == "ammo":
                self.ammo[1], self.ammo[2] = min(48, self.ammo[1] + 12), min(16, self.ammo[2] + 4)
            elif item.kind == "shield":
                p.shield, p.shield_time = 60, 150
            elif item.kind == "overcharge":
                p.overcharge = 90
            elif item.kind == "speed":
                p.speed = 120
            self.pickups.remove(item)
            self.emit("pickup", item.x, item.y, pickup=item.kind)
            if self.variant == "tutorial" and self.lesson == 5:
                self.lesson = 6

    def relay_secure(self, relay: Relay) -> bool:
        index = self.relays.index(relay)
        left = self.doors[index - 1][0] if index and self.doors else 0
        right = self.doors[index][0] if index < len(self.doors) else self.width
        return not any(e.kind != "dummy" and left <= e.x < right and abs(e.x - relay.x) < 360
                       for e in self.enemies)

    def _interact(self):
        p = self.player
        for r in self.relays:
            if abs(p.x + p.w // 2 - r.x) < 60 and abs(p.y - r.y) < 65 and not r.active:
                if not self.relay_secure(r):
                    self.emit("locked", r.x, r.y)
                elif self.variant != "tutorial" or self.lesson == 6:
                    r.active = True
                    p.hp = 100
                    self.ammo[1], self.ammo[2] = max(24, self.ammo[1]), max(8, self.ammo[2])
                    self.emit("checkpoint", r.x, r.y)
                    if self.variant == "tutorial":
                        self.status = "won"
                return
        if self.variant == "campaign" and abs(p.x - self.exit_x) < 70 and p.grounded:
            if all(r.active for r in self.relays):
                self.status = "won"
                self.emit("extraction", p.x, p.y)
            else:
                self.emit("locked", p.x, p.y)

    def _horde(self):
        if self.enemies:
            return
        if self.break_ticks > 0:
            self.break_ticks -= 1
            if not self.break_ticks:
                self.wave += 1
                kinds = ["stalker", "drone"] + (["sentry"] if self.wave >= 2 else [])
                for i in range(2 + self.wave * 2):
                    kind = "titan" if self.wave % 3 == 0 and i == 0 else self.rng.choice(kinds)
                    x = 50 + (i // 2) * 32 if i % 2 == 0 else self.width - 90 - (i // 2) * 32
                    self.spawn_enemy(kind, x, 260 if kind == "drone" else FLOOR - (58 if kind == "titan" else 36))
                self.emit("wave", self.player.x, self.player.y, wave=self.wave)
        else:
            self.cleared = self.wave
            self.break_ticks = 75
            for kind, x in zip(("health", "ammo", "shield", "overcharge"), (400, 480, 600, 680), strict=True):
                self.pickups.append(Pickup(kind, x, FLOOR - 30))
            self.emit("wave_clear", self.player.x, self.player.y, wave=self.wave)

    def snapshot(self):
        return copy.deepcopy(self.__dict__)

    def restore(self, snapshot):
        self.__dict__ = copy.deepcopy(snapshot)

    def state_hash(self) -> str:
        state = {k: v for k, v in self.__dict__.items() if k not in ("rng", "events")}

        def encode(value):
            if isinstance(value, set):
                return sorted(value)
            return asdict(value)

        state["rng"] = self.rng.getstate()
        return hashlib.sha256(json.dumps(state, default=encode, sort_keys=True).encode()).hexdigest()
