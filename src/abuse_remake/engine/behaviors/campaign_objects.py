"""Objects of Remastered's campaign levels that Level 1 does not have: the training level's
ladders, lava, springs, switch ball and training messages, the flyers and their straight rockets,
and the four power-ups.

They are ported from the 2.0-era Lisp in data/original/lisp, as Level 1's objects are:
- latter_ai: ladder.lsp:5-29 (the climbing itself is cop.c's climb_handler, in player.py)
- lava_ai: duong.lsp:206-227
- spring_ai, spring_cons, train_ai, sball_damage: general.lsp:26-109; the training messages are
  english.lsp:226-243
- flyer_ai, flyer_cons, flyer_damage: flyer.lsp:5-122 (FLYER and GREEN_FLYER); WHO, the
  training level's flyer, uses the same functions (jugger.lsp:200-222)
- strait_rocket_ai, animate_ai, eg_explo_ufun: ant.lsp:63-104
- fast_ai, sneaky_power_ai, fly_power_ai, health_power_ai: powerup.lsp:39-108. Using a power is
  cop.c (do_special_power and undo_special_power, in player.py), already ported for Level 1.
- Level 2: block_ai (duong.lsp:117-135), step_ai (ladder.lsp:31-43), pusher_ai and pusher_cons
  (general.lsp:4-24), track_ai, track_cons, track_fire and track_set_angle (guns.lsp:313-430),
  rob1_ai, rob_cons, jug_ai, jug_cons and explo_damage (jugger.lsp:4-190), grenade_ufun
  (weapons.lsp:120-132).

The shareware levels were built for the 1995 shareware Lisp. Where it differs from the 2.0 rules
used here, docs/remastered.md lists it (for example, the 1995 train_ai also froze the player).
"""

from __future__ import annotations

from ..cmath import cdiv, cmod
from . import lisp
from .lispfns import (
    activated,
    atan2,
    blocked_left,
    blocked_right,
    bmove,
    can_see,
    distx,
    do_damage,
    facing,
    find_rgb,
    go_state,
    hurt_radius,
    lcos,
    lisp_try_move,
    lmod,
    lmul,
    lnum,
    lsin,
    play_sound,
    random,
    set_aistate,
    set_course,
    set_frame_angle,
    state_time,
    touching_bg,
    toward,
)
from .player import FAST_POWER, FLY_POWER, HEALTH_POWER, SNEAKY_POWER, give_player_health
from .weapons import bounce_move, fire_object
from .world_objects import push_char

# --- ladders -------------------------------------------------------------------------------------

@lisp("latter_ai")
def latter_ai(o) -> bool:
    """ladder.lsp:5-23: a player inside the box from the ladder to its link is told how far
    below the top it is (``in_climbing_area``); a climbing player is moved to the middle."""
    if o.objs:
        corner = o.objs[0]
        for v in o.world.views:  # (first_focus) ... (next_focus first)
            first = v.focus
            if first is None:
                continue
            if o.x <= first.x and o.y <= first.y and corner.x >= first.x and corner.y >= first.y:
                yd = first.y - o.y
                if first.state == "climbing":
                    first.x = cdiv(o.x + corner.x, 2)
                first.lvars["in_climbing_area"] = yd
    return True


# --- lava ----------------------------------------------------------------------------------------

@lisp("lava_ai")
def lava_ai(o) -> bool:
    """duong.lsp:206-221: 6 damage every 20 ticks while touched; a random bubble (1 in 100 each
    tick) bursts 5 ticks later and hurts everything within 20 pixels."""
    if touching_bg(o) and cmod(state_time(o), 20) == 0:
        do_damage(o, 6, o.world.bg(o))
    if o.aistate == 0:
        if random(o, 100) == 0:
            play_sound(o, "LAVA_SND", 64)
            set_aistate(o, 1)
        o.next_picture()
    elif o.aistate == 1:
        o.next_picture()
        if state_time(o) == 5:
            hurt_radius(o, o.x, o.y, 20, 20, None, 10)
            set_aistate(o, 0)
    return True


# --- springs -------------------------------------------------------------------------------------

@lisp("spring_cons")
def spring_cons(o) -> None:
    o.yvel = -15  # general.lsp:26; a saved spring keeps its own "yvel" field


