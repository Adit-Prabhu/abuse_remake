"""Alien ants, the ant crack, the spray-gun turret, and the pickups.

- ant_ai: compiled C, historicalsource/abuse@01cce80 abuse/src/ant.c:115-423, with its states
  from abuse/inc/ant.hpp. C's ``&&`` short-circuits, so ``jrand()`` is only drawn when the
  conditions before it hold; the port keeps every such order.
- ant_damage, ant_cons, ant_ct, crack_ai, crack_cons: data/original/lisp/ant.lsp:398-570
- spray_gun_ai, spray_gun_cons, guner_damage: data/original/lisp/guns.lsp, weapons.lsp
- hp_up: powerup.lsp; weapon_icon_ai and giver: weapons.lsp:161-237
"""

from __future__ import annotations

from ..cmath import lisp_atan2
from . import lisp
from .lispfns import (
    activated,
    can_see,
    distx,
    disty,
    go_state,
    lcos,
    lisp_try_move,
    lmul,
    lnum,
    lsin,
    play_sound,
    random,
    set_aistate,
    set_frame_angle,
    state_time,
    touching_bg,
)
from .player import give_player_health
from .weapons import create_dead_parts, fire_object, get_dead_part

ANT_START, ANT_FALL_DOWN, ANT_RUNNING, ANT_POUNCE_WAIT, ANT_JUMP = 0, 1, 2, 4, 6
ANT_FIRE, ANT_LANDING, ANT_JUMP_ROOF, ANT_ROOF_WALK, ANT_CEIL_SHOOT = 8, 9, 12, 13, 14
ANT_HANGING, ANT_HIDING = 15, 16

# guns.lsp:19-27 ai_ammo: what an enemy of each aitype drops
AI_AMMO = ("MBULLET_ICON5", "MBULLET_ICON5", "GRENADE_ICON2", "ROCKET_ICON2", "PLASMA_ICON20",
           "MBULLET_ICON5", "MBULLET_ICON5", "MBULLET_ICON5", "MBULLET_ICON5")


def _jrand(o) -> int:
    return o.world.rng.jrand()


def _player(o):
    return o.world.bg(o)


def _ant_can_see(o, x1, y1, x2, y2) -> bool:
    return can_see(o, x1, y1, x2, y2, False)  # ant.c:19-27 uses boundary_setback


def _scream_check(o, b) -> None:
    if _ant_can_see(o, o.x, o.y, b.x, b.y):
        if o.lvars["no_see_time"] == 0 or o.lvars["no_see_time"] > 20:
            play_sound(o, "ASCREAM_SND")
            o.world.emit("enemy_alert", uid=o.uid)
        o.lvars["no_see_time"] = 1
    else:
        o.lvars["no_see_time"] += 1


def _ant_congestion(o) -> bool:
    for d in o.world.active:
        # ant.c:45 compares o->x with d->y (a typo in the original), kept as written
        if d.ctype is o.ctype and abs(o.x - d.x) < 30 and abs(o.x - d.y) < 20:
            return True
    return False


def _ant_dodge(o) -> bool:
    if o.lvars["need_to_dodge"] == 1:
        o.lvars["need_to_dodge"] = 0
        if _jrand(o) % 2 == 0:
            o.set_state("stopped")
            o.set_aistate(ANT_JUMP)
            if not _ant_can_see(o, o.x, o.y, o.x, o.y - 120):  # a roof above?
                o.yvel = -17
                o.xvel = 0
                o.set_aistate(ANT_JUMP_ROOF)
                ant_ai(o)
            else:
                o.yvel = -12
                o.xvel = 22 if o.direction > 0 else -22
                o.set_aistate(ANT_JUMP)
        return True
    return False


def _alien_wait_time(o) -> int:
    return {"easy": 6, "medium": 4, "hard": 2}.get(o.world.difficulty, 1)


def _can_hit_player(o, b) -> bool:
    return _ant_can_see(o, o.x + (15 if o.direction > 0 else -15), o.y - 15, b.x, b.y - 15)


def _fire_at_player(o, b) -> None:
    firex = o.x + (15 if o.direction > 0 else -15)
    firey = o.y - 15
    playerx = b.x + b.xvel * 8
    playery = b.y - 15 + b.yvel * 2
    if _ant_can_see(o, o.x, o.y, firex, firey) and _ant_can_see(o, firex, firey, playerx, playery):
        angle = lisp_atan2(firey - playery, playerx - firex)
        fire_object(o, o.aitype, firex, firey, angle, b)
        o.set_state("weapon_fire")
        o.world.emit("enemy_fired", uid=o.uid)


