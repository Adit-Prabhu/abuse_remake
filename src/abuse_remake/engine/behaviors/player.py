"""The player (DARNEL) and the weapon-holding top half.

Ported from historicalsource/abuse@01cce80 abuse/src/cop.c, which is compiled C that the Lisp
calls (clisp.c registers ``cop_mover``, ``top_ai``, ``laser_ufun``, ``top_ufun`` and
``player_rocket_ufun``), and from data/original/lisp/people.lsp (``bottom_damage``,
``give_player_health``, ``set_player_defaults``, ``cop_ufun``).
"""

from __future__ import annotations

from ..cmath import cdiv, lisp_atan2
from . import lisp
from .lispfns import bad_guy_types, play_sound, random
from .weapons import create_dead_parts, fire_object, get_dead_part

# cop.c:23-73: x,y offsets from the player to the end of the gun, for each of the 24 frames.
SMALL_FIRE_OFF = ((17, 20), (17, 23), (17, 28), (15, 33), (11, 39), (7, 43), (-3, 44), (-10, 42),
                  (-16, 39), (-20, 34), (-20, 28), (-20, 25), (-19, 20), (-19, 16), (-16, 14),
                  (-14, 11), (-11, 9), (-7, 8), (-3, 8), (2, 8), (6, 9), (10, 10), (14, 13), (16, 15))
LARGE_FIRE_OFF = ((18, 25), (17, 30), (15, 34), (14, 36), (10, 39), (7, 41), (4, 42), (-3, 41),
                  (-8, 39), (-11, 37), (-14, 33), (-16, 30), (-18, 25), (-17, 21), (-14, 17),
                  (-11, 15), (-7, 13), (-4, 12), (3, 12), (9, 12), (12, 15), (14, 16), (15, 18), (16, 21))

# cop.c:13-19: weapon ids passed to fire_object
SHOTGUN, GRENADE, ROCKET, PLASMA, FIREBOMB, DFRIS, LSABER = 10, 2, 3, 4, 5, 6, 7
NO_POWER, FAST_POWER, FLY_POWER, SNEAKY_POWER, HEALTH_POWER = 0, 1, 2, 3, 4
JUST_START, NORMAL_PLAY = 0, 1  # people.lsp enum for the cop's aistate


def angle_diff(a1: int, a2: int) -> int:
    """cop.c:108-121."""
    if a1 < a2:
        return a2 - a1 if (a2 - a1) < 180 else 360 - a2 + a1
    return a1 - a2 if (a1 - a2) < 180 else 360 - a1 + a2


def _fire_off(top) -> tuple:
    return LARGE_FIRE_OFF if top.ctype.name in ("DFRIS_TOP", "ROCKET_TOP", "BFG_TOP") else SMALL_FIRE_OFF


@lisp("top_ai")
def top_ai(o) -> bool:
    """cop.c:125-188: aim the top half at the pointer, pick the frame, switch weapon type."""
    if not o.objs:
        return True
    q = o.objs[0]
    v = q.controller
    if v is None or v.freeze_time:
        return True
    o.direction = 1  # always face right; the frame does the aiming
    if q.direction < 0:
        q.x += 4
    f = _fire_off(o)
    iy, ix = f[0][1], f[6][0]
    best_angle = lisp_atan2(q.y - iy - v.pointer_y, v.pointer_x - q.x - ix)
    best_diff, best_num, fb = 200, 0, f[0]
    for i, off in enumerate(f):
        this_diff = angle_diff(lisp_atan2(off[1] - iy, off[0] - ix), best_angle)
        if this_diff < best_diff:
            best_diff, best_num, fb = this_diff, i, off
    # if the pointer is too close to the player, use the angle the frame shows (cop.c:163-167;
    # the original's second test adds fb[0] where it means to subtract it)
    if abs(q.y - fb[1] - v.pointer_y) < 45 and abs(v.pointer_x - q.x + fb[0]) < 40:
        o.lvars["point_angle"] = lisp_atan2(fb[1] - iy, fb[0] - ix)
    else:
        o.lvars["point_angle"] = lisp_atan2(q.y - fb[1] - v.pointer_y, v.pointer_x - (q.x + fb[0]))
    if q.direction < 0:
        q.x -= 4
    o.x = q.x
    o.y = q.y + 29 - q.picture_height()
    o.world.rng.shift(o.lvars["point_angle"])  # rand_on += point_angle
    o.current_frame = best_num
    if o.lvars["fire_delay1"]:
        o.lvars["fire_delay1"] -= 1
    wt = o.world.weapon_types[v.current_weapon]
    if o.ctype is not wt:  # o->otype=weapon_types[current_weapon] (no constructor, same vars)
        o.ctype = wt
    return True


