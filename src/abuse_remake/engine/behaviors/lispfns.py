"""Python equivalents of the Lisp builtins the ported behaviours use.

Each helper cites its builtin in historicalsource/abuse@01cce80 abuse/src/clisp.c (the
``c_caller``/``l_caller`` case number) or abuse/src/lisp.c (arithmetic). Lisp evaluates function
arguments left to right, so the ported code calls ``random`` in the same order the Lisp does;
that keeps the shared random table in step with the original.
"""

from __future__ import annotations

from ..cmath import cdiv, cmod, lisp_atan2, lisp_cos, lisp_sin
from ..obj import BLOCKED_DOWN, BLOCKED_LEFT, BLOCKED_RIGHT, BLOCKED_UP, GameObject


class Fixed(int):
    """A Lisp fixed-point value (16.16), as returned by ``cos`` and ``sin``."""


def lnum(v) -> int:
    """lnumber_value (lisp.c:501): a fixed-point value is shifted down 16 bits."""
    if isinstance(v, Fixed):
        return int(v) >> 16
    if v is True:
        return 1
    if v is None or v is False:
        return 0
    return int(v)


def lfix(v) -> int:
    """lfixed_point_value (lisp.c:575): a plain number is shifted up 16 bits."""
    return int(v) if isinstance(v, Fixed) else lnum(v) << 16


def lcos(a: int) -> Fixed:
    return Fixed(lisp_cos(a))


def lsin(a: int) -> Fixed:
    return Fixed(lisp_sin(a))


def ladd(*args) -> int:
    return sum(lnum(a) for a in args)  # lisp.c case 8


def lsub(first, *rest) -> int:
    x = lnum(first)  # lisp.c case 9
    for a in rest:
        x -= lnum(a)
    return x


def lmul(*args):
    """lisp.c case 28: fixed-point multiply when the first argument is fixed point.

    In the integer branch the original evaluates every argument twice and multiplies the
    second values (lisp.c:1904-1931). Callers whose arguments have side effects, such as
    ``(random n)``, must repeat them; see ``weapons.create_dead_parts``."""
    if isinstance(args[0], Fixed):
        s = 1 << 16
        for a in args:
            s = (s >> 8) * (lfix(a) >> 8)
        return Fixed(s)
    s = 1
    for a in args:
        s *= lnum(a)
    return s


def ldiv(first, *rest) -> int:
    x = lnum(first)  # lisp.c case 29 (numbers only, C division)
    for a in rest:
        x = cdiv(x, lnum(a))
    return x


def lmod(a, b) -> int:
    return cmod(lnum(a), lnum(b))


def atan2(dy, dx) -> int:
    return lisp_atan2(lnum(dy), lnum(dx))  # lisp.c case 56: (atan2 y x)


# --- object state -----------------------------------------------------------------------

def state_time(o: GameObject) -> int:
    return o.aistate_time  # clisp.c case 10


def set_aistate(o: GameObject, n: int) -> None:
    o.set_aistate_time(0)  # clisp.c case 8
    o.set_aistate(n)


def go_state(o: GameObject, n: int):
    """l_caller case 0: set the state, zero its time and run the AI again immediately."""
    o.set_aistate(n)
    o.set_aistate_time(0)
    return o.ctype.ai_fun(o)


def activated(o: GameObject) -> bool:
    """l_caller case 39: on when nothing is linked, or the first link's aistate is non-zero."""
    if not o.objs:
        return True
    return o.objs[0].aistate != 0


def touching_bg(o: GameObject) -> bool:
    """c_caller case 22: picture spaces of the object and the nearest player overlap."""
    p = o.world.attacker(o)
    if p is None:
        return False
    x1, y1, x2, y2 = p.picture_space()
    xp1, yp1, xp2, yp2 = o.picture_space()
    return not (xp1 > x2 or xp2 < x1 or yp1 > y2 or yp2 < y1)


def distx(o: GameObject) -> int:
    return abs(o.x - o.world.attacker(o).x)  # c_caller case 1


def disty(o: GameObject) -> int:
    return abs(o.y - o.world.attacker(o).y)  # c_caller case 2


def random(o: GameObject, n: int) -> int:
    return o.world.rng.jrandom(n)  # c_caller case 9


def site_angle(o: GameObject, target: GameObject) -> int:
    """c_caller case 153: angle from o's centre to target's centre (y up)."""
    x = target.x - o.x
    y = -(target.y - cdiv(target.picture_height(), 2) - (o.y - cdiv(o.picture_height(), 2)))
    return lisp_atan2(y, x)


def set_course(o: GameObject, ang: int, mag) -> None:
    """c_caller case 154: velocity of magnitude ``mag`` at ``ang`` degrees."""
    m = lfix(mag)
    xvel = (lisp_cos(ang) >> 8) * (m >> 8)
    o.xvel = xvel >> 16
    o.set_fxvel((xvel & 0xFFFF) >> 8)
    yvel = -(lisp_sin(ang) >> 8) * (m >> 8)
    o.yvel = yvel >> 16
    o.set_fyvel((yvel & 0xFFFF) >> 8)