@lisp("spring_ai")
def spring_ai(o) -> bool:
    """general.lsp:27-47: while on (unlinked, or its first link on), a touch adds the spring's
    yvel to the player's and throws a standing player into a jump; then it plays its bounce."""
    if not o.objs or o.objs[0].aistate != 0:
        if o.aistate == 0:
            if touching_bg(o):
                add_yvel = o.yvel
                play_sound(o, "SPRING_SOUND")
                bg = o.world.bg(o)
                bg.yvel += add_yvel
                if bg.gravity() == 0:
                    bg.set_state("run_jump")
                    bg.set_gravity(1)
                o.set_state("running")
                set_aistate(o, 1)
        elif o.aistate == 1:
            if not o.next_picture():
                set_aistate(o, 0)
                o.set_state("stopped")
    return True


# --- the switch ball and training messages --------------------------------------------------------

@lisp("sball_damage")
def sball_damage(o, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
    """general.lsp:96-100: a shot turns a stopped switch ball on. It takes no damage."""
    if o.state == "stopped":
        set_aistate(o, 1)
        o.set_state("running")


# english.lsp:226-246 (get_train_msg). Checked against the file by tests/test_training_level.py.
TRAIN_MSGS = {
    0: "Aim gun with mouse, fire with left mouse button",
    1: "Collect ammo to increase firing speed",
    2: "Press the down key to activate objects. This is a switch.",
    3: "This console saves the state of the game, press down",
    4: "Press down to activate platform",
    5: "Hold down the right mouse button to use special powers",
    6: "Use the CTRL & INS keys to select weapons",
    7: "Press the up key to climb ladders",
    8: "Press the down key to start!",
    9: "Shoot hidden walls to destroy them",
    10: "Shoot switch ball to activate",
    11: "Press down to teleport",
}


def _show_help(o, number: int) -> None:
    """``show_help`` (game.c:482-487) puts a line of help text on screen; output only."""
    o.world.emit("help", number=number, text=TRAIN_MSGS.get(number, ""))


@lisp("train_ai")
def train_ai(o) -> bool:
    """general.lsp:66-86: when activated, show message number ``aitype``; keep showing it for 99
    more ticks, then delete the object."""
    if o.aistate == 0:
        if activated(o):
            _show_help(o, o.aitype)
            set_aistate(o, 1)
        return True
    if o.aistate == 100:
        return False
    _show_help(o, o.aitype)
    set_aistate(o, o.aistate + 1)
    return True


# --- flyers --------------------------------------------------------------------------------------

def _halve_xvel(o) -> bool:
    o.xvel = cdiv(o.xvel, 2)
    return True


def _halve_yvel(o) -> bool:
    o.yvel = cdiv(o.yvel, 2)
    return True


@lisp("flyer_cons")
def flyer_cons(o) -> None:
    """flyer.lsp:101-107."""
    lv = o.lvars
    lv["fire_delay"] = 20
    lv["burst_delay"] = 3
    lv["max_xvel"] = 10
    lv["max_yvel"] = 5
    o.change_aitype(9)  # fire_object type 9: the straight rocket
    lv["burst_total"] = 2


@lisp("flyer_ai")
def flyer_ai(o) -> bool:
    """flyer.lsp:5-97. Off until its first link is on (stopped and untargetable); then it flies
    toward a point 50 to 70 pixels above the player, jitters at random, and fires bursts of
    straight rockets when within 150 pixels and the line of fire is clear. At 0 health it
    explodes and counts as a kill."""
    lv = o.lvars
    if lv["smoke_time"] != 0:  # just hit: trail smoke
        lv["smoke_time"] -= 1
        if cmod(lv["smoke_time"], 2) == 0:
            o.world.spawn("SMALL_DARK_CLOUD", o.x, o.y)
    if o.aistate == 0:  # wait for something to turn us on
        if not o.objs or o.objs[0].aistate != 0:
            if o.next_picture():
                return True
            o.targetable_on = 1
            o.set_state("running")
            set_aistate(o, 1)
            return True
        o.targetable_on = 0
        o.set_state("stopped")
        return True
    if o.hp == 0:  # dead: an explosion
        o.world.spawn("EXPLODE1", o.x + random(o, 10), random(o, 10) + o.y - 20, 0)
        o.world.spawn("EXPLODE1", o.x - random(o, 10), o.y - random(o, 10) - 20, 2)
        o.world.spawn("EXPLODE1", o.x, o.y - random(o, 20) - 20, 4)
        v = o.world.bg(o).controller
        if v is not None:
            v.kills += 1
        o.world.emit("enemy_killed", uid=o.uid, type=o.ctype.name, x=o.x, y=o.y)
        return False
    bg = o.world.bg(o)
    if cmod(state_time(o), 5) == 0:
        play_sound(o, "FLYER_SND")
    mx, my = lv["max_xvel"], lv["max_yvel"]
    if bg.x > o.x:  # head right if the player is to the right
        o.xvel += 1
        if o.xvel > mx:
            o.xvel = mx
        if o.direction == -1:
            o.direction = 1
            o.set_state("turn_around")
    elif bg.x < o.x:
        o.xvel -= 1
        if o.xvel < -mx:
            o.xvel = -mx
        if o.direction == 1:
            o.direction = -1
            o.set_state("turn_around")
    if bg.y - 70 > o.y:
        if o.yvel > my:
            o.yvel -= 1
        else:
            o.yvel += 1
    elif bg.y - 50 < o.y:
        if o.yvel < -my:
            o.yvel += 1
        else:
            o.yvel -= 1
    if random(o, 5) == 0:  # some randomness in the movement
        o.xvel += 1
    elif random(o, 5) == 0:
        o.xvel -= 1
    if random(o, 5) == 0:
        o.yvel += 1
    elif random(o, 5) == 0:
        o.yvel -= 1
    if not o.next_picture():
        o.set_state("running")
    bounce_move(o, _halve_xvel, _halve_xvel, _halve_yvel, _halve_yvel, None)
    if lv["fire_time"] > 0:  # waiting for the next burst
        lv["fire_time"] -= 1
        if lv["fire_time"] == 0:
            lv["burst_left"] = lv["burst_total"]
            lv["burst_wait"] = 0
    elif lv["burst_wait"] == 0:
        if distx(o) < 150 and o.direction == facing(o):
            firex = o.x + o.direction * 10
            firey = o.y
            playerx = bg.x + bg.xvel * 4
            playery = bg.y - 15 + bg.yvel * 2
            if can_see(o, o.x, o.y, firex, firey, False) and can_see(o, firex, firey, playerx, playery, False):
                angle = atan2(firey - playery, playerx - firex)
                if lv["burst_left"] in (0, 1):
                    lv["fire_time"] = lv["fire_delay"]
                else:
                    lv["burst_left"] -= 1
                lv["burst_wait"] = lv["burst_delay"]
                fire_object(o, o.aitype, firex, firey, angle, bg)
    else:
        lv["burst_wait"] -= 1
    return True


@lisp("flyer_damage")
def flyer_damage(o, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
    """flyer.lsp:110-122: no damage from a FLYER's or GREEN_FLYER's own shots, none while
    stopped; otherwise smoke, a jolt upward, a flinch and normal damage."""
    if from_obj is not None and from_obj.objs and from_obj.objs[0].ctype.name in ("FLYER", "GREEN_FLYER"):
        return
    if o.state == "stopped":
        return
    o.lvars["smoke_time"] = 30
    o.yvel -= 14
    o.set_state("flinch_up")
    o.damage_fun(amount, from_obj, hitx, hity, push_xvel, push_yvel)


SROCKET_SPEED = {"easy": 12, "medium": 15, "hard": 17, "extreme": 22}  # ant.lsp:64-69


@lisp("strait_rocket_ai")
def strait_rocket_ai(o) -> bool:
    """ant.lsp:63-85: fly straight at the angle in ``aistate``. Hitting a character makes an
    explosion that hurts within 25 pixels; any hit leaves a flash (EG_EXPLO) and ends the rocket."""
    set_course(o, o.aistate, SROCKET_SPEED[o.world.difficulty])
    set_frame_angle(o, 0, 359, o.aistate)
    stat = bmove(o, None)
    if stat is True:
        return True
    if stat is not None:
        for name, sign, aitype in (("EXPLODE3", 1, 0), ("EXPLODE2", 1, 2), ("EXPLODE3", -1, 1),
                                   ("EXPLODE3", -1, 2)):
            ex = o.x + sign * random(o, 5)
            ey = o.y + sign * random(o, 5)
            o.world.spawn(name, ex, ey, aitype)
        hurt_radius(o, o.x, o.y + 20, 25, 15, None, 10)
    flash = o.world.spawn("EG_EXPLO", o.x, o.y)
    eg_explo_ufun(flash, o, None)  # (user_fun myself (car stat)): car of an object is nil (lisp.c:554-560)
    return False


@lisp("animate_ai")
def animate_ai(o) -> bool:
    return o.next_picture()  # ant.lsp:92: play the animation once, then go


@lisp("eg_explo_ufun")
def eg_explo_ufun(o, creator, block_flags) -> None:
    """ant.lsp:94-98."""
    o.direction = creator.direction
    if block_flags and (blocked_left(block_flags) or blocked_right(block_flags)):
        o.set_state("blocking")


# --- power-ups -----------------------------------------------------------------------------------

def _take_power(o, power: int, item: str) -> bool:
    o.next_picture()
    if not touching_bg(o):
        return True
    bg = o.world.bg(o)
    bg.lvars["special_power"] = power
    if power == FAST_POWER and bg.controller is not None:
        bg.controller.draw_solid = find_rgb(255, 255, 255)  # make_view_solid: a white flash
    if power == HEALTH_POWER:
        give_player_health(bg, 100)
    o.world.emit("pickup", item=item, uid=o.uid, x=o.x, y=o.y)
    return False


@lisp("fast_ai")
def fast_ai(o) -> bool:
    return _take_power(o, FAST_POWER, "fast")  # powerup.lsp:39-47


@lisp("sneaky_power_ai")
def sneaky_power_ai(o) -> bool:
    return _take_power(o, SNEAKY_POWER, "sneaky")  # powerup.lsp:59-65


@lisp("fly_power_ai")
def fly_power_ai(o) -> bool:
    return _take_power(o, FLY_POWER, "fly")  # powerup.lsp:74-80


@lisp("health_power_ai")
def health_power_ai(o) -> bool:
    return _take_power(o, HEALTH_POWER, "ultra health")  # powerup.lsp:93-102


# --- Level 2: blocks, steps and pushers ----------------------------------------------------------

@lisp("block_ai")
def block_ai(o) -> bool:
    """duong.lsp:117-125: at no health a block crumbles, then goes."""
    if o.hp <= 0:
        if o.state == "dieing":
            return o.next_picture()
        play_sound(o, "CRUMBLE_SND")
        o.set_state("dieing")
    return True


@lisp("step_ai")
def step_ai(o) -> bool:
    """ladder.lsp:31-36: the step is there while unlinked or its first link is on."""
    if not o.objs or o.objs[0].aistate != 0:
        o.set_state("stopped")
    else:
        o.set_state("running")  # "step_gone"
    return True


@lisp("pusher_cons")
def pusher_cons(o) -> None:
    set_aistate(o, 4)  # general.lsp:4: the speed is kept in aistate


@lisp("pusher_ai")
def pusher_ai(o) -> bool:
    """general.lsp:5-14: while on, a touching player is moved ``aistate`` pixels its way."""
    if not o.objs or o.objs[0].aistate != 0:
        o.next_picture()
        if touching_bg(o):
            xamount = o.aistate if o.direction > 0 else -o.aistate
            lisp_try_move(o.world.bg(o), xamount, 0)
    return True


# --- Level 2: the tracking gun --------------------------------------------------------------------

@lisp("track_cons")
def track_cons(o) -> None:
    """guns.lsp:355-362."""
    lv = o.lvars
    lv["angle"] = 270
    lv["track_speed"] = 1
    lv["fire_delay"] = 5
    lv["burst_total"] = 3
    lv["continue_time"] = 8
    lv["track_start_angle"] = 180
    lv["track_end_angle"] = 359


def track_fire(o) -> None:
    """guns.lsp:364-378: one shot of type ``aitype`` from the barrel's end, 2 degrees either
    way at random; then the next shot of the burst, or the pause after it."""
    lv = o.lvars
    a = lv["angle"]
    x = o.x + lnum(lmul(lcos(a), 18))
    y = o.y - 15 - lnum(lmul(lsin(a), 15))
    fire_object(o, o.aitype, x, y, lmod(a + (2 - random(o, 5)), 360), o.world.bg(o))
    if lv["burst_total_left"] in (0, 1):
        lv["continue_time_left"] = lv["continue_time"]
    else:
        lv["burst_total_left"] -= 1
        lv["fire_delay_left"] = lv["fire_delay"]
    o.set_state("firing")
    set_frame_angle(o, 0, 359, a)


def track_set_angle(o, new_angle: int) -> None:
    """guns.lsp:380-385: only angles inside the gun's arc are taken."""
    lv = o.lvars
    start, end = lv["track_start_angle"], lv["track_end_angle"]
    if start > end:
        if end <= new_angle <= start:
            lv["angle"] = new_angle
    elif start <= new_angle <= end:
        lv["angle"] = new_angle


@lisp("track_ai")
def track_ai(o) -> bool:
    """guns.lsp:387-430: off until activated; then it opens and turns toward a point 8 px above
    the player's feet by at most ``track_speed`` degrees a tick, inside its arc. It fires whenever
    that turn (``angle_add``, capped at ``track_speed``) is under 5 degrees and its delays are 0,
    so a slow gun fires even when it cannot reach the player. Shots are ``fire_delay`` + 1 ticks
    apart in a burst of ``burst_total``, with ``continue_time`` + 1 ticks between bursts; the
    counters start at 0, so the first burst is one shot."""
    if o.hp == 0:
        return False
    if not activated(o):
        o.targetable_on = 0
        o.set_state("stopped")
        return True
    if o.state == "stopped":
        o.targetable_on = 1
        o.set_state("opening")
        return True
    if o.state == "opening" and o.next_picture():
        return True
    lv = o.lvars
    o.set_state("spinning")
    set_frame_angle(o, 0, 359, lv["angle"])
    if lv["continue_time_left"] == 0:
        if lv["fire_delay_left"] == 0:
            bg = o.world.bg(o)
            pangle = atan2(o.y - bg.y + 8, bg.x - o.x)
            angle = lv["angle"]
            clock_dist = angle - pangle if pangle < angle else angle + (360 - pangle)
            closest = 360 - clock_dist if clock_dist > 180 else clock_dist
            angle_add = lv["track_speed"] if closest >= lv["track_speed"] else closest
            if clock_dist > 180:  # which way round is shorter
                track_set_angle(o, lmod(angle + angle_add, 360))
            else:
                track_set_angle(o, lmod(angle - angle_add + 360, 360))
            if angle_add < 5:  # nearly on target: fire
                track_fire(o)
        else:
            lv["fire_delay_left"] -= 1
    else:
        lv["continue_time_left"] -= 1
        if lv["continue_time_left"] == 0:
            lv["burst_total_left"] = lv["burst_total"]
    return True


# --- Level 2: the cleaner robot and the Juggernaut ------------------------------------------------

@lisp("explo_damage")
def explo_damage(o, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
    """jugger.lsp:153-157: a small explosion near its middle (it ignores where the hit was); never pushed."""
    o.world.spawn("EXPLODE6", o.x + (10 - random(o, 20)), o.y - random(o, 30), 0)
    o.damage_fun(amount, from_obj, hitx, hity, 0, 0)
    if o.hp == 0:
        play_sound(o, "BLOWN_UP")


@lisp("rob_cons")
def rob_cons(o) -> None:
    o.xvel = 2  # jugger.lsp:159


ROB_EXPLOSIONS = ((5, -10, 0), (-5, -15, 2), (10, -2, 1), (-10, -20, 3), (20, -27, 4), (-25, -30, 2),
                  (20, -5, 4), (-3, -1, 5))  # jugger.lsp:137-144: (dx, dy, delay)


@lisp("rob1_ai")
def rob1_ai(o) -> bool:
    """jugger.lsp:103-149: the cleaner robot waits (hidden, or pushing the player away) until
    its link is on, fades in if it was hidden, then rolls ahead by ``xvel`` a tick while there is
    room 23 pixels ahead, pushing the player. At no health it explodes and goes 3 ticks later."""
    if o.fade_count != 0:  # fading in
        o.set_fade_count(o.fade_count - 1)
    s = o.aistate
    if s == 0:  # wait for the sensor
        if o.lvars["rob_hiden"] == 1:
            o.targetable_on = 0
            o.set_state("rob_hiding")
        else:
            o.targetable_on = 1
            push_char(o, 30, 55)
        if not o.objs or o.objs[0].aistate != 0:
            if o.lvars["rob_hiden"] == 1:
                o.set_fade_count(15)
            set_aistate(o, 1)
        return True
    if s == 1:  # roll toward the player
        push_char(o, 30, 55)
        o.next_picture()
        if cmod(state_time(o), 6) == 0:
            play_sound(o, "CLEANER_SND")
        lisp_try_move(o, 0, 10)
        if o.direction > 0:
            if can_see(o, o.x, o.y, o.x + o.xvel + 23, o.y, False):
                o.x += o.xvel
        elif can_see(o, o.x, o.y, o.x - o.xvel - 23, o.y, False):
            o.x -= o.xvel
        if o.hp <= 0:
            for dx, dy, delay in ROB_EXPLOSIONS:
                o.world.spawn("EXPLODE1", o.x + dx, o.y + dy, delay)
            o.world.emit("enemy_killed", uid=o.uid, type=o.ctype.name, x=o.x, y=o.y)
            set_aistate(o, 2)
        return True
    if s == 2:  # dead: go after 3 ticks
        push_char(o, 30, 55)
        return state_time(o) < 3
    return False  # (select) with no match returns nil


@lisp("jug_cons")
def jug_cons(o) -> None:
    o.lvars["throw_xvel"] = 13  # jugger.lsp:69-72
    o.lvars["throw_yvel"] = -10
    o.change_aitype(10)


@lisp("jug_ai")
def jug_ai(o) -> bool:
    """jugger.lsp:4-67: when activated, a walking Juggernaut stomps toward the player through
    its walk animation and throws a grenade at the end of it; a stationary one throws one every
    ``aitype`` ticks. At no health it plays its death and counts as a kill."""
    if o.hp <= 0:
        if o.state == "dieing":
            if not o.next_picture():
                v = o.world.bg(o).controller
                if v is not None:
                    v.kills += 1
                o.world.emit("enemy_killed", uid=o.uid, type=o.ctype.name, x=o.x, y=o.y)
                return False
            return True
        o.set_state("dieing")
        return o.state == "dieing"  # set_state's value (clisp.c:1152-1157)
    if not activated(o):
        o.targetable_on = 0
        return True
    o.targetable_on = 1
    push_char(o, 35, 40)
    lv = o.lvars
    s = o.aistate
    if s == 0:  # prepare to walk toward the player
        if lv["stationary"] == 0:
            o.set_state("running")
            go_state(o, 1)
        elif state_time(o) > o.aitype:
            o.set_state("weapon_fire")
            set_aistate(o, 2)
    elif s == 1:  # walk toward the player
        if lv["stationary"] == 0:
            o.direction = toward(o)
            curx, cury = o.x, o.y  # in case it walks off a cliff
            if o.next_picture():
                if o.current_frame == 8:
                    play_sound(o, "JSTOMP_SND")
            else:
                play_sound(o, "JSTOMP_SND")
                o.set_state("weapon_fire")
                set_aistate(o, 2)
            if can_see(o, o.x, o.y, o.x, o.y + 5, False):
                o.x, o.y = curx, cury
                lisp_try_move(o, 0, 10)
        elif state_time(o) > o.aitype:
            o.set_state("weapon_fire")
            set_aistate(o, 2)
    elif s == 2:  # start firing
        if state_time(o) > 3:
            xspeed = lv["throw_xvel"] * o.direction
            yspeed = lv["throw_yvel"]
            g = o.world.spawn("GRENADE", o.x, o.y - 24, 1)
            grenade_ufun(g, o, None)
            g.xvel, g.yvel = xspeed, yspeed
            go_state(o, 3)
        else:
            o.next_picture()
    elif s == 3:  # wait for the throw animation
        if not o.next_picture():
            set_aistate(o, 0)
    return True


@lisp("grenade_ufun")
def grenade_ufun(o, creator, _unused=None) -> None:
    """weapons.lsp:120-132: a thrown grenade takes its thrower's direction and speed."""
    o.direction = creator.direction
    play_sound(o, "GRENADE_THROW")
    if o.aitype == 1:
        o.xvel = 13 + random(o, 2) if o.direction > 0 else -13 + random(o, 2)
        o.yvel = -4
    elif o.aitype == 2:
        o.xvel = 7 + random(o, 2) if o.direction > 0 else -7 + random(o, 2)
        o.yvel = -10
    o.xvel += creator.xvel
    o.add_object(creator)