def player_fire_weapon(o, wtype: int, target, angle: int, fire_off) -> bool:
    """cop.c:191-234: fire from the end of the gun unless a wall is in the way."""
    if not o.objs:
        return False
    other = o.objs[0]
    ox, oy = other.x, other.y
    if other.direction < 0:
        other.x += 4
    firex = other.x + fire_off[o.current_frame][0]
    firey = other.y - fire_off[o.current_frame][1]
    x2, y2 = o.x, firey
    other.y = y2
    if other.y == firey:  # always true: the earlier blocked-above check is commented out
        x2 = firex
        x2, y2 = o.world.tiles.foreground_intersect(other.x, other.y, x2, y2)
        _, x2, y2 = o.world.all_boundary_setback(other, other.x, other.y, x2, y2)
        o.x = x2
    fire_object(o.objs[0], wtype, x2, y2, angle, target)
    o.lvars["just_fired"] = 1
    other.lvars["just_fired"] = 1
    other.x, other.y = ox, oy
    return True


@lisp("laser_ufun")
def laser_ufun(o, signal, value) -> int:
    """cop.c:238-265: 3 ticks between shots with ammo; with none, 5 ticks and no ammo used."""
    if signal != "FIRE":
        return 0
    if o.lvars["fire_delay1"]:
        return 0
    if value:
        o.lvars["fire_delay1"] = 3
        return -1 if player_fire_weapon(o, SHOTGUN, None, o.lvars["point_angle"], SMALL_FIRE_OFF) else 0
    o.lvars["fire_delay1"] = 5
    player_fire_weapon(o, SHOTGUN, None, o.lvars["point_angle"], SMALL_FIRE_OFF)
    return 0


def _ammo_type(o) -> int:
    name = o.ctype.name  # cop.c:268-277
    if name == "GRENADE_TOP":
        return GRENADE
    if name == "FIREBOMB_TOP":
        return FIREBOMB
    if name == "DFRIS_TOP":
        return DFRIS
    return SHOTGUN


@lisp("top_ufun")
def top_ufun(o, signal, value) -> int:
    """cop.c:280-303: grenade and firebomb tops, 6 ticks between shots, need ammo."""
    if signal != "FIRE" or o.lvars["fire_delay1"] or not value:
        return 0
    o.lvars["fire_delay1"] = 6
    # cop.c:296 compares the type index with the weapon id DFRIS (6); kept as written
    fire_off = LARGE_FIRE_OFF if o.ctype.index == DFRIS else SMALL_FIRE_OFF
    return -1 if player_fire_weapon(o, _ammo_type(o), None, o.lvars["point_angle"], fire_off) else 0


@lisp("player_rocket_ufun")
def player_rocket_ufun(o, signal, value) -> int:
    """cop.c:358-404: rockets lock onto the nearest bad guy within 160x130."""
    if signal != "FIRE" or o.lvars["fire_delay1"] or not value:
        return 0
    o.lvars["fire_delay1"] = 6
    target, closest = None, 0xFFFFFFF
    bot = o.objs[0] if o.objs else None
    bad = bad_guy_types(o.world)
    rocket_index = o.world.types["ROCKET"].index
    for p in o.world.active:
        if p.deleted:
            continue
        xd, yd = abs(p.x - o.x), abs(p.y - o.y)
        if xd < 160 and yd < 130 and p.ctype.index in bad and p is not bot:
            if p.targetable_on and not (p.ctype.index == rocket_index and p.objs and p.objs[0] is bot):
                d = xd * xd + yd * yd
                if d < closest:
                    closest, target = d, p
    return -1 if player_fire_weapon(o, ROCKET, target, o.lvars["point_angle"], LARGE_FIRE_OFF) else 0


# --- the bottom half -----------------------------------------------------------------------

def _player_move(o, xm, ym, but) -> int:
    """cop.c:406-419."""
    if not o.lvars["in_climbing_area"]:
        if o.state == "climbing":
            o.set_gravity(1)
            o.set_state("run_jump_fall")
        o.next_picture()
        return o.mover(xm, ym, but)
    return _climb_handler(o, xm, ym, but)


