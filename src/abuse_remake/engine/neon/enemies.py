"""Neon enemies: state machines that see, hear, warn each other and react to being hurt.

Every enemy perceives the player through the tile map (line of sight), hears gunfire within
the weapon's noise radius, and screams an alert that spreads to its neighbours a few ticks
later. Damage interrupts what it is doing (flinch, knock-back, falling off the ceiling).

- Xeno Crawler: the Abuse ant reimagined. Hangs from ceilings and walks them upside-down,
  drops onto the player, climbs walls, spits acid from above, runs, leaps gaps, crouches and
  pounces, dodges when shot at, and retreats when badly hurt.
- Stinger: a flyer that circles at range, telegraphs, dives along a line and pulls away.
- Sentry: a wall or ceiling turret that pops out when it sees you, leads its target, fires a
  burst and retracts. Armoured while retracted.
- Strider: a heavy walker with a frontal shield (pulse and scatter deflect), lobbed plasma
  and a ground shockwave stomp; weak from behind.
- Watcher drone: patrols with a searchlight. If it spots you (or is shot) it raises an
  alarm that opens the vent nests and wakes everything nearby.
- Nest: a vent that releases crawlers once disturbed.
- Core Warden: the boss, in three phases.
"""

from __future__ import annotations

from dataclasses import dataclass

from .fixed import SIN, angle_diff, approach, dist, iatan2, px, sign, turn_toward, vec
from .physics import Body, integrate, on_ceiling, step_x, step_y
from .tilemap import LADDER, ONEWAY, OPAQUE, SHIFT
from .weapons import Shot, hostile_shot

HP = {"crawler": 30, "stinger": 24, "sentry": 42, "strider": 170, "drone": 18, "nest": 70,
      "warden": 2200, "target": 20}
SIZE = {"crawler": (28, 18), "stinger": (30, 24), "sentry": (20, 20), "strider": (36, 54),
        "drone": (24, 22), "nest": (26, 22), "warden": (72, 88), "target": (22, 22)}
DROP_CHANCE = {"crawler": 18, "stinger": 25, "sentry": 35, "strider": 100, "drone": 45, "nest": 60,
               "warden": 0, "target": 0}
SCORE = {"crawler": 10, "stinger": 15, "sentry": 20, "strider": 60, "drone": 15, "nest": 25, "warden": 500,
         "target": 0}


