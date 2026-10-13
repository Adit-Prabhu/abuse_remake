"""Doors, force fields, hidden walls, trap doors, teleporters, platforms and the boulder.

Sources: data/original/lisp/doors.lsp, duong.lsp, teleport.lsp, platform.lsp, common.lsp.
``(remove_object x)`` in the Lisp only unlinks ``x`` (clisp.c case 99); an object is deleted
from the level when its AI returns nil.
"""

from __future__ import annotations

from ..cmath import cdiv, cmod
from . import lisp
from .lispfns import (
    activated,
    blocked_down,
    blocked_left,
    blocked_right,
    blocked_up,
    distx,
    disty,
    go_state,
    hurt_radius,
    lisp_try_move,
    play_sound,
    random,
    set_aistate,
    touching_bg,
)
from .logic import pressing_action_key
from .weapons import bounce_move


def push_char(o, xamount: int, yamount: int) -> None:
    """common.lsp:15-23: shove the player out of a closing door."""
    bg = o.world.bg(o)
    bgx, bgy = bg.x, bg.y
    if bgy <= o.y and disty(o) < yamount and distx(o) < xamount:
        amount = xamount - (bgx - o.x) if bgx > o.x else (o.x - bgx) - xamount
        lisp_try_move(bg, amount, 0)


def general_sdoor_ai(o, push: bool) -> bool:
    """doors.lsp:31-62: a door that opens while its first link's signal is on."""
    s = o.aistate
    if s == 0:
        if o.objs:
            if o.objs[0].aistate != 0:
                o.set_state("running")
                play_sound(o, "SWISH", 70)
                o.world.emit("door", uid=o.uid, opening=True, x=o.x, y=o.y)
                go_state(o, 1)
            else:
                o.set_state("stopped")
                if push:
                    push_char(o, o.picture_width() + 8, o.picture_height())
    elif s == 1:
        if not o.next_picture():
            o.set_state("blocking")
            set_aistate(o, 2)
    elif s == 2:
        if o.objs and o.objs[0].aistate == 0:
            o.set_state("walking")
            play_sound(o, "SWISH", 70)
            o.world.emit("door", uid=o.uid, opening=False, x=o.x, y=o.y)
            go_state(o, 3)
    elif s == 3:
        if not o.next_picture():
            o.set_state("stopped")
            set_aistate(o, 0)
    return True


@lisp("sdoor_ai")
def sdoor_ai(o) -> bool:
    return general_sdoor_ai(o, True)


@lisp("strap_door_ai")
def strap_door_ai(o) -> bool:
    return general_sdoor_ai(o, False)


def _ff_push(o, who, xamount: int) -> None:
    views = o.world.views
    idx = 0
    while who is not None:
        bgx, bgy = who.x, who.y
        if bgy >= o.y and bgy <= o.lvars["end_y"] + 20 and abs(bgx - o.x) < xamount:
            amount = xamount - (bgx - o.x) if bgx > o.x else (o.x - bgx) - xamount
            lisp_try_move(who, amount, 0)
        idx += 1
        who = views[idx].focus if idx < len(views) else None  # (next_focus who)


@lisp("ff_ai")
def ff_ai(o) -> bool:
    """doors.lsp:93-107: the force field pushes the player back while its signal is on."""
    o.world.rng.shift(random(o, 80))
    if activated(o):
        nowx, nowy = o.x, o.y
        if cmod(o.world.tick_counter, 4) == 0:
            play_sound(o, "FF_SND")
        lisp_try_move(o, 0, o.y + 200)  # find the floor (the original moves by y+200 pixels)
        o.lvars["end_y"] = o.y
        o.x, o.y = nowx, nowy
        first = o.world.views[0].focus if o.world.views else None
        _ff_push(o, first, 35)
    return True


def _wall_blown(o) -> bool:
    return o.hp == 0 or (len(o.objs) == 1 and o.objs[0].aistate != 0)


@lisp("hwall_ai")
def hwall_ai(o) -> bool:
    """doors.lsp:130-139: a breakable wall section; it explodes when shot to 0 hp or signalled."""
    if _wall_blown(o):
        o.world.spawn("EXPLODE1", o.x + 15, o.y - 7, 0)
        play_sound(o, "HWALL_SND")
        hurt_radius(o, o.x + 15 * o.direction, o.y - 7, 50, 60, o.world.bg(o), 20)
        o.world.emit("wall_destroyed", uid=o.uid, x=o.x, y=o.y)
        return False
    return True