def set_frame_angle(o: GameObject, ang1: int, ang2: int, ang: int) -> bool:
    """c_caller case 155: pick the animation frame that faces ``ang``."""
    tframes = o.total_frames()
    if ang1 < 0:
        ang1 = cmod(ang1, 360) + 360
    elif ang1 >= 360:
        ang1 = cmod(ang1, 360)
    if ang2 < 0:
        ang2 = cmod(ang2, 360) + 360
    elif ang2 >= 360:
        ang2 = cmod(ang2, 360)
    ang = cmod(ang + cdiv(90, tframes), 360)
    if ang1 > ang2:
        if ang2 < ang < ang1:
            return False
        if ang >= ang1:
            f = cdiv((ang - ang1) * tframes, 359 - ang1 + ang2 + 1)
        else:
            f = cdiv((359 - ang1 + ang) * tframes, 359 - ang1 + ang2 + 1)
    elif ang < ang1 or ang > ang2:
        return False
    else:
        f = cdiv((ang - ang1) * tframes, ang2 - ang1 + 1)
    o.current_frame = f if o.direction > 0 else tframes - f - 1
    return True


def jump_state(o: GameObject, state: str) -> None:
    frame = o.current_frame  # c_caller case 156: change state, keep the frame number
    o.set_state(state)
    o.current_frame = frame


def lisp_try_move(o: GameObject, xv: int, yv: int, check_top: bool = True) -> bool:
    """c_caller case 200: move as far as allowed; T if the full move was possible."""
    oxv, oyv = xv, yv
    _, xv, yv = o.try_move(o.x, o.y, xv, yv, 1 | (2 if check_top else 0))
    o.x += xv
    o.y += yv
    return oxv == xv and oyv == yv


def can_see(o: GameObject, x1, y1, x2, y2, block_all) -> bool:
    """c_caller case 202: an unobstructed line from (x1, y1) to (x2, y2)."""
    nx2, ny2 = x2, y2
    x2, y2 = o.world.tiles.foreground_intersect(x1, y1, x2, y2)
    if x2 != nx2 or y2 != ny2:
        return False
    if block_all:
        _, x2, y2 = o.world.all_boundary_setback(o, x1, y1, x2, y2)
    else:
        _, x2, y2 = o.world.boundary_setback(o, x1, y1, x2, y2)
    return x2 == nx2 and y2 == ny2


def bmove(o: GameObject, exclude):
    """l_caller case 2: the hit object, None if a wall was hit, or True if nothing was hit."""
    hit, whit = o.bmove(exclude)
    if hit is not None:
        return hit
    if whit:
        return None
    return True


def do_damage(o: GameObject, amount: int, target: GameObject, xv: int = 0, yv: int = 0) -> None:
    """c_caller case 75: ``o`` damages ``target`` from o's position."""
    target.do_damage(amount, o, o.x, o.y, xv, yv)


def hurt_radius(o: GameObject, x, y, r, m, exclude, max_push) -> None:
    o.world.hurt_radius(x, y, r, m, o, exclude, max_push)  # c_caller case 143


def blocked_left(v) -> bool:
    return bool(lnum(v) & BLOCKED_LEFT)


def blocked_right(v) -> bool:
    return bool(lnum(v) & BLOCKED_RIGHT)


def blocked_up(v) -> bool:
    return bool(lnum(v) & BLOCKED_UP)


def blocked_down(v) -> bool:
    return bool(lnum(v) & BLOCKED_DOWN)


def play_sound(o: GameObject, name: str, volume: int = 127, x: int | None = None, y: int | None = None):
    o.world.emit("sound", name=name, volume=volume, x=o.x if x is None else x, y=o.y if y is None else y)


def add_panim(o: GameObject, name: str, x: int, y: int, direction: int) -> None:
    o.world.emit("panim", name=name, x=x, y=y, direction=direction)  # particle animation (visual)


def add_light(o: GameObject, ltype, x, y, r1, r2, xs, ys):
    return o.world.add_light(ltype, x, y, r1, r2, xs, ys)  # l_caller case 14


def link_light(o: GameObject, light) -> None:
    if light not in o.lights:
        o.lights.append(light)  # c_caller case 100
    light.known = True


def find_rgb(r: int, g: int, b: int) -> int:
    """Colours only matter to drawing; keep the RGB value instead of a palette index."""
    return (r << 16) | (g << 8) | b


# abuse.lsp: (setq bad_guy_list (list DARNEL ANT_ROOF TRACK_GUN SPRAY_GUN JUGGER ROB1 WHO
# ROCKET FLYER GREEN_FLYER BOSS_ANT)). Used by rocket targeting and weapon proximity.
BAD_GUY_NAMES = ("DARNEL", "ANT_ROOF", "TRACK_GUN", "SPRAY_GUN", "JUGGER", "ROB1", "WHO",
                 "ROCKET", "FLYER", "GREEN_FLYER", "BOSS_ANT")


def bad_guy_types(world) -> frozenset[int]:
    cached = world.globals.get("_bad_guy_types")
    if cached is None:
        cached = frozenset(world.types[n].index for n in BAD_GUY_NAMES if n in world.types)
        world.globals["_bad_guy_types"] = cached
    return cached