def _fall_trigger(o) -> bool:
    if not o.objs:
        b = _player(o)
        return abs(b.x - o.x) < 130 and o.y < b.y
    return o.objs[0].aistate != 0


@lisp("ant_ai")
def ant_ai(o) -> bool:
    if o.hp == 0:  # dead: delete next time round
        if o.state == "dead":
            return False
        o.set_state("dead")
        return True
    if o.state in ("flinch_up", "flinch_down"):
        o.next_picture()
        return True
    s = o.aistate
    if s == ANT_START:
        o.set_state("hanging")
        o.set_aistate(ANT_HIDING if o.lvars["hide_flag"] else ANT_HANGING)
    elif s == ANT_HIDING:
        if _jrand(o) % 128 == 0:
            play_sound(o, "SCARE_SND")
        if o.ctype.name != "HIDDEN_ANT":
            o.change_type("HIDDEN_ANT")  # switch types so no one hurts us
            o.set_state("stopped")
            o.set_aistate(ANT_HIDING)
        if _fall_trigger(o):
            o.change_type("ANT_ROOF")
            o.set_state("falling")
            o.set_aistate(ANT_FALL_DOWN)
            o.targetable_on = 1
            o.world.emit("enemy_revealed", uid=o.uid)
        else:
            o.targetable_on = 0
    elif s == ANT_HANGING:
        if _jrand(o) % 128 == 0:
            play_sound(o, "SCARE_SND")
        if o.lvars["hide_flag"]:
            o.set_aistate(ANT_HIDING)
        else:
            o.set_state("hanging")
            if _fall_trigger(o):
                o.set_state("fall_start")
                o.set_aistate(ANT_FALL_DOWN)
                o.targetable_on = 1
            else:
                o.targetable_on = 0
    elif s == ANT_FALL_DOWN:
        o.set_state("falling")
        _scream_check(o, _player(o))
        ret = o.mover(0, 0, 0)
        if (ret & 8) or not _ant_can_see(o, o.x, o.y, o.x, o.y + 1):
            o.set_state("landing")
            play_sound(o, "ALAND_SND")
            o.set_aistate(ANT_LANDING)
    elif s == ANT_LANDING:
        if not o.next_picture():
            _, _, yv = o.try_move(o.x, o.y, 0, 2, 1)
            if yv != 0:
                o.set_gravity(1)
                o.set_aistate(ANT_FALL_DOWN)
            else:
                o.set_state("stopped")
                o.set_aistate(ANT_RUNNING)
                return True
    elif s == ANT_RUNNING:
        b = _player(o)
        _scream_check(o, b)
        if _jrand(o) % 16 == 0:
            o.lvars["need_to_dodge"] = 1
        if not _ant_dodge(o):
            if (o.x > b.x and o.direction == -1) or (o.x < b.x and o.direction == 1):
                o.next_picture()
                if (_jrand(o) % 4 == 0 and abs(o.x - b.x) < 180 and abs(o.y - b.y) < 100
                        and _can_hit_player(o, b)):
                    o.set_state("weapon_fire")
                    o.set_aistate(ANT_FIRE)
                elif abs(o.x - b.x) < 100 and abs(o.y - b.y) < 10 and _jrand(o) % 4 == 0:
                    o.set_aistate(ANT_POUNCE_WAIT)
                elif abs(o.x - b.x) > 140 and not _ant_congestion(o):
                    o.set_aistate(ANT_JUMP)
                else:
                    _ant_run(o)
            else:
                o.direction = -1 if o.x > b.x else 1
                o.set_aistate(ANT_LANDING)
    elif s == ANT_POUNCE_WAIT:
        if not _ant_dodge(o):
            o.set_state("pounce_wait")
            if o.aistate_time > _alien_wait_time(o):
                play_sound(o, "ASLASH_SND")
                o.set_state("stopped")
                o.set_aistate(ANT_JUMP)
    elif s == ANT_JUMP:
        o.lvars["need_to_dodge"] = 0
        if o.move(o.direction, -1, 0) & 8:
            o.set_aistate(ANT_RUNNING)
    elif s == ANT_FIRE:
        if not _ant_dodge(o):
            if o.state == "fire_wait":
                if not o.next_picture() or o.world.difficulty == "extreme":
                    _fire_at_player(o, _player(o))
                    o.set_state("stopped")
                    o.set_aistate(ANT_RUNNING)
            else:
                o.set_state("fire_wait")
    elif s == ANT_JUMP_ROOF:
        o.lvars["need_to_dodge"] = 0
        o.set_state("jump_up")
        o.xacel = 0
        yvel = o.yvel
        o.y -= 31
        _, _, yv = o.try_move(o.x, o.y, 0, yvel, 1)
        o.y += 31 + yv
        if yv != o.yvel:
            if o.yvel > 0:
                o.set_state("stopped")
                o.set_aistate(ANT_RUNNING)
            else:
                o.set_state("top_walk")
                o.set_aistate(ANT_ROOF_WALK)
            o.yvel = 0
    elif s == ANT_ROOF_WALK:
        b = _player(o)
        _scream_check(o, b)
        drop = _jrand(o) % 8 == 0 and abs(o.x - b.x) < 10 and o.y < b.y
        if drop or o.lvars["need_to_dodge"] == 1:
            o.set_gravity(1)
            o.set_state("run_jump")
            o.set_aistate(ANT_JUMP)
            ant_ai(o)
        elif (o.x > b.x and o.direction > 0) or (o.x < b.x and o.direction < 0):
            o.direction = -o.direction
        elif abs(o.x - b.x) < 120 and _jrand(o) % 4 == 0:
            o.set_state("ceil_fire")
            o.set_aistate(ANT_CEIL_SHOOT)
            ant_ai(o)
        else:
            speed = o.ability("run_top_speed") if o.direction > 0 else -o.ability("run_top_speed")
            if (_ant_can_see(o, o.x, o.y - 31, o.x + speed, o.y - 31)
                    and not _ant_can_see(o, o.x + speed, o.y - 31, o.x + speed, o.y - 32)):
                o.x += speed
                if not o.next_picture():
                    o.set_state("top_walk")
            else:
                o.set_aistate(ANT_FALL_DOWN)
    elif s == ANT_CEIL_SHOOT:
        if not o.next_picture():
            _fire_at_player(o, _player(o))
            o.set_state("top_walk")
            o.set_aistate(ANT_ROOF_WALK)
    return True


