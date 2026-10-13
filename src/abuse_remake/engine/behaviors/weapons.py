"""Projectiles, explosions and death debris.

Sources (historicalsource/abuse@01cce80 and data/original/lisp):
- fire_object: guns.lsp:34-193
- sgun_ai (the laser and turret bullets): abuse/src/cop.c:888-928 (compiled C; the Lisp
  version in weapons.lsp is commented out)
- grenade_ai, firebomb_ai, rocket_ai: weapons.lsp:28-55, 356-394
- explosions (exp_ai, explo_light, do_explo, do_small_explo): explo.lsp
- debris (create_dead_parts, get_dead_part, head_ai, bounce_move): ant.lsp:348-395, 572-582;
  duong.lsp:358-388
"""

from __future__ import annotations

from ..cmath import cdiv, lisp_atan2, lisp_cos, lisp_sin
from . import lisp
from .lispfns import (
    activated,
    bad_guy_types,
    blocked_left,
    blocked_right,
    can_see,
    find_rgb,
    go_state,
    hurt_radius,
    lmod,
    play_sound,
    random,
    set_aistate,
    set_course,
    set_frame_angle,
    state_time,
)

FRAME_PANIC = False  # clisp.c case 243: always 0 in a deterministic single-player run


def _link0(o):
    return o.objs[0] if o.objs else None


# --- fire_object (guns.lsp:34-193) -----------------------------------------------------

def _shotgun_bullet(world, creator, x, y, angle, lifetime, speed, bright, medium):
    b = world.spawn("SHOTGUN_BULLET", x, y)
    play_sound(b, "ZAP_SND")
    b.lvars["sgb_lifetime"] = lifetime
    b.lvars["sgb_speed"] = speed
    b.lvars["sgb_lastx"] = b.x
    b.lvars["sgb_lasty"] = b.y
    b.lvars["sgb_angle"] = angle
    b.lvars["sgb_bright_color"] = find_rgb(*bright)
    b.lvars["sgb_medium_color"] = find_rgb(*medium)
    if creator is not None:
        # (/ (xvel) 2) runs inside with_object, so it reads the new bullet's xvel, which is 0
        b.lvars["sgb_speed"] += cdiv(b.xvel, 2)
        b.add_object(creator)
    sgun_ai(b)
    return b


def fire_object(creator, wtype: int, x: int, y: int, angle: int, target):
    shot = _fire_object(creator, wtype, x, y, angle, target)
    if shot is not None:  # an output event for statistics; it draws no random numbers
        creator.world.emit("shot", uid=shot.uid, weapon=wtype, x=x, y=y,
                           by_player=creator.world.player_owned(shot))
    return shot


def _fire_object(creator, wtype: int, x: int, y: int, angle: int, target):
    world = creator.world
    if wtype == 0:
        return _shotgun_bullet(world, creator, x, y, angle, 6, 15, (255, 255, 200), (150, 150, 0))
    if wtype == 1:
        return _shotgun_bullet(world, creator, x, y, angle, 40, 6, (255, 128, 64), (255, 0, 0))
    if wtype == 10:
        return _shotgun_bullet(world, creator, x, y, angle, 6, 15, (255, 0, 0), (150, 0, 0))
    if wtype == 2:
        g = world.spawn("GRENADE", x, y)
        play_sound(g, "GRENADE_THROW", 127, x, y)
        set_course(g, angle, 20)
        if creator is not None:
            g.add_object(creator)
            g.xvel += creator.xvel
            g.yvel += creator.yvel
        set_frame_angle(g, 0, 359, angle)
        return g
    if wtype == 3:
        r = world.spawn("ROCKET", x, y)
        play_sound(r, "ROCKET_LAUNCH_SND", 127, x, y)
        r.set_aistate_time(0)
        r.set_aistate(angle)
        if creator is not None:
            r.add_object(creator)
        if target is not None and can_see(r, r.x, r.y, target.x, target.y, False):
            r.add_object(target)
        set_frame_angle(r, 0, 359, angle)
        r.lvars["speed"] = 5
        r.lvars["max_speed"] = 14 if (creator is not None and creator.controller is not None) else 10
        r.y = r.y + cdiv(r.picture_height(), 2)
        return r
    if wtype == 5:
        f = world.spawn("FIREBOMB", x, y)
        play_sound(f, "FIREBOMB_SND")
        set_course(f, angle, 20)
        if creator is not None:
            f.add_object(creator)
            f.yvel += creator.yvel
        return f
    raise NotImplementedError(f"fire_object type {wtype} is outside the Level 1 scope")