@dataclass
class Enemy(Body):
    uid: int = 0
    kind: str = ""
    hp: int = 1
    max_hp: int = 1
    state: str = "idle"
    t: int = 0
    facing: int = -1
    alerted: bool = False
    spread: int = 0
    flinch: int = 0
    cd: int = 0
    cd2: int = 0
    lost: int = 0
    home_x: int = 0
    home_y: int = 0
    surface: str = "floor"
    flash: int = 0
    aim: int = 0
    dead: bool = False
    elite: bool = False
    owner: int = 0  # the nest that released it
    touch_cd: int = 0  # contact damage cooldown (separate from attack cooldowns)

    # --- perception ---
    def eye(self) -> tuple[int, int]:
        return self.cx, self.y + min(6, self.h // 3)

    def sees(self, game, reach: int, cone: bool = False) -> bool:
        p = game.player
        if not p.alive:
            return False
        ex, ey = self.eye()
        if abs(p.cx - ex) > reach or abs(p.cy - ey) > reach or dist(p.cx - ex, p.cy - ey) > reach:
            return False
        if cone and not self.alerted and (p.cx - ex) * self.facing < -12 and dist(p.cx - ex, p.cy - ey) > 56:
            return False
        g = game.grid
        return g.line_clear(ex, ey, p.cx, p.cy) or g.line_clear(ex, ey, p.cx, p.y + 6)

    def alert(self, game, scream: bool = True) -> None:
        if self.alerted:
            return
        self.alerted = True
        self.spread = 7
        if scream:
            game.emit("alert", self.cx, self.y, enemy=self.kind, uid=self.uid)

    def hittable(self) -> bool:
        return not self.dead

    def deflects(self) -> bool:
        return False

    def heard(self, game, x: int, y: int) -> None:
        """Gunfire or an explosion within earshot."""
        self.alert(game)

    # --- damage ---
    def damage(self, game, amount: int, kind: str, sx: int, sy: int, knock: int = 0) -> int:
        if self.dead or not self.hittable() or amount <= 0:
            return 0
        amount = self.shielded(game, amount, kind, sx)
        if amount <= 0:
            return 0
        self.hp -= amount
        self.flash = 4
        game.emit("hit", self.cx, self.cy, damage=amount, uid=self.uid, enemy=self.kind, shot=kind)
        if self.hp <= 0:
            game.kill(self, sx, sy)
            return amount
        self.alert(game)
        self.react(game, amount, sx, sy, knock)
        return amount

    def shielded(self, game, amount: int, kind: str, sx: int) -> int:
        return amount

    def react(self, game, amount: int, sx: int, sy: int, knock: int) -> None:
        pass

    def touch(self, game, damage: int, kind: str = "bite") -> None:
        p = game.player
        if self.touch_cd == 0 and p.alive and self.overlaps(p):
            if p.hurt(game, damage, self.cx, kind):
                game.emit(kind, self.cx, self.cy, enemy=self.kind)
            self.touch_cd = 20

    def tick_common(self, game) -> None:
        for name in ("cd", "cd2", "flash", "touch_cd"):
            v = getattr(self, name)
            if v > 0:
                setattr(self, name, v - 1)
        if self.spread:
            self.spread -= 1
            if self.spread == 0:
                game.alert_near(self.cx, self.cy, 170, self.uid)

    def update(self, game) -> None:
        self.tick_common(game)
        getattr(self, "s_" + self.state)(game)

    def ledge_ahead(self, game, d: int) -> bool:
        """No floor within two tiles below the front foot."""
        fx = self.x + self.w + 1 if d > 0 else self.x - 2
        g = game.grid
        ty = self.bottom >> SHIFT
        return all(g.at(fx >> SHIFT, ty + k) not in OPAQUE and g.at(fx >> SHIFT, ty + k) not in (ONEWAY, LADDER)
                   for k in range(0, 2))


# ---------------------------------------------------------------- crawler
@dataclass
class Crawler(Enemy):
    wall_dir: int = 0
    dodge_cd: int = 0
    spit_cd: int = 0

    def update(self, game) -> None:
        self.tick_common(game)
        if self.dodge_cd:
            self.dodge_cd -= 1
        if self.spit_cd:
            self.spit_cd -= 1
        if self.flinch:
            self.flinch -= 1
            if self.surface == "floor":
                integrate(game, self)
                if self.grounded:
                    self.vx = self.vx * 7 // 10
            if self.flinch == 0:
                if self.hp * 100 < self.max_hp * 40 and game.rng.randrange(3) == 0:
                    self.state, self.t = "retreat", 20
                else:
                    self.state = "chase" if self.surface == "floor" else self.state
            return
        getattr(self, "s_" + self.state)(game)
        if self.surface == "floor" and self.state in ("chase", "pounce", "drop", "land", "retreat", "crouch"):
            self.touch(game, 16 if self.state == "pounce" else 11)

    def _fall(self, game) -> None:
        self.surface, self.state = "floor", "drop"
        self.vx, self.vy = self.vx // 2, 0
        game.emit("crawler_drop", self.cx, self.cy, uid=self.uid)

    def s_hang(self, game) -> None:
        p = game.player
        if not on_ceiling(game, self):
            self._fall(game)
            return
        dx = p.cx - self.cx
        if self.sees(game, 230):
            if not self.alerted:
                self.alert(game)
            if abs(dx) < 34 and p.y > self.bottom:
                self._fall(game)
                return
            self.state = "ceil"

    def s_ceil(self, game) -> None:
        p = game.player
        dx = p.cx - self.cx
        sees = self.sees(game, 300)
        self.lost = 0 if sees else self.lost + 1
        if self.lost > 120:
            self.state = "hang"
            return
        if sees and abs(dx) < 22 and p.y > self.bottom:
            self._fall(game)
            return
        if sees and self.spit_cd == 0 and p.y > self.bottom + 16 and 36 < abs(dx) < 210:
            self.state, self.t = "spit", 11
            game.emit("crawler_wind", self.cx, self.cy, uid=self.uid)
            return
        d = sign(dx) or self.facing
        self.facing = d
        nx = self.x + d * 2
        g = game.grid
        support = g.at((nx + self.w // 2) >> SHIFT, (self.y - 1) >> SHIFT) in OPAQUE
        if support and abs(dx) > 6:
            if step_x(game, self, d * (2 if game.frames % 3 else 3)):
                self.state = "hang"
        elif not support and sees and p.y > self.bottom and abs(dx) < 120:
            self._fall(game)

    def s_spit(self, game) -> None:
        self.t -= 1
        if self.t <= 0:
            p = game.player
            a = iatan2(p.cy - self.cy, p.cx - self.cx)
            hostile_shot(game, "acid", self.cx, self.bottom, a, px(5.5), 10, gravity=px(0.18), life=60)
            game.emit("spit", self.cx, self.bottom, uid=self.uid)
            self.spit_cd = 75
            self.state = "ceil"

    def s_drop(self, game) -> None:
        integrate(game, self)
        if self.grounded:
            self.state, self.t = "land", 7
            game.emit("crawler_land", self.cx, self.bottom, uid=self.uid)

    def s_land(self, game) -> None:
        self.vx = 0
        integrate(game, self)
        self.t -= 1
        if self.t <= 0:
            self.state = "chase"
            self.alert(game)

    def s_idle(self, game) -> None:
        self.vx = self.facing * px(1)
        hit, _ = integrate(game, self)
        if hit or (self.grounded and self.ledge_ahead(game, self.facing)):
            self.facing = -self.facing
        if self.sees(game, 250, cone=True):
            self.alert(game)
            self.state = "chase"

    def s_chase(self, game) -> None:
        p = game.player
        dx, dy = p.cx - self.cx, p.bottom - self.bottom
        sees = self.sees(game, 440)
        self.lost = 0 if sees else self.lost + 1
        if self.lost > 160:
            self.state, self.alerted = "idle", False
            return
        d = sign(dx) or self.facing
        self.facing = d
        speed = px(3.3) if not self.elite else px(3.8)
        if abs(dx) < 10:
            speed = 0
        self.vx = approach(self.vx, d * speed, px(0.6))
        grounded_before = self.grounded
        hit, _ = integrate(game, self)
        if not grounded_before:
            return
        if hit:
            if dy < -20 and abs(dx) < 140:
                self.surface, self.state, self.wall_dir = "wall", "climb", d
                self.vx = self.vy = 0
                return
            self.vy = -px(7)  # hop the obstacle
            return
        if self.grounded and self.ledge_ahead(game, d) and dy <= 24 and abs(dx) > 30:
            self.vy, self.vx = -px(7.2), d * px(4.6)  # leap the gap
            game.emit("crawler_leap", self.cx, self.bottom, uid=self.uid)
            return
        if not sees:
            return
        if self.grounded and dy < -36 and abs(dx) < 100 and self.cd == 0:
            self.vy = -px(9)
            self.vx = d * px(2.5)
            self.cd = 40
            self.state = "pounce"
            game.emit("pounce", self.cx, self.cy, uid=self.uid)
            return
        if self.grounded and abs(dx) < 120 and abs(dy) < 40 and self.cd == 0:
            self.state, self.t = "crouch", 7
            self.vx = 0
            game.emit("crawler_wind", self.cx, self.cy, uid=self.uid)

    def s_crouch(self, game) -> None:
        self.vx = 0
        integrate(game, self)
        self.t -= 1
        if self.t <= 0:
            self.state, self.t = "pounce", 0
            self.vx = self.facing * px(5.6)
            self.vy = -px(6.4)
            self.cd = 48
            game.emit("pounce", self.cx, self.cy, uid=self.uid)

    def s_pounce(self, game) -> None:
        self.t += 1
        integrate(game, self)
        if self.grounded and self.t > 2:
            self.state, self.t = "land", 5

    def s_climb(self, game) -> None:
        p = game.player
        g = game.grid
        blocked = step_y(game, self, -2)
        side = (self.x - 1) >> SHIFT if self.wall_dir < 0 else (self.x + self.w) >> SHIFT
        wall_mid = g.at(side, (self.y + self.h // 2) >> SHIFT) in OPAQUE
        wall_low = g.at(side, (self.bottom - 1) >> SHIFT) in OPAQUE
        if blocked:
            self.surface, self.state = "ceil", "ceil"
            return
        if not wall_mid and not wall_low:
            step_x(game, self, self.wall_dir * 10)  # over the top
            self.surface, self.state = "floor", "chase"
            self.vy = 0
            return
        if p.bottom > self.bottom + 24 or not p.alive:
            self.surface = "floor"
            self.state = "drop"

    def s_retreat(self, game) -> None:
        p = game.player
        d = -(sign(p.cx - self.cx) or 1)
        self.facing = d
        self.vx = approach(self.vx, d * px(3.6), px(0.6))
        hit, _ = integrate(game, self)
        self.t -= 1
        if self.t <= 0 or hit or (self.grounded and self.ledge_ahead(game, d)):
            self.state = "chase"
            self.facing = -d

    def heard(self, game, x, y) -> None:
        self.alert(game)
        p = game.player
        if self.surface == "floor" and self.state == "chase" and self.grounded and self.dodge_cd == 0 \
                and abs(angle_diff(p.aim, iatan2(self.cy - p.shoulder()[1], self.cx - p.cx))) < 40 \
                and game.rng.randrange(3) == 0:
            self.vy = -px(6.5)
            self.vx = self.facing * px(2.5)
            self.dodge_cd = 70
            game.emit("dodge", self.cx, self.cy, uid=self.uid)
        if self.state == "hang":
            self.state = "ceil"

    def react(self, game, amount, sx, sy, knock) -> None:
        if self.surface != "floor":
            self.surface = "floor"
            self.state = "drop"
            self.vx = 0
            game.emit("crawler_drop", self.cx, self.cy, uid=self.uid)
            return
        if amount >= 6 or knock:
            d = 1 if self.cx >= sx else -1
            self.flinch = 6
            self.vx = d * (px(2.5) + knock)
            if self.grounded:
                self.vy = -px(2.5)
            self.state = "chase"


# ---------------------------------------------------------------- stinger
@dataclass
class Stinger(Enemy):
    surface: str = "air"

    def fly(self, game) -> tuple[bool, bool]:
        return integrate(game, self, gravity=0, oneway=False)

    def update(self, game) -> None:
        self.tick_common(game)
        if self.flinch:
            self.flinch -= 1
            self.fly(game)
            self.vx, self.vy = self.vx * 8 // 10, self.vy * 8 // 10
            if self.flinch == 0:
                self.state, self.t = "recover", 14
            return
        getattr(self, "s_" + self.state)(game)

    def _steer(self, game, tx: int, ty: int, top: int, accel: int) -> None:
        wx = max(-top, min(top, (tx - self.cx) * 256 // 14))
        wy = max(-top, min(top, (ty - self.cy) * 256 // 14))
        self.vx = approach(self.vx, wx, accel)
        self.vy = approach(self.vy, wy, accel)
        for o in game.enemies:
            if o is not self and o.kind == "stinger" and abs(o.cx - self.cx) < 34 and abs(o.cy - self.cy) < 34:
                self.vx += px(0.4) if self.cx >= o.cx else -px(0.4)
                self.vy += px(0.3) if self.cy >= o.cy else -px(0.3)
        hx, hy = self.fly(game)
        if hx:
            self.vx = -self.vx // 2
        if hy:
            self.vy = -self.vy // 2

    def s_idle(self, game) -> None:
        f = (game.frames * 5 + self.uid * 97) % 1024
        self._steer(game, self.home_x + SIN[f] * 28 // 1024, self.home_y + SIN[(f * 2) % 1024] * 10 // 1024,
                    px(1.4), px(0.15))
        self.facing = sign(self.vx) or self.facing
        if self.sees(game, 280):
            self.alert(game)
            self.state = "stalk"

    def s_stalk(self, game) -> None:
        p = game.player
        sees = self.sees(game, 420)
        self.lost = 0 if sees else self.lost + 1
        if self.lost > 200:
            self.state, self.alerted = "idle", False
            self.home_x, self.home_y = self.cx, self.cy
            return
        side = 1 if self.cx >= p.cx else -1
        f = (game.frames * 9 + self.uid * 131) % 1024
        tx = p.cx + side * 120
        ty = p.y - 64 + SIN[f] * 22 // 1024
        self._steer(game, tx, ty, px(3.6), px(0.35))
        self.facing = 1 if p.cx > self.cx else -1
        if sees and self.cd == 0 and dist(p.cx - self.cx, p.cy - self.cy) < 270:
            self.state, self.t = "wind", 14
            game.emit("stinger_wind", self.cx, self.cy, uid=self.uid)

    def s_wind(self, game) -> None:
        self.vx = approach(self.vx, 0, px(0.5))
        self.vy = approach(self.vy, -px(0.6), px(0.5))
        self.fly(game)
        self.t -= 1
        if self.t <= 0:
            p = game.player
            tx = p.cx + p.vx * 6 // 256
            ty = p.cy + 4
            a = iatan2(ty - self.cy, tx - self.cx)
            self.vx, self.vy = vec(a, px(7.6))
            self.aim = a
            self.state, self.t = "dive", 26
            game.emit("dive", self.cx, self.cy, uid=self.uid)

    def s_dive(self, game) -> None:
        hx, hy = self.fly(game)
        self.t -= 1
        p = game.player
        if p.alive and self.overlaps(p):
            p.hurt(game, 12, self.cx, "sting")
            game.emit("sting", self.cx, self.cy)
            self.state, self.t = "recover", 18
            return
        if hx or hy or self.t <= 0:
            self.state, self.t = "recover", 18

    def s_recover(self, game) -> None:
        self.vy = approach(self.vy, -px(3), px(0.5))
        self.vx = self.vx * 9 // 10
        hx, hy = self.fly(game)
        self.t -= 1
        if self.t <= 0:
            self.state = "stalk"
            self.cd = 45 + game.rng.randrange(40)

    def react(self, game, amount, sx, sy, knock) -> None:
        d = 1 if self.cx >= sx else -1
        self.flinch = 5
        self.vx = d * (px(3) + knock)
        self.vy = -px(1.5)


# ---------------------------------------------------------------- sentry
MOUNT_ANGLE = {"ceil": 256, "floor": 768, "left": 0, "right": 512}


@dataclass
class Sentry(Enemy):
    mount: str = "ceil"
    out: int = 0
    burst: int = 0
    state: str = "hidden"
    surface: str = "mount"

    def hittable(self) -> bool:
        return not self.dead and self.out >= 4

    def deflects(self) -> bool:
        return self.out < 4

    def muzzle(self) -> tuple[int, int]:
        dx, dy = vec(self.aim, 10)
        return self.cx + dx, self.cy + dy

    def update(self, game) -> None:
        self.tick_common(game)
        getattr(self, "s_" + self.state)(game)

    def _track(self, game, step: int) -> None:
        p = game.player
        lead = 8
        tx, ty = p.cx + p.vx * lead // 256, p.cy + p.vy * lead // 512
        want = iatan2(ty - self.cy, tx - self.cx)
        base = MOUNT_ANGLE[self.mount]
        off = angle_diff(base, want)
        want = (base + max(-230, min(230, off))) % 1024
        self.aim = turn_toward(self.aim, want, step)

    def s_hidden(self, game) -> None:
        if self.sees(game, 300) or (self.alerted and self.sees(game, 400)):
            self.state = "rise"
            self.aim = MOUNT_ANGLE[self.mount]
            game.emit("sentry_up", self.cx, self.cy, uid=self.uid)

    def s_rise(self, game) -> None:
        self.out += 1
        if self.out >= 8:
            self.state, self.t = "aim", 12

    def s_aim(self, game) -> None:
        self._track(game, 22)
        self.t -= 1
        if self.t <= 0:
            self.state, self.burst, self.t = "burst", 3, 0

    def s_burst(self, game) -> None:
        self._track(game, 10)
        self.t -= 1
        if self.t <= 0:
            mx, my = self.muzzle()
            jitter = game.rng.randrange(-10, 11)
            hostile_shot(game, "bolt", mx, my, self.aim + jitter, px(7.5), 9, life=60)
            game.emit("enemy_shot", mx, my, enemy="sentry", angle=self.aim)
            self.burst -= 1
            self.t = 5
            if self.burst == 0:
                self.state, self.t = "cool", 28

    def s_cool(self, game) -> None:
        self._track(game, 12)
        self.t -= 1
        if self.t <= 0:
            if self.sees(game, 340):
                self.state, self.t, self.lost = "aim", 8, 0
            else:
                self.lost += 1
                if self.lost > 30:
                    self.state = "lower"

    def s_lower(self, game) -> None:
        self.out -= 1
        if self.out <= 0:
            self.out = 0
            self.state, self.lost = "hidden", 0


# ---------------------------------------------------------------- strider
@dataclass
class Strider(Enemy):
    turn: int = 0

    def update(self, game) -> None:
        self.tick_common(game)
        getattr(self, "s_" + self.state)(game)
        self.touch(game, 14, "crush")

    def _face_player(self, game) -> None:
        p = game.player
        want = sign(p.cx - self.cx) or self.facing
        if want != self.facing:
            self.turn += 1
            if self.turn > 14:  # heavy: turning around takes half a second, so it can be flanked
                self.facing, self.turn = want, 0
                game.emit("strider_turn", self.cx, self.cy, uid=self.uid)
        else:
            self.turn = 0

    def s_idle(self, game) -> None:
        self.vx = self.facing * px(0.8)
        hit, _ = integrate(game, self)
        if hit or (self.grounded and self.ledge_ahead(game, self.facing)):
            self.facing = -self.facing
        if self.sees(game, 340, cone=True):
            self.alert(game)
            self.state = "stalk"

    def s_stalk(self, game) -> None:
        p = game.player
        sees = self.sees(game, 460)
        self.lost = 0 if sees else self.lost + 1
        self._face_player(game)
        dx, dy = p.cx - self.cx, p.bottom - self.bottom
        want = 0 if abs(dx) < 70 else self.facing * px(1.5)
        self.vx = approach(self.vx, want, px(0.2))
        hit, _ = integrate(game, self)
        if hit and self.grounded:
            self.vy = -px(6)
        if self.lost > 220:
            self.state, self.alerted = "idle", False
            return
        if not self.grounded:
            return
        if self.cd2 == 0 and abs(dx) < 90 and abs(dy) < 40:
            self.state, self.t = "stomp_wind", 16
            self.vx = 0
            game.emit("stomp_wind", self.cx, self.bottom, uid=self.uid)
        elif self.cd == 0 and sees and dist(dx, dy) < 400:
            self.state, self.t = "lob_wind", 14
            self.vx = 0
            game.emit("lob_wind", self.cx, self.y, uid=self.uid)

    def s_lob_wind(self, game) -> None:
        integrate(game, self)
        self.t -= 1
        if self.t <= 0:
            shots = 3 if self.elite else 1
            for i in range(shots):
                lob(game, self.cx + self.facing * 14, self.y + 10, game.player, 16, extra=(i - shots // 2) * 9)
            game.emit("enemy_shot", self.cx, self.y + 10, enemy="strider")
            self.cd = 75
            self.state = "stalk"

    def s_stomp_wind(self, game) -> None:
        integrate(game, self)
        self.t -= 1
        if self.t <= 0:
            stomp(game, self, 14, px(6))
            self.cd2 = 100
            self.state = "stalk"

    def s_stagger(self, game) -> None:
        integrate(game, self)
        self.vx = self.vx * 8 // 10
        self.t -= 1
        if self.t <= 0:
            self.state = "stalk"

    def shielded(self, game, amount, kind, sx) -> int:
        front = (sx - self.cx) * self.facing > 0
        if front and kind in ("pulse", "pellet"):
            game.emit("deflect", self.cx + self.facing * 18, self.cy, uid=self.uid)
            self.alert(game)
            return 0
        if not front and kind not in ("blast",):
            return amount * 3 // 2  # the exposed reactor on its back
        return amount

    def react(self, game, amount, sx, sy, knock) -> None:
        if amount >= 40 and self.state != "stagger":
            self.state, self.t = "stagger", 12
            self.vx = (1 if self.cx >= sx else -1) * px(2)


def lob(game, x: int, y: int, target, damage: int, extra: int = 0, radius: int = 26):
    """A plasma arc that lands near the target (ballistic, integer)."""
    g = px(0.3)
    dx = target.cx + extra * 4 - x
    dy = target.bottom - 10 - y
    t = max(18, min(42, dist(dx, dy) // 7))
    vx = dx * 256 // t
    vy = (dy * 256 - g * t * t // 2) // t
    game.shots.append(Shot("plasma", x, y, vx, vy, damage, hostile=True, life=t + 30, gravity=g, radius=radius))


def stomp(game, e: Enemy, damage: int, speed: int) -> None:
    y = e.bottom - 5
    for d in (-1, 1):
        game.shots.append(Shot("shock", e.cx + d * (e.w // 2), y, d * speed, 0, damage, hostile=True, life=34))
    game.emit("stomp", e.cx, e.bottom, uid=e.uid, big=e.kind == "warden")
    game.noise(e.cx, e.cy, 200)


# ---------------------------------------------------------------- watcher drone
@dataclass
class Drone(Enemy):
    spot: int = 0
    alarmed: bool = False
    surface: str = "air"
    state: str = "patrol"

    def update(self, game) -> None:
        self.tick_common(game)
        getattr(self, "s_" + self.state)(game)

    def s_patrol(self, game) -> None:
        f = (game.frames * 7 + self.uid * 61) % 1024
        self.vx = self.facing * px(1.2)
        self.vy = (self.home_y + SIN[f] * 6 // 1024 - self.cy) * 64
        hx, _ = integrate(game, self, gravity=0, oneway=False)
        if hx or abs(self.cx - self.home_x) > 170 and sign(self.cx - self.home_x) == self.facing:
            self.facing = -self.facing
        p = game.player
        ex, ey = self.eye()
        look = 128 if self.facing > 0 else 384  # 45 degrees down, ahead
        a = iatan2(p.cy - ey, p.cx - ex)
        in_cone = abs(angle_diff(look, a)) < 110 and dist(p.cx - ex, p.cy - ey) < 230
        if in_cone and self.sees(game, 230):
            self.spot += 1
            if self.spot >= 7:
                self.raise_alarm(game)
        else:
            self.spot = max(0, self.spot - 1)

    def raise_alarm(self, game) -> None:
        if not self.alarmed:
            self.alarmed = True
            self.alerted = True
            self.state = "hunt"
            game.emit("alarm", self.cx, self.cy, uid=self.uid)
            game.alarm(self.cx, self.cy)

    def s_hunt(self, game) -> None:
        p = game.player
        tx, ty = p.cx, p.y - 84
        self.vx = approach(self.vx, max(-px(2.2), min(px(2.2), (tx - self.cx) * 24)), px(0.25))
        self.vy = approach(self.vy, max(-px(2.2), min(px(2.2), (ty - self.cy) * 24)), px(0.25))
        integrate(game, self, gravity=0, oneway=False)
        self.facing = 1 if p.cx > self.cx else -1
        if self.cd == 0 and self.sees(game, 320):
            a = iatan2(p.cy - self.cy, p.cx - self.cx)
            hostile_shot(game, "bolt", self.cx, self.cy + 6, a, px(6), 6, life=60)
            game.emit("enemy_shot", self.cx, self.cy, enemy="drone", angle=a)
            self.cd = 50

    def react(self, game, amount, sx, sy, knock) -> None:
        self.raise_alarm(game)


# ---------------------------------------------------------------- training target
@dataclass
class Target(Enemy):
    surface: str = "air"
    state: str = "idle"

    def s_idle(self, game) -> None:
        f = (game.frames * 6 + self.uid * 211) % 1024
        self.y = self.home_y - self.h // 2 + SIN[f] * 5 // 1024


# ---------------------------------------------------------------- nest
@dataclass
class Nest(Enemy):
    count: int = 3
    active: bool = False
    surface: str = "mount"
    state: str = "closed"
    spawn_point: bool = False  # Horde: a permanent spawn vent, not a target

    def hittable(self) -> bool:
        return not self.dead and not self.spawn_point

    def update(self, game) -> None:
        self.tick_common(game)
        if self.spawn_point:
            return
        p = game.player
        if not self.active and (self.alerted or (dist(p.cx - self.cx, p.cy - self.cy) < 150 and self.sees(game, 150))):
            self.activate(game)
        if self.active and self.count > 0:
            self.t -= 1
            alive = sum(1 for e in game.enemies if e.owner == self.uid and not e.dead)
            if self.t <= 0 and alive < 3:
                game.spawn_from_nest(self, "crawler")
                self.count -= 1
                self.t = 85

    def activate(self, game) -> None:
        if not self.active:
            self.active = True
            self.alerted = True
            self.t = 20
            self.state = "open"
            game.emit("nest_open", self.cx, self.cy, uid=self.uid)

    def heard(self, game, x, y) -> None:
        pass  # nests wake to alarms, sight and damage, not to every shot

    def react(self, game, amount, sx, sy, knock) -> None:
        self.activate(game)


# ---------------------------------------------------------------- the boss
@dataclass
class Warden(Enemy):
    phase: int = 1
    roar: int = 0
    laser: str = ""  # "", "charge", "sweep", "vent"
    laser_t: int = 0
    laser_cd: int = 90
    laser_high: bool = False
    laser_hit: bool = False
    left: int = 0
    right: int = 0
    floor: int = 0
    stomp_wind: int = 0  # the raised-leg telegraph before a stomp
    sweep_x: int = 0  # centre of the moving laser segment
    sweep_dir: int = 1

    def hittable(self) -> bool:
        return not self.dead and self.roar == 0

    def deflects(self) -> bool:
        return self.roar > 0

    def beam(self) -> tuple[int, int]:
        """The sweeping laser band (top, bottom) in world pixels."""
        if self.laser_high:
            return self.floor - 62, self.floor - 30
        return self.floor - 30, self.floor - 12

    def update(self, game) -> None:
        self.tick_common(game)
        p = game.player
        if not self.alerted:
            # dormant until the runner comes into the arena (or is heard)
            if abs(p.cx - self.cx) < 560 and self.sees(game, 600):
                self.alert(game, scream=False)
                self.roar = 30
                game.emit("boss_wake", self.cx, self.cy)
            return
        if self.roar:
            self.roar -= 1
            self.vx = 0
            integrate(game, self)
            return
        frac = self.hp * 100 // self.max_hp
        if self.phase == 1 and frac < 66 or self.phase == 2 and frac < 33:
            self.phase += 1
            self.roar = 45
            self.laser, self.laser_cd = "", 40
            game.emit("boss_phase", self.cx, self.cy, phase=self.phase)
            game.alarm(self.cx, self.cy, radius=900)
            return
        want = sign(p.cx - self.cx) or self.facing
        if want != self.facing and self.laser != "sweep":
            self.facing = want
        speed = (px(1.0), px(1.1), px(1.4))[self.phase - 1]
        target_v = 0 if abs(p.cx - self.cx) < 60 or self.laser in ("charge", "sweep", "vent") else self.facing * speed
        if (self.facing < 0 and self.x < self.left) or (self.facing > 0 and self.x + self.w > self.right):
            target_v = 0
        self.vx = approach(self.vx, target_v, px(0.2))
        integrate(game, self)
        self.touch(game, 20, "crush")
        if self.stomp_wind:
            self.stomp_wind -= 1
            if self.stomp_wind == 0:
                stomp(game, self, 18, px(7))
                self.cd2 = 95 if self.phase < 3 else 75
        elif self.cd2 == 0 and abs(p.cx - self.cx) < 120 and p.bottom > self.floor - 40 and self.laser != "vent":
            self.stomp_wind = 15  # half a second of warning: jump the shockwave
            self.cd2 = 200
            game.emit("stomp_wind", self.cx, self.bottom, uid=self.uid, big=True)
        if self.cd == 0 and self.laser in ("", "vent"):
            n = 3 if self.phase < 3 else 4
            for i in range(n):
                lob(game, self.cx, self.y + 14, p, 14, extra=(i - n // 2) * 12, radius=26)
            game.emit("enemy_shot", self.cx, self.y + 14, enemy="warden")
            self.cd = (110, 90, 120)[self.phase - 1]
        if self.phase == 3:
            self._laser(game)

    def _laser(self, game) -> None:
        p = game.player
        if self.laser == "":
            self.laser_cd -= 1
            if self.laser_cd <= 0:
                self.laser, self.laser_t = "charge", 36
                self.laser_high = game.rng.randrange(2) == 1
                game.emit("laser_charge", self.cx, self.cy, high=self.laser_high)
        elif self.laser == "charge":
            self.laser_t -= 1
            if self.laser_t <= 0:
                self.laser, self.laser_t, self.laser_hit = "sweep", 40, False
                self.sweep_dir = (1 if p.cx >= self.cx else -1)
                self.sweep_x = self.cx
                game.emit("laser_fire", self.cx, self.cy, high=self.laser_high)
        elif self.laser == "sweep":
            # an 80 px beam segment sweeps out across the arena at 22 px/tick: it passes any one
            # spot in about four ticks, so a timed jump clears the low beam and a crouch the high one
            self.laser_t -= 1
            self.sweep_x += self.sweep_dir * 22
            top, bottom = self.beam()
            if not self.laser_hit and p.alive and p.y < bottom and p.bottom > top \
                    and abs(p.cx - self.sweep_x) < SWEEP_HALF + p.w // 2:
                if p.hurt(game, 20, self.sweep_x, "laser"):
                    self.laser_hit = True
            past = self.sweep_x > self.right + 120 or self.sweep_x < self.left - 120
            if self.laser_t <= 0 or past:
                self.laser, self.laser_t = "vent", 75
                game.emit("vent", self.cx, self.cy)
        elif self.laser == "vent":
            self.laser_t -= 1
            if self.laser_t <= 0:
                self.laser, self.laser_cd = "", 50

    def shielded(self, game, amount, kind, sx) -> int:
        if self.laser == "vent":
            return amount * 2
        return amount

    def heard(self, game, x, y) -> None:
        self.alert(game, scream=False)


SWEEP_HALF = 40

KINDS = {"crawler": Crawler, "stinger": Stinger, "sentry": Sentry, "strider": Strider, "drone": Drone,
         "nest": Nest, "warden": Warden, "target": Target}


def make_enemy(game, kind: str, tx: int, ty: int, uid: int, args: tuple = ()) -> Enemy:
    """Create an enemy standing on (or hanging from, or mounted on) the tile at (tx, ty)."""
    w, h = SIZE[kind]
    hp = HP[kind] * game.enemy_hp_scale // 100
    cls = KINDS[kind]
    x = tx * 16 + 8 - w // 2
    y = (ty + 1) * 16 - h
    g = game.grid
    e = cls(x=x, y=y, w=w, h=h, uid=uid, kind=kind, hp=hp, max_hp=hp, home_x=tx * 16 + 8, home_y=ty * 16 + 8)
    e.facing = -1 if game.rng.randrange(2) else 1
    if kind == "crawler":
        if g.at(tx, ty - 1) in OPAQUE and g.at(tx, ty + 1) not in OPAQUE:
            e.surface, e.state, e.y = "ceil", "hang", ty * 16
        else:
            e.state = "idle"
    elif kind == "sentry":
        if g.at(tx, ty - 1) in OPAQUE:
            e.mount, e.y = "ceil", ty * 16
        elif g.at(tx, ty + 1) in OPAQUE:
            e.mount = "floor"
        elif g.at(tx - 1, ty) in OPAQUE:
            e.mount, e.x, e.y = "left", tx * 16, ty * 16 + 8 - h // 2
        else:
            e.mount, e.x, e.y = "right", tx * 16 + 16 - w, ty * 16 + 8 - h // 2
        e.aim = MOUNT_ANGLE[e.mount]
    elif kind in ("stinger", "drone", "target"):
        e.y = ty * 16 + 8 - h // 2
        e.home_y = e.cy
        e.state = "idle" if kind != "drone" else "patrol"
    elif kind == "nest":
        e.count = int(args[0]) if args else 3
        if g.at(tx, ty - 1) in OPAQUE and g.at(tx, ty + 1) not in OPAQUE:
            e.y = ty * 16
    elif kind == "warden":
        e.left, e.right = e.x - 16 * 14, e.x + w + 16 * 14
        e.floor = (ty + 1) * 16
        e.state = "boss"
        e.facing = -1
    elif kind == "strider":
        e.state = "idle"
    if "elite" in args:
        e.elite = True
        e.hp = e.max_hp = e.hp * 2
    return e