@lisp("big_wall_ai")
def big_wall_ai(o) -> bool:
    if _wall_blown(o):
        o.world.spawn("EXPLODE1", o.x - 15, o.y - 7, 0)
        o.world.spawn("EXPLODE1", o.x + 15, o.y - 22, 0)
        ex = o.x + random(o, 5)
        ey = random(o, 5) + o.y - 20
        o.world.spawn("EXPLODE1", ex, ey, 0)
        play_sound(o, "HWALL_SND")
        hurt_radius(o, o.x, o.y - 15, 110, 120, o.world.bg(o), 20)
        o.world.emit("wall_destroyed", uid=o.uid, x=o.x, y=o.y)
        return False
    return True


@lisp("hwall_damage")
def hwall_damage(o, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
    if activated(o):
        o.damage_fun(amount, from_obj, hitx, hity, push_xvel, push_yvel)
        max_hp = o.ability("start_hp")
        if o.hp != 0 and not o.hp > max_hp:
            o.current_frame = cdiv(o.total_frames() * (max_hp - o.hp), max_hp)  # cracks show


@lisp("hwall_reload")
def hwall_reload(o) -> None:
    if o.hp == 60:  # walls saved with the old 60 hp are fixed up to 25
        o.set_hp(25)


@lisp("tp2_ai")
def tp2_ai(o) -> bool:
    """duong.lsp:228-266: stand in the teleporter and press the action key."""
    if not o.objs:
        return True
    s = o.aistate
    if s == 0:
        if touching_bg(o) and len(o.objs) == 1:
            bg = o.world.bg(o)
            if pressing_action_key(bg):
                o.add_object(bg)
                o.set_state("running")
                play_sound(o, "TELEPORTER_SND")
                set_aistate(o, 1)
    elif s == 1:
        if o.next_picture():
            x, y = o.x, o.y - 16
            fade = o.current_frame if o.current_frame < 16 else 15
            p = o.objs[1]
            p.x, p.y = x, y
            _cop_set_fade(p, fade)
            p.lvars["is_teleporting"] = 1
        else:
            dest = o.objs[0]
            p = o.objs[1]
            p.x, p.y = dest.x, dest.y - 16
            p.lvars["is_teleporting"] = 0
            _cop_set_fade(p, 0)
            o.remove_object(p)
            set_aistate(o, 0)
            o.world.emit("teleported", uid=o.uid, x=p.x, y=p.y)
    return True


def _cop_set_fade(p, value) -> None:
    """cop_ufun SET_FADE_COUNT (people.lsp:112-129): fade the player and its top half."""
    fn = p.ctype.user_fun
    if fn is not None and p.objs:
        p.set_fade_count(value)
        p.objs[0].set_fade_count(value)


@lisp("bolder_ai")
def bolder_ai(o) -> bool:
    """duong.lsp:279-327: a rolling boulder that bounces and hurts what it touches."""
    if o.objs and o.objs[0].aistate == 0:
        return True
    if o.hp == 0:
        play_sound(o, "P_EXPLODE_SND")
        for sign, aitype in ((1, 0), (1, 2), (-1, 1), (-1, 2)):
            ex = o.x + sign * random(o, 5)
            ey = o.y + sign * random(o, 5)
            o.world.spawn("EXPLODE1", ex, ey, aitype)
        for xv, yv in ((-4, -8), (4, -9), (2, -5), (-3, -5), (-1, 2)):
            rock = o.world.spawn("SMALL_BOLDER", o.x, o.y)
            rock.xvel, rock.yvel = xv, yv
        o.world.spawn("EXP_LIGHT", o.x, o.y, 100)
        return False
    o.next_picture()
    o.yvel += 1
    old_yv, old_xv = o.yvel, o.xvel
    status = o.float_tick()
    # The original binds variables called set_x/set_y in a let instead of calling them, so
    # the position is never rolled back and the platform push is always (0, 0).
    o.world.platform_push(o, 0, 0)
    hurt_radius(o, o.x, o.y, 19, 30, o, 15)
    if status is not True and status is not False:
        flags = status[0]
        if blocked_up(flags) or blocked_down(flags):
            if abs(old_yv) > 3:
                play_sound(o, "SBALL_SND")
            o.xvel = old_xv
            o.yvel = 2 - old_yv if old_yv > 1 else -old_yv
        elif blocked_left(flags) or blocked_right(flags):
            o.yvel = old_yv
            o.xvel = -old_xv
    return True


@lisp("bolder_cons")
def bolder_cons(o) -> None:
    o.xvel, o.yvel = -4, 0


@lisp("bold_dam")
def bold_dam(o, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
    ex = o.x + (10 - random(o, 20))
    ey = o.y - random(o, 30)
    o.world.spawn("EXPLODE3", ex, ey, 0)
    o.damage_fun(amount, from_obj, hitx, hity, cdiv(push_xvel, 10), cdiv(push_yvel, 2))


def _rock_hit_ground(o):
    ex1 = o.x + random(o, 10)
    ey1 = random(o, 5) + o.y - 10
    o.world.spawn("EXPLODE1", ex1, ey1, 0)
    ex2 = o.x - random(o, 10)
    ey2 = o.y - random(o, 5) - 10
    o.world.spawn("EXPLODE1", ex2, ey2, 2)
    play_sound(o, "P_EXPLODE_SND")
    hurt_radius(o, o.x, o.y, 40, 15, o.objs[0] if o.objs else None, 20)
    return False  # the stub's progn ends in nil


@lisp("small_rock_ai")
def small_rock_ai(o) -> bool:
    """duong.lsp:392-404: returns bounce_move's value, so the rock goes when it lands."""
    o.next_picture()
    o.yvel += 1
    return bool(bounce_move(o, on_down=_rock_hit_ground))


# --- teleport.lsp: TP_DOOR ---------------------------------------------------------------------

def _other_door_opening(o) -> bool:
    if not o.objs:
        return False
    other = o.objs[0]
    if other.ctype.name != "TP_DOOR":
        return False
    if other.lvars["is_opening"] == 0:
        return distx(other) < 100 and disty(other) < 80
    return True


@lisp("tpd_ai")
def tpd_ai(o) -> bool:
    if (distx(o) < 100 and disty(o) < 80) or _other_door_opening(o):
        o.lvars["is_opening"] = 1
        if o.current_frame == 4:
            o.lvars["is_opening"] = 0
        else:
            if o.current_frame == 0:
                play_sound(o, "DOOR_UP")
            o.next_picture()
    else:
        o.lvars["is_opening"] = 0
        if o.current_frame != 0:
            if o.current_frame == 4:
                play_sound(o, "DOOR_DOWN")
            o.current_frame -= 1
    player = o.world.bg(o)
    if player in o.objs:
        if not pressing_action_key(player):
            o.remove_object(player)
    elif distx(o) < 20 and disty(o) < 30 and pressing_action_key(player) and o.objs:
        other = o.objs[0]
        other.add_object(player)
        player.x, player.y = other.x, other.y
        o.world.emit("teleported", uid=o.uid, x=player.x, y=player.y)
    return True


@lisp("tp_door_cons")
def tp_door_cons(o) -> None:
    o.xvel = -1


# --- platform.lsp ------------------------------------------------------------------------------

def _plat_speed(o) -> int:
    if o.aistate == 0:
        return o.xacel
    return o.xacel if o.yacel == 0 else o.yacel


def _platform_move(o, source, dest) -> None:
    destx, desty = dest.x, dest.y
    sourcex, sourcey = source.x, source.y
    if o.xvel == 0:
        o.world.platform_push(o, destx - o.x, desty - o.y)
        o.x, o.y = destx, desty
        set_aistate(o, 0)
    else:
        speed = _plat_speed(o)
        newx = destx - cdiv((destx - sourcex) * o.xvel, speed)
        newy = desty - cdiv((desty - sourcey) * o.xvel, speed)
        o.world.platform_push(o, newx - o.x, newy - o.y)
        o.xvel -= 1
        o.x, o.y = newx, newy


@lisp("platform_ai")
def platform_ai(o) -> bool:
    """platform.lsp:57-89: rides between its two linked markers when called or signalled."""
    n = len(o.objs)
    if n == 2 or (n == 3 and o.objs[2].aistate != 0):
        if o.state == "stopped":
            o.set_state("running")
        else:
            o.next_picture()
        s = o.aistate
        if s == 0:
            bg = o.world.bg(o)
            called = touching_bg(o) and pressing_action_key(bg)
            if o.objs[o.aitype].aistate != 0 or called:
                if touching_bg(o) and pressing_action_key(bg):
                    bg.y = o.y - o.ability("start_accel")
                go_state(o, 2)
        elif s == 2:
            play_sound(o, "PLAT_A_SND")
            o.set_aitype(1 - o.aitype)
            o.xvel = _plat_speed(o)
            go_state(o, 3)
        elif s == 3:
            if o.xvel == 6:
                play_sound(o, "PLAT_D_SND")
            _platform_move(o, o.objs[o.aitype], o.objs[1 - o.aitype])
    else:
        o.set_state("stopped")
    return True


@lisp("platform_cons")
def platform_cons(o) -> None:
    o.xacel, o.yvel = 20, 50