@lisp("sgun_ai")
def sgun_ai(o) -> bool:
    """cop.c:888-928: the laser bolt speeds up by 6/5 each tick and hits the first thing."""
    if o.lvars["sgb_lifetime"] == 0:
        return False
    o.lvars["sgb_lifetime"] -= 1
    o.lvars["sgb_lastx"] = o.x
    o.lvars["sgb_lasty"] = o.y
    o.lvars["sgb_speed"] = cdiv(o.lvars["sgb_speed"] * 6, 5)
    ang, mag = o.lvars["sgb_angle"], o.lvars["sgb_speed"]
    xvel = lisp_cos(ang) * mag
    o.xvel = xvel >> 16
    o.set_fxvel((xvel & 0xFFFF) >> 8)
    yvel = -lisp_sin(ang) * mag
    o.yvel = yvel >> 16
    o.set_fyvel((yvel & 0xFFFF) >> 8)
    who, whit = o.bmove(_link0(o))
    rng = o.world.rng
    if whit or (who is not None and "unactive_shield" in who.ctype.cflags and who.objs
                and who.objs[0].aistate == 0):
        o.lvars["sgb_lifetime"] = 0
        ex, ey = o.x + rng.jrand() % 4, o.y + rng.jrand() % 4  # C argument order taken as left to right
        o.world.add_object(o.world.create("EXPLODE5", ex, ey))
    elif who is not None and who.hurtable():
        o.lvars["sgb_lifetime"] = 0
        ex, ey = o.x + rng.jrand() % 4, o.y + rng.jrand() % 4
        o.world.add_object(o.world.create("EXPLODE3", ex, ey))
        who.do_damage(5, o, o.x, o.y, (lisp_cos(ang) * 10) >> 16, (lisp_sin(ang) * 10) >> 16)
    return True


@lisp("grenade_ai")
def grenade_ai(o) -> bool:
    """weapons.lsp:28-39: explode on touching anything, or when a bad guy is within 7 px."""
    if o.tick() == 0:
        if o.objs:
            mex, mey = o.x, o.y
            owner = o.objs[0]
            near = o.world.find_object_in_area(owner.x, owner.y, mex - 7, mey - 7, mex + 7, mey + 7,
                                               bad_guy_types(o.world), owner)
            if near is None:
                o.next_picture()
                return True
    return do_explo(o, 40, 36)


@lisp("firebomb_ai")
def firebomb_ai(o) -> bool:
    """weapons.lsp:43-55: burns along the ground for up to 20 ticks."""
    o.world.spawn("EXPLODE1", o.x - random(o, 5), o.y + random(o, 20), 0)
    hurt_radius(o, o.x, o.y, 60, 40, _link0(o), 10)
    if not (state_time(o) < 3 or o.xvel != 0):
        return False
    if not state_time(o) < 20:
        return False
    if o.direction == 1:
        return not blocked_right(o.move(0, 0, 0))
    if o.direction == -1:
        return not blocked_left(o.move(0, 0, 0))
    return False


@lisp("rocket_ai")
def rocket_ai(o) -> bool:
    """weapons.lsp:356-394: smoke trail, homing on the linked target, explode on contact."""
    if not FRAME_PANIC:
        rng = o.world.rng
        saved = rng.rand_on
        cx = o.x + random(o, 3)
        cy = o.y - random(o, 3) - cdiv(o.picture_height(), 2)
        cloud = o.world.spawn("SMALL_LIGHT_CLOUD", cx, cy)
        cloud.set_fade_count(11)
        rng.rand_on = saved  # the smoke must not change the random sequence
    if len(o.objs) > 1:
        tgt = o.objs[1]
        angle = lisp_atan2(o.y - tgt.y + 15, tgt.x - o.x)
        cur = o.aistate
        clock_dist = cur - angle if angle < cur else cur + (360 - angle)
        closest = 360 - clock_dist if clock_dist > 180 else clock_dist
        add = 23 if closest > 23 else (0 if closest < 5 else closest)
        if clock_dist > 180:  # Lisp set_aistate also zeroes aistate_time (clisp.c:1074-1078)
            set_aistate(o, lmod(cur + add, 360))
        else:
            set_aistate(o, lmod(cur - add + 360, 360))
    if o.lvars["speed"] < o.lvars["max_speed"]:
        o.lvars["speed"] += 2
    set_course(o, o.aistate, o.lvars["speed"])
    set_frame_angle(o, 0, 359, o.aistate)
    hit_something = False
    if o.hp == 0:
        hit_something = True
    else:
        res = o.bmove(_link0(o))
        if not (res[0] is None and not res[1]):  # bmove did not return T
            hit_something = True
        elif len(o.objs) > 1:
            tgt = o.objs[1]
            if abs(tgt.x - o.x) < 10 and abs(tgt.y - o.y - 15) < 10:
                hit_something = True
    if hit_something:
        return do_explo(o, 40, 50)
    return True


# --- explosions (explo.lsp) ----------------------------------------------------------------

@lisp("exp_ai")
def exp_ai(o) -> bool:
    if o.aitype == 0:
        return o.next_picture()
    o.change_aitype(o.aitype - 1)
    return True


@lisp("explo_light")
def explo_light(o) -> bool:
    if o.aistate == 0:
        light = o.world.add_light(0, o.x, o.y, 1, o.aitype, 0, 0)
        light.known = True
        o.lights.append(light)
        return go_state(o, 1)
    if o.aistate == 1:
        if state_time(o) > 3:
            if o.lights:
                o.world.remove_light(o.lights[0])
            return False
        return True
    return False


