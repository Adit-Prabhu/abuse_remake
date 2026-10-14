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
    hurt_radius,
    play_sound,
    random,
    set_aistate,
    set_course,
    set_frame_angle,
    state_time,
    touching_bg,
)
from .player import FAST_POWER, FLY_POWER, HEALTH_POWER, SNEAKY_POWER, give_player_health
from .weapons import bounce_move, fire_object

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


# english.lsp:226-243 (get_train_msg). Checked against the file by tests/test_training_level.py.
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