def _climb_handler(o, xm, ym, but) -> int:
    """cop.c:516-597. Level 1 has no ladders, so in_climbing_area stays 0 there."""
    yd = o.lvars["in_climbing_area"]
    o.lvars["in_climbing_area"] = 0
    if o.state == "climb_off":
        if o.next_picture():
            o.controller.pan_y -= 4
        else:
            o.y -= 28
            o.controller.pan_y += 28
            o.controller.last_y -= 28
            o.set_state("stopped")
    elif o.state == "climb_on":
        if o.next_picture():
            o.controller.pan_y += 4
        else:
            o.set_state("climbing")
    elif o.state == "climbing":
        if ym > 0:
            if o.current_frame == 0:
                o.current_frame = 9
            o.current_frame -= 1
            o.y += 3
        elif ym < 0:
            if yd < 32:
                o.set_state("climb_off")
            else:
                if not o.next_picture():
                    o.set_state("climbing")
                o.y -= 3
        if xm:
            _, _, y2 = o.try_move(o.x, o.y, 0, -20, 3)
            if y2 == -20:
                o.set_gravity(1)
                if ym >= 0:
                    o.set_state("run_jump_fall")
                else:
                    o.set_state("run_jump")
                    o.yvel = o.ability("jump_yvel")
    elif ym > 0 and yd < 10:
        o.y += 28
        o.controller.pan_y -= 28
        o.controller.last_y += 28
        o.set_state("climb_on")
    elif o.yvel >= 0 and (ym > 0 or (ym < 0 and yd > 8)):
        o.set_state("climbing")
        o.set_gravity(0)
        o.xvel = o.yvel = o.xacel = o.yacel = 0
        return 0
    else:
        o.next_picture()
        return o.mover(xm, ym, but)
    return 0


def _undo_special_power(o) -> None:
    sp = o.lvars["special_power"]  # cop.c:422-436
    if sp == SNEAKY_POWER:
        if o.lvars["used_special_power"] > 0:
            o.lvars["used_special_power"] -= 1
    elif sp == FAST_POWER:
        o.lvars["used_special_power"] = 0


def _do_special_power(o, xm, ym, but, top) -> None:
    """cop.c:438-490. Level 1 has no power-ups, so special_power stays NO_POWER there."""
    sp = o.lvars["special_power"]
    if sp == FLY_POWER:
        cloud = o.world.create("CLOUD", o.x + o.direction * -10, o.y + o.world.rng.jrand() % 5)
        o.world.add_object(cloud)
        o.set_state("run_jump")
        o.set_gravity(1)
        o.yacel = 0
        if o.yvel > 0:
            o.yvel = cdiv(o.yvel, 2)
        o.yvel -= 3 if ym < 0 else 2
        play_sound(o, "FLY_SND", 32)
    elif sp == FAST_POWER:
        if o.world.tick_counter % 16 == 0:
            play_sound(o, "SPEED_SND", 100)
        o.lvars["used_special_power"] = 1
        o.lvars["last1_x"], o.lvars["last1_y"] = o.x, o.y
        oyvel = o.yvel
        inside = o.lvars["in_climbing_area"]
        _player_move(o, xm, ym, but)
        if ym < 0 and not oyvel and o.yvel < 0:
            o.yvel += cdiv(o.yvel, 3)
        o.lvars["in_climbing_area"] = inside
        o.lvars["last2_x"] = o.x
        o.lvars["last2_x"] = o.y  # sic: cop.c:479 stores y into last2_x
    elif sp == SNEAKY_POWER:
        if o.lvars["used_special_power"] < 15:
            o.lvars["used_special_power"] += 1