def do_explo(o, radius: int, amount: int) -> bool:
    play_sound(o, "GRENADE_SND")
    x1 = o.x + random(o, 10)
    y1 = random(o, 10) + o.y - 20
    o.world.spawn("EXPLODE1", x1, y1, 0)
    if not FRAME_PANIC:
        x2 = o.x - random(o, 10)
        y2 = o.y - random(o, 10) - 20
        o.world.spawn("EXPLODE1", x2, y2, 2)
        o.world.spawn("EXP_LIGHT", o.x, o.y, 100)
    hurt_radius(o, o.x, o.y, radius, amount, _link0(o), 20)
    o.world.emit("explosion", x=o.x, y=o.y, radius=radius)
    return False


def do_small_explo(o, radius: int, amount: int) -> bool:
    parts = (("EXPLODE3", 1, 0), ("EXPLODE2", 1, 2), ("EXPLODE3", -1, 1), ("EXPLODE3", -1, 2))
    for name, sign, aitype in parts:
        ex = o.x + sign * random(o, 5)
        ey = o.y + sign * random(o, 5)
        o.world.spawn(name, ex, ey, aitype)
    hurt_radius(o, o.x, o.y, radius, amount, _link0(o), 20)
    return False


# --- debris (ant.lsp, duong.lsp) -------------------------------------------------------------

DECAY_PART, FLAMING_PART, ELECTRIC_PART, NORMAL_PART = 0, 1, 2, 3
PART_ARRAYS = {
    "ant_dead_parts": ("AD_1", "AD_2", "AD_3", "AD_4", "AD_5", "AD_6",
                       "AD_7", "AD_8", "AD_9", "AD_10", "AD_11", "AD_12"),
    "cop_dead_parts": ("CP_1", "CP_2", "CP_3", "CP_4", "CP_5", "CP_6",
                       "CP_7", "CP_8", "CP_9", "CP_10", "CP_11", "CP_12"),
}


def get_dead_part(o, from_obj) -> int:
    if from_obj is None:
        return NORMAL_PART
    name = from_obj.ctype.name
    if name in ("GRENADE", "ROCKET", "FIREBOMB"):
        return FLAMING_PART
    if name in ("PLASMAGUN_BULLET", "LSABER_BULLET"):
        return ELECTRIC_PART
    return NORMAL_PART


def create_dead_parts(o, array: str, part_num: int, ptype: int) -> None:
    """Five flying body parts; the random table is restored afterwards (ant.lsp:348-378)."""
    names = PART_ARRAYS[array]
    d = o.direction
    rng = o.world.rng
    saved = rng.rand_on
    for k, extra_frames in ((0, 0), (1, 0), (2, 1), (2, 2), (2, 3)):
        p = o.world.spawn(names[part_num + k], o.x, o.y)
        p.change_aitype(ptype)
        for _ in range(extra_frames):
            p.next_picture()
        # (* dir (random 10)): Lisp's integer * evaluates each argument twice and multiplies
        # the second values (lisp.c:1904-1931), so two random numbers are drawn
        random(p, 10)
        p.xvel = d * random(p, 10)
        p.yvel = -random(p, 25)
    rng.rand_on = saved


def bounce_move(o, on_left=None, on_right=None, on_up=None, on_down=None, on_nothing=None):
    """duong.lsp:358-388. Returns what the Lisp returns: the value of the stub that ran
    (a missing stub counts as T), or nil when the move was blocked in no listed direction."""
    old_yv, old_xv = o.yvel, o.xvel
    status = o.float_tick()

    def run(stub):
        return True if stub is None else stub(o)

    if status is True or status is False:  # float_tick returned T (or nil for a dead object)
        return run(on_nothing) if status is True else False
    flags = status[0]
    if flags & 4:  # blocked up: bounce
        o.xvel = old_xv
        o.yvel = 2 - old_yv if old_yv > 1 else -old_yv
        return run(on_up)
    if flags & 8:  # blocked down
        o.xvel = old_xv
        o.yvel = 2 - old_yv if old_yv > 1 else -old_yv
        return run(on_down)
    if flags & 1:
        o.yvel = old_yv
        o.xvel = -old_xv
        return run(on_left)
    if flags & 2:
        o.yvel = old_yv
        o.xvel = -old_xv
        return run(on_right)
    return False


def _landed(o):
    o.set_state("dieing")
    o.set_aistate_time(0)
    o.set_aistate(1)
    return True


@lisp("head_ai")
def head_ai(o) -> bool:
    if o.aistate == 0:
        o.next_picture()
        o.yvel += 3
        bounce_move(o, on_down=_landed)
        return state_time(o) < 15 or not FRAME_PANIC
    return False


__all__ = ["fire_object", "create_dead_parts", "get_dead_part", "do_explo", "do_small_explo",
           "bounce_move", "activated"]
