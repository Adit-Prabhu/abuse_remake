"""Five futuristic weapons, their projectiles, the hitscan rail and explosions.

| slot | weapon | behaviour |
|---|---|---|
| 1 | PULSE CARBINE | unlimited fast cyan bolts |
| 2 | SCATTER ARC | five pink lasers in a fan, short range, knockback |
| 3 | RAIL LANCE | instant beam that pierces every enemy in line and stops at walls |
| 4 | PLASMA MORTAR | arcing, bouncing plasma that bursts; the blast breaks cracked walls |
| 5 | SEEKER SWARM | three homing micro-missiles |

Enemy projectiles (acid, sentry bolts, strider plasma, shockwaves) use the same ``Shot``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fixed import ANG, SUB, angle_diff, dist, iatan2, px, sign, turn_toward, vec
from .tilemap import BREAK, ONEWAY, OPAQUE, SHIFT


@dataclass(frozen=True)
class WeaponSpec:
    name: str
    short: str
    cooldown: int  # ticks between shots
    damage: int
    ammo_start: int  # rounds given with the weapon (-1: unlimited)
    ammo_max: int
    ammo_pickup: int  # rounds per ammo cell
    noise: int  # how far enemies hear it (px)


WEAPONS = (
    WeaponSpec("PULSE CARBINE", "PULSE", 4, 7, -1, -1, 0, 220),
    WeaponSpec("SCATTER ARC", "SCATTER", 17, 7, 20, 60, 10, 240),
    WeaponSpec("RAIL LANCE", "RAIL", 30, 48, 8, 30, 5, 320),
    WeaponSpec("PLASMA MORTAR", "MORTAR", 22, 55, 6, 24, 4, 300),
    WeaponSpec("SEEKER SWARM", "SEEKER", 26, 20, 5, 18, 3, 260),
)
RAIL_RANGE = 720
MUZZLE = 17  # px from the shoulder to the gun tip


@dataclass
class Shot:
    kind: str  # pulse pellet mortar seeker | acid bolt plasma shock spit
    x: int
    y: int
    vx: int  # sub-pixels per tick
    vy: int
    damage: int
    hostile: bool = False
    life: int = 40
    gravity: int = 0
    bounces: int = 0
    radius: int = 0  # blast radius (0: none)
    target: int = 0  # seeker target uid
    angle: int = 0
    speed: int = 0
    knock: int = 0
    rx: int = 0
    ry: int = 0
    age: int = 0
    hit: list = field(default_factory=list)


def muzzle(player) -> tuple[int, int]:
    sx, sy = player.shoulder()
    dx, dy = vec(player.aim, MUZZLE)
    return sx + dx, sy + dy


def fire(game, player) -> bool:
    """Fire the current weapon if it is ready. Returns True if a shot left the gun."""
    slot = game.weapon
    spec = WEAPONS[slot]
    if slot and (not game.owned[slot] or game.ammo[slot] <= 0):
        if game.fire_cd == 0:
            game.emit("empty", player.cx, player.cy, weapon=slot)
            game.fire_cd = 10
        return False
    sx, sy = player.shoulder()
    mx, my = muzzle(player)
    if not game.grid.line_clear(sx, sy, mx, my, 3):
        mx, my = sx, sy  # the gun tip is inside a wall: fire from the shoulder
    a = player.aim
    dmg = game.player_damage(spec.damage)
    if slot == 0:
        vx, vy = vec(a, px(14))
        game.shots.append(Shot("pulse", mx, my, vx, vy, dmg, life=42, angle=a))
    elif slot == 1:
        for i, spread in enumerate((-40, -20, 0, 20, 40)):
            speed = px(12) + (i % 2) * px(1.5)
            vx, vy = vec(a + spread, speed)
            game.shots.append(Shot("pellet", mx, my, vx, vy, dmg, life=11, angle=(a + spread) % ANG,
                                   knock=px(3)))
    elif slot == 2:
        _rail(game, player, mx, my, a, dmg)
    elif slot == 3:
        vx, vy = vec(a, px(8.5))
        game.shots.append(Shot("mortar", mx, my, vx, vy - px(1.5), dmg, life=60, gravity=px(0.32),
                               bounces=2, radius=46, angle=a))
    else:
        for spread in (-70, 0, 70):
            ang = (a + spread) % ANG
            vx, vy = vec(ang, px(5))
            game.shots.append(Shot("seeker", mx, my, vx, vy, dmg, life=75, radius=22, angle=ang,
                                   speed=px(5), target=_seek_target(game, mx, my, a)))
    if slot:
        game.ammo[slot] -= 1
    game.fire_cd = spec.cooldown * game.upgrade_pct("fire_cd") // 100
    game.shots_fired += 1
    game.emit("shot", mx, my, weapon=slot, angle=a)
    game.noise(player.cx, player.cy, spec.noise)
    return True


def _rail(game, player, x0, y0, angle, dmg):
    dx, dy = vec(angle, 4 * SUB)  # 4 px steps, kept in sub-pixels so shallow angles stay true
    x, y = x0, y0
    hit = []
    for i in range(1, RAIL_RANGE // 4):
        nx, ny = x0 + dx * i // SUB, y0 + dy * i // SUB
        if game.grid.opaque_px(nx, ny):
            break
        x, y = nx, ny
        for e in game.enemies:
            if e.uid not in hit and e.hittable() and e.contains(x, y, 3):
                hit.append(e.uid)
                e.damage(game, dmg, "rail", x0, y0)
    game.emit("rail", x0, y0, x2=x, y2=y, hits=len(hit))


def _seek_target(game, x, y, angle) -> int:
    best, best_d = 0, 380
    for e in game.enemies:
        if not e.hittable():
            continue
        d = dist(e.cx - x, e.cy - y)
        if d < best_d and abs(angle_diff(angle, iatan2(e.cy - y, e.cx - x))) < 220 \
                and game.grid.line_clear(x, y, e.cx, e.cy):
            best, best_d = e.uid, d
    return best


def update_shots(game) -> None:
    keep = []
    for s in game.shots:
        if _advance(game, s):
            keep.append(s)
    game.shots = keep


def _advance(game, s: Shot) -> bool:
    """Move one shot one tick. Returns False when it is spent."""
    s.age += 1
    s.life -= 1
    if s.kind == "seeker":
        _home(game, s)
    elif s.kind == "shock" and game.grid.at_px(s.x, s.y + 8) not in OPAQUE and game.grid.at_px(s.x, s.y + 8) != ONEWAY:
        return False  # the shockwave runs out of floor
    s.vy += s.gravity
    s.rx += s.vx
    s.ry += s.vy
    dx, dy = s.rx // SUB, s.ry // SUB
    s.rx -= dx * SUB
    s.ry -= dy * SUB
    n = max(abs(dx), abs(dy)) // 3 + 1
    ox, oy = s.x, s.y
    for i in range(1, n + 1):
        nx, ny = ox + dx * i // n, oy + dy * i // n
        if game.grid.opaque_px(nx, ny):
            if s.kind == "mortar" and s.bounces > 0 and game.grid.at_px(nx, ny) != BREAK:
                s.bounces -= 1
                if game.grid.opaque_px(nx, s.y):
                    s.vx = -s.vx * 3 // 5
                if game.grid.opaque_px(s.x, ny):
                    s.vy = -s.vy * 3 // 5
                    s.vx = s.vx * 4 // 5
                game.emit("bounce", s.x, s.y)
                return s.life > 0
            if s.kind == "shock":
                return False
            return _spend(game, s, s.x, s.y, wall=True)
        s.x, s.y = nx, ny
        if s.hostile:
            p = game.player
            if p.alive and p.contains(s.x, s.y, 1):
                if s.kind == "shock" and p.bottom < s.y - 2:
                    continue  # jumped over the shockwave
                p.hurt(game, s.damage, s.x - sign(s.vx) * 8, s.kind)
                return _spend(game, s, s.x, s.y)
        else:
            for e in game.enemies:
                if e.uid in s.hit or not e.contains(s.x, s.y, 2):
                    continue
                if not e.hittable():
                    if e.deflects():
                        game.emit("deflect", s.x, s.y)
                        return False
                    continue
                s.hit.append(e.uid)
                if s.radius:
                    return _spend(game, s, s.x, s.y)
                e.damage(game, s.damage, s.kind, s.x - sign(s.vx) * 6, s.y - sign(s.vy) * 6, knock=s.knock)
                return _spend(game, s, s.x, s.y)
    if s.life <= 0:
        if s.radius:
            return _spend(game, s, s.x, s.y)
        game.emit("fizzle", s.x, s.y, shot=s.kind)
        return False
    return True


def _spend(game, s: Shot, x: int, y: int, wall: bool = False) -> bool:
    if s.radius:
        explode(game, x, y, s.radius, s.damage, hostile=s.hostile, kind=s.kind)
    else:
        game.emit("impact", x, y, shot=s.kind, wall=wall, hostile=s.hostile)
    return False


def _home(game, s: Shot) -> None:
    target = next((e for e in game.enemies if e.uid == s.target and e.hittable()), None)
    if target is None and s.age % 6 == 0:
        s.target = _seek_target(game, s.x, s.y, s.angle)
        target = next((e for e in game.enemies if e.uid == s.target), None)
    if target is not None and s.age > 4:
        want = iatan2(target.cy - s.y, target.cx - s.x)
        s.angle = turn_toward(s.angle, want, 26)
    s.speed = min(px(11), s.speed + px(0.35))
    s.vx, s.vy = vec(s.angle, s.speed)


def explode(game, x: int, y: int, radius: int, damage: int, hostile: bool = False, kind: str = "blast") -> None:
    game.emit("explosion", x, y, radius=radius, source=kind)
    game.noise(x, y, 320)
    for e in list(game.enemies):
        d = dist(e.cx - x, e.cy - y) - min(e.w, e.h) // 3
        if d < radius and e.hittable() and not hostile:
            e.damage(game, damage * (radius - max(0, d) // 2) // radius, "blast", x, y, knock=px(4))
    p = game.player
    if hostile and p.alive:
        d = dist(p.cx - x, p.cy - y) - 8
        if d < radius:
            p.hurt(game, damage * (radius - max(0, d) // 2) // radius, x, "blast")
    if not hostile:
        g = game.grid
        r = radius
        for ty in range((y - r) >> SHIFT, ((y + r) >> SHIFT) + 1):
            for tx in range((x - r) >> SHIFT, ((x + r) >> SHIFT) + 1):
                if g.at(tx, ty) == BREAK and dist(tx * 16 + 8 - x, ty * 16 + 8 - y) <= r + 8:
                    game.break_tile(tx, ty)


def hostile_shot(game, kind: str, x: int, y: int, angle: int, speed: int, damage: int, **kw) -> Shot:
    vx, vy = vec(angle, speed)
    s = Shot(kind, x, y, vx, vy, damage, hostile=True, angle=angle, **kw)
    game.shots.append(s)
    return s


def solid_px(game, x: int, y: int) -> bool:
    return game.grid.at_px(x, y) in OPAQUE