@lisp("cop_mover")
def cop_mover(o, xm: int, ym: int, but: int) -> int:
    """cop.c:600-683: the player's per-tick move function."""
    ret = 0
    v = o.controller
    if v is not None and v.freeze_time:
        v.freeze_time -= 1
        if but:
            v.freeze_time = 0
        return 0
    if not o.objs:  # no top half yet: create one (cop.c:613-618)
        top = o.world.create("MGUN_TOP", o.x, o.y)
        o.world.add_object_after(top, o)
        o.add_object(top)
        top.add_object(o)
    else:
        top = o.objs[0]
    if o.yvel > 10:  # terminal velocity
        o.yacel = 0
        o.yvel -= 1
    if o.aistate == 0:  # just started
        o.set_aistate(1)
    elif o.aistate == 1:  # normal play
        if o.hp == 0:
            o.set_aistate(2)
            o.set_state("dead")
            o.world.emit("player_died", x=o.x, y=o.y)
        else:
            tc = o.world.tick_counter
            if (o.hp < 40 and tc % 16 == 0) or (o.hp < 15 and tc % 8 == 0) or (o.hp < 7 and tc % 4 == 0):
                play_sound(o, "LOW_HEALTH_SND")
            if but & 1:
                _do_special_power(o, xm, ym, but, top)
            else:
                _undo_special_power(o)
            ret = _player_move(o, xm, ym, but)
            top.x = o.x
            top.y = o.y + 29 - top.picture_height()
            if (but & 2) and not o.lvars["is_teleporting"] and o.state not in ("climbing", "climb_off"):
                fn = top.ctype.user_fun
                used = fn(top, "FIRE", v.weapon_total(v.current_weapon)) if fn else 0
                v.add_ammo(v.current_weapon, used or 0)
    elif o.aistate == 3:
        pass  # dead: waiting for the restart key, handled by the game layer (cop.c:669-678)
    else:
        o.set_aistate(o.aistate + 1)
    return ret


@lisp("bottom_damage")
def bottom_damage(o, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
    """people.lsp:328-370: difficulty-scaled damage, flinch, screen flash, death debris."""
    if o.lvars["is_teleporting"] == 1:
        return
    if o.world.globals.get("player_iframes"):  # Remastered dash only; never set in Classic mode
        return
    diff = o.world.difficulty
    if diff == "easy":
        amount = cdiv(amount, 2)
    elif diff == "medium":
        amount = cdiv(amount * 3, 4)
    elif diff == "extreme":
        amount = amount * 3
    if o.aistate != NORMAL_PLAY or o.state in ("dieing", "dead"):
        return
    o.set_state("flinch_up" if random(o, 2) == 0 else "flinch_down")
    o.lvars["r_ramp"] = min(120, o.lvars["r_ramp"] + amount * 7)  # the red damage flash
    o.lvars["g_ramp"] = max(0, o.lvars["g_ramp"] - amount * 14)
    o.lvars["b_ramp"] = max(0, o.lvars["b_ramp"] - amount * 14)
    o.damage_fun(amount, from_obj, hitx, hity, cdiv(push_xvel, 2), cdiv(push_yvel, 2))
    if o.hp == 0:
        # (time_for_next_level) is false outside network games, so that branch is skipped
        create_dead_parts(o, "cop_dead_parts", get_dead_part(o, from_obj) * 3,
                          o.controller.player_number if o.controller else 0)
        play_sound(o, f"PLAYER_DEATH{random(o, 4)}")
    elif amount > 8:
        play_sound(o, f"PLAYER_PAIN{random(o, 4)}")


def give_player_health(o, amount: int) -> bool:
    """people.lsp:49-66. Returns True if any health was given."""
    diff = o.world.difficulty
    if diff == "medium":
        amount = cdiv(amount * 3, 4)
    elif diff == "hard":
        amount = cdiv(amount, 2)
    elif diff == "extreme":
        amount = cdiv(amount, 5)
    h_max = 200 if o.lvars["special_power"] == HEALTH_POWER else 100
    if o.hp == h_max:
        return False
    if o.hp + amount <= h_max:
        o.add_hp(amount)
    else:
        o.add_hp(h_max - o.hp)
    o.lvars["b_ramp"] += amount * 2
    return True


@lisp("cop_ufun")
def cop_ufun(o, signal, value=None):
    """people.lsp:112-129: only power-up timers use it; none exist in Level 1."""
    return None


def set_player_defaults(o) -> None:
    """people.lsp:101-115, run for each player when a level loads (level.c:1817-1830)."""
    if o.controller is not None:
        o.controller.ambient = 35
    o.set_aistate(0)
    o.set_fade_count(0)
    for name in ("in_climbing_area", "disable_top_draw", "just_hit", "used_special_power",
                 "has_saved_this_level", "r_ramp", "g_ramp", "b_ramp", "is_teleporting",
                 "just_fired", "has_compass"):
        o.lvars[name] = 0
    o.lvars["special_power"] = NO_POWER