def _ant_run(o) -> None:
    """ant.c:266-297: run, climb small ramps, turn at walls, fall off edges."""
    rts = o.ability("run_top_speed")
    xm = rts if o.direction > 0 else -rts
    if o.state != "running":
        o.set_state("running")
    _, new_xm, ym = o.try_move(o.x, o.y, xm, 0, 3)
    if new_xm != xm:  # blocked: try to climb a ramp
        _, new_xm, ym = o.try_move(o.x, o.y, xm, -abs(xm), 3)
        if new_xm == xm:
            o.x += new_xm
            o.y += ym
            _, new_xm, ym = o.try_move(o.x, o.y, 0, abs(xm), 3)
            o.x += new_xm
            o.y += ym
        else:
            o.direction = -o.direction
            o.set_aistate(ANT_JUMP)
    else:
        o.x += new_xm
    _, _, ym = o.try_move(o.x, o.y, 0, 10, 3)  # see if we should fall
    if ym == 10:
        o.set_aistate(ANT_FALL_DOWN)
    else:
        o.y += ym


def _hurt_by_ant(from_obj) -> bool:
    """ant_damage's guard: ants (and their bullets) do not hurt each other."""
    if from_obj is None:
        return False
    if not from_obj.objs:
        return from_obj.ctype.name == "ANT_ROOF"
    return from_obj.objs[0].ctype.name == "ANT_ROOF"


@lisp("ant_damage")
def ant_damage(o, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
    if o.state == "dead" or _hurt_by_ant(from_obj):
        return
    if o.aistate == ANT_HANGING:
        return
    o.set_state("flinch_up" if random(o, 2) == 0 else "flinch_down")
    o.damage_fun(amount, from_obj, hitx, hity, push_xvel, push_yvel)
    play_sound(o, "APAIN_SND")
    o.lvars["need_to_dodge"] = 1
    if o.hp <= 0:
        if o.aitype == 0:
            play_sound(o, f"ASML_DEATH{random(o, 2)}")
        else:
            play_sound(o, f"ALRG_DEATH{random(o, 3)}")
        o.set_state("dead")
        chance = {"easy": 2, "medium": 5, "hard": 8, "extreme": 20}[o.world.difficulty]
        if random(o, chance) == 0:
            if random(o, 4) == 0:
                o.world.spawn(AI_AMMO[o.aitype + 1], o.x, o.y)
        else:
            o.world.spawn(AI_AMMO[o.aitype], o.x, o.y)
        create_dead_parts(o, "ant_dead_parts", get_dead_part(o, from_obj) * 3, o.aitype)
        o.world.emit("enemy_killed", uid=o.uid, type=o.ctype.name, x=o.x, y=o.y)


@lisp("ant_cons")
def ant_cons(o) -> None:
    o.set_state("hanging")
    o.lvars["no_see_time"] = 300


@lisp("ant_ct")
def ant_ct(o) -> None:
    hp = {0: 15, 1: 50, 2: 25, 3: 35, 4: 35, 5: 20}.get(o.aitype)
    if hp is not None:
        o.set_hp(hp)


@lisp("crack_ai")
def crack_ai(o) -> bool:
    """ant.lsp:526-557: a wall crack that releases ants when triggered."""
    if o.aistate == 0:
        if not o.objs:
            trig = distx(o) < 50 and disty(o) < 70
        else:
            trig = o.objs[0].aistate != 0
        if trig:
            set_aistate(o, 1)
    else:
        f = o.current_frame
        if f == 3:
            d, atype = o.direction, o.aitype
            if o.lvars["create_total"] in (0, 1):
                o.current_frame = 4
            else:
                o.lvars["create_total"] -= 1
                o.current_frame = 0
            ant = o.world.spawn_after("ANT_ROOF", o.x + o.direction * 20, o.y, o)
            ant.change_aitype(atype)
            ant.direction = d
            ant.xvel = d * 20
            ant.set_state("run_jump")
            set_aistate(ant, 6)
            o.world.emit("enemy_spawned", uid=ant.uid)
        elif f in (0, 1, 2):
            o.next_picture()
    return True


@lisp("crack_cons")
def crack_cons(o) -> None:
    o.lvars["create_total"] = 1
    o.change_aitype(1)


# --- guns.lsp: SPRAY_GUN --------------------------------------------------------------------

def _spray_fire(o) -> None:
    a = o.lvars["spray.angle"]
    x = o.x + lnum(lmul(lcos(a), 20))
    y = o.y - 21 - lnum(lmul(lsin(a), 22))
    fire_object(o, o.aitype, x, y, a, o.world.bg(o))


@lisp("spray_gun_ai")
def spray_gun_ai(o) -> bool:
    if o.hp <= 0:
        return False
    if distx(o) < 450 and disty(o) < 400:
        s = o.aistate
        if s == 0:  # look at the sensor
            if activated(o):
                if o.state == "stopped":
                    o.targetable_on = 1
                    o.set_state("spray.appear")
                    go_state(o, 1)
                else:
                    go_state(o, 3)
            else:
                o.targetable_on = 0
                o.set_state("stopped")
        elif s == 1:  # unfold
            if not o.next_picture():
                set_aistate(o, 3)
                o.set_state("spray.aim")
                o.lvars["spray.angle"] = o.lvars["spray.start_angle"]
                set_frame_angle(o, 0, 359, o.lvars["spray.angle"])
        elif s == 2:  # fold up
            if not o.next_picture():
                o.set_state("stopped")
                set_aistate(o, 0)
        elif s == 3:  # swivel down
            if state_time(o) > o.lvars["spray.fire_delay"]:
                set_aistate(o, 3)
                o.lvars["spray.angle"] -= o.lvars["spray.angle_speed"]
                if o.lvars["spray.angle"] <= o.lvars["spray.start_angle"]:
                    o.lvars["spray.angle"] = o.lvars["spray.start_angle"]
                    set_aistate(o, 4)
                set_frame_angle(o, 0, 359, o.lvars["spray.angle"])
                _spray_fire(o)
        elif s == 4:  # swivel up
            if state_time(o) > o.lvars["spray.fire_delay"]:
                set_aistate(o, 4)
                o.lvars["spray.angle"] += o.lvars["spray.angle_speed"]
                if o.lvars["spray.angle"] >= o.lvars["spray.end_angle"]:
                    o.lvars["spray.angle"] = o.lvars["spray.end_angle"]
                    set_aistate(o, 0)
                set_frame_angle(o, 0, 359, o.lvars["spray.angle"])
                _spray_fire(o)
        return True
    o.set_state("stopped")
    return True


@lisp("spray_gun_cons")
def spray_gun_cons(o) -> None:
    o.lvars["spray.bullet_speed"] = 20
    o.lvars["spray.angle_speed"] = 10
    o.lvars["spray.start_angle"] = 270
    o.lvars["spray.end_angle"] = 350
    o.lvars["spray.fire_delay"] = 4


@lisp("guner_damage")
def guner_damage(o, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
    """weapons.lsp:300-317: turrets only take damage while unfolded, and are never pushed."""
    if o.state == "stopped":
        return
    parts = (("EXPLODE3", 1, 0), ("EXPLODE2", 1, 2), ("EXPLODE3", -1, 1), ("EXPLODE3", -1, 2))
    for name, sign, aitype in parts:
        ex = hitx + sign * random(o, 5)
        ey = hity + sign * random(o, 5)
        o.world.spawn(name, ex, ey, aitype)
    o.damage_fun(amount, from_obj, hitx, hity, 0, 0)
    if o.hp <= 0:
        play_sound(o, "BLOWN_UP")
        for sx, rx, sy, ry, aitype in ((-1, 10, -1, 25, 0), (1, 10, 1, 25, 1), (-1, 10, -1, 10, 2),
                                       (1, 10, 1, 10, 3)):
            ex = hitx + sx * random(o, rx)
            ey = hity + sy * random(o, ry)
            o.world.spawn("EXPLODE1", ex, ey, aitype)
        o.world.emit("enemy_killed", uid=o.uid, type=o.ctype.name, x=o.x, y=o.y)


# --- pickups --------------------------------------------------------------------------------

@lisp("hp_up")
def hp_up(o) -> bool:
    """powerup.lsp:9-15: +20 health (scaled by difficulty) when touched, if not full."""
    o.next_picture()
    if touching_bg(o) and give_player_health(o.world.bg(o), 20):
        play_sound(o, "HEALTH_UP_SND")
        o.world.emit("pickup", item="health", uid=o.uid, x=o.x, y=o.y)
        return False
    return True


WEAPON_SLOT = {"MBULLET_ICON5": 0, "MBULLET_ICON20": 0, "GRENADE_ICON2": 1, "GRENADE_ICON10": 1,
               "ROCKET_ICON2": 2, "ROCKET_ICON5": 2, "FBOMB_ICON1": 3, "FBOMB_ICON5": 3,
               "PLASMA_ICON20": 4, "PLASMA_ICON50": 4, "LSABER_ICON50": 5, "LSABER_ICON100": 5,
               "DFRIS_ICON4": 6, "DFRIS_ICON10": 6}


def giver(o, wtype: int) -> None:
    """weapons.lsp:161-170: add the icon's start_hp as ammo; a new weapon is selected."""
    amount = o.ability("start_hp")
    v = o.world.bg(o).controller
    if v is None:
        return
    if not v.has_weapon(wtype) and o.world.globals.get("change_on_pickup", True):
        v.give_weapon(wtype)
        v.current_weapon = wtype  # set_current_weapon (clisp.c case 230) applies at once
    else:
        v.give_weapon(wtype)
    v.add_ammo(wtype, amount)


def _take(o) -> bool:
    play_sound(o, "AMMO_SND")
    slot = WEAPON_SLOT.get(o.ctype.name)
    if slot is not None:
        giver(o, slot)
    o.world.emit("pickup", item="ammo", type=o.ctype.name, uid=o.uid, x=o.x, y=o.y)
    return False


@lisp("weapon_icon_ai")
def weapon_icon_ai(o) -> bool:
    if o.aistate == 0:
        if activated(o):
            lisp_try_move(o, 0, 10)
            fx, fy = o.world.tiles.foreground_intersect(o.x, o.y, o.x, o.y + 1)  # see_dist
            if fy == o.y:  # on the floor: stop checking for falls
                set_aistate(o, 1)
            if touching_bg(o):
                return _take(o)
            return True
        return True
    if touching_bg(o):
        return _take(o)
    return True


