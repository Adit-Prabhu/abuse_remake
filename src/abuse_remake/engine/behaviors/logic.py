"""The logic network: gates, switches, sensors, dimmers, sound emitters and progress objects.

Sources: data/original/lisp/gates.lsp, switch.lsp, light.lsp, sfx.lsp, people.lsp, common.lsp;
SENSOR's AI is compiled C (historicalsource/abuse@01cce80 abuse/src/sensor.c; the Lisp
version in switch.lsp is commented out). An object's ``aistate`` is its output signal: 0 is
off, anything else is on. ``activated`` reads the first linked object's signal.
"""

from __future__ import annotations

from . import lisp
from .lispfns import (
    activated,
    distx,
    disty,
    go_state,
    play_sound,
    random,
    set_aistate,
    state_time,
    touching_bg,
)


def _on(o) -> None:
    o.set_state("on_state")
    set_aistate(o, 1)  # Lisp set_aistate also zeroes aistate_time (clisp.c:1074-1078)


def _off(o) -> None:
    o.set_state("stopped")
    set_aistate(o, 0)


def pressing_action_key(player) -> bool:
    """people.lsp:74-75: the action key is "down"."""
    v = player.controller
    return v is not None and v.y_suggestion > 0


@lisp("do_nothing")
def do_nothing(o) -> bool:
    o.next_picture()  # common.lsp
    return True


# --- gates.lsp ---------------------------------------------------------------------------

@lisp("delay_ai")
def delay_ai(o) -> bool:
    if o.xvel > 0:
        o.xvel -= 1
        if o.xvel == 0:
            if o.state == "stopped":
                set_aistate(o, 1)
                o.set_state("on_state")
            else:
                o.set_state("stopped")
                set_aistate(o, 0)
    elif o.objs:
        if (o.aistate == 0) != (o.objs[0].aistate == 0):
            o.xvel = o.lvars["delay_time"]
    return True


@lisp("and_ai")
def and_ai(o) -> bool:
    if all(link.aistate != 0 for link in o.objs):  # and_check: true for no links
        _on(o)
    else:
        _off(o)
    return True


@lisp("xor_ai")
def xor_ai(o) -> bool:
    stat = False
    for link in reversed(o.objs):
        if link.aistate != 0:
            stat = not stat
    if stat:
        _on(o)
    else:
        _off(o)
    return True


@lisp("or_ai")
def or_ai(o) -> bool:
    if any(link.aistate != 0 for link in o.objs):
        _on(o)
    else:
        _off(o)
    return True


@lisp("not_ai")
def not_ai(o) -> bool:
    if o.objs:
        if o.objs[0].aistate == 0:
            _on(o)
        else:
            _off(o)
    return True


@lisp("pulse_ai")
def pulse_ai(o) -> bool:
    if o.objs and o.objs[0].aistate != 0:
        if o.lvars["time_left"] == 0:
            if o.aistate == 0:
                o.lvars["time_left"] = o.lvars["pulse_speed"]
                _on(o)
            else:
                _off(o)
        else:
            o.lvars["time_left"] -= 1
    return True


@lisp("indicator_ai")
def indicator_ai(o) -> bool:
    if o.objs:
        if o.objs[0].aistate == 0:
            _off(o)
        else:
            _on(o)
    return True


# --- switch.lsp ----------------------------------------------------------------------------

def _near_and_pressing(o) -> bool:
    if not (distx(o) < 20 and disty(o) < 30):
        return False
    return pressing_action_key(o.world.bg(o))


@lisp("switcher_ai")
def switcher_ai(o) -> bool:
    o.next_picture()
    s = o.aistate
    if s == 0:
        if _near_and_pressing(o):
            play_sound(o, "SWITCH_SND")
            o.set_state("running")
            set_aistate(o, 1)
            o.world.emit("switch", uid=o.uid, on=True, x=o.x, y=o.y)
    elif s == 1:
        if not pressing_action_key(o.world.bg(o)):
            set_aistate(o, 2)
    elif s == 2:
        if _near_and_pressing(o):
            play_sound(o, "SWITCH_SND")
            o.set_state("stopped")
            set_aistate(o, 4)
            o.world.emit("switch", uid=o.uid, on=False, x=o.x, y=o.y)
    elif s == 4:
        if not pressing_action_key(o.world.bg(o)):
            set_aistate(o, 0)
    return True


@lisp("switch_once_ai")
def switch_once_ai(o) -> bool:
    if o.aistate == 0:
        o.next_picture()
        if _near_and_pressing(o):
            random(o, 1000)  # (print (random 1000)): a debug print that still draws a random number
            play_sound(o, "SWITCH_SND")
            o.set_state("running")
            set_aistate(o, 1)
            o.world.emit("switch", uid=o.uid, on=True, x=o.x, y=o.y)
    return True


@lisp("switch_delay_ai")
def switch_delay_ai(o) -> bool:
    s = o.aistate
    if s == 0:
        o.next_picture()
        if _near_and_pressing(o):
            random(o, 1000)
            play_sound(o, "SWITCH_SND")
            o.set_state("running")
            set_aistate(o, 1)
    elif s == 1:
        if not pressing_action_key(o.world.bg(o)):
            set_aistate(o, 2)
    elif s == 2:
        if state_time(o) > o.lvars["reset_time"]:
            play_sound(o, "SWITCH_SND")
            o.set_state("stopped")
            set_aistate(o, 0)
    return True


@lisp("lower_reload")
def lower_reload(o) -> None:
    o.world.to_back(o)  # (lower): move to the front of the list, drawn behind everything


@lisp("switch_mover_ai")
def switch_mover_ai(o) -> bool:
    if len(o.objs) <= 1:
        return False
    if o.aistate == 0:
        if o.objs[0].aistate != 0:
            mex, mey = o.x, o.y
            moved = o.objs[1]
            if o.xvel == 0:
                moved.x, moved.y = mex, mey
                moved.set_fade_count(15)
                set_aistate(o, 1)
                return True
            moved.x, moved.y = mex, mey
            return False
        return True
    if o.aistate == 1:
        moved = o.objs[1]
        if moved.fade_count == 0:
            return False
        moved.set_fade_count(moved.fade_count - 1)
        return True
    return False


@lisp("sensor_ai")
def sensor_ai(o) -> bool:
    """sensor.c: on when the player enters the (xvel, yvel) box; off when it leaves the
    (xacel, yacel) box, or after ``hp`` ticks if hp is set; ``unoffable`` sensors stay on."""
    b = o.world.bg(o)
    if o.aistate == 0:
        if abs(b.x - o.x) < o.xvel and abs(b.y - o.y) < o.yvel:
            o.set_aistate(1 if not o.hp else o.hp)
            o.set_state("blocking")
        elif o.state != "stopped":
            o.set_state("stopped")
    elif not o.lvars["unoffable"]:
        if not o.hp:
            if abs(o.x - b.x) > o.xacel or abs(o.y - b.y) > o.yacel:
                o.set_aistate(0)
        else:
            o.set_aistate(o.aistate - 1)
    return True


@lisp("sensor_cons")
def sensor_cons(o) -> None:
    o.change_aitype(1)  # (set_aitype 1) runs sensor_ct: on box 50x50, off box 100x100
    o.add_hp(-10)


@lisp("sensor_ct")
def sensor_ct(o) -> None:
    sizes = {1: (50, 50, 100, 100), 2: (50, 30, 100, 50), 3: (50, 15, 100, 30)}
    if o.aitype in sizes:
        o.xvel, o.yvel, o.xacel, o.yacel = sizes[o.aitype]


@lisp("death_sen_ai")
def death_sen_ai(o) -> bool:
    if not o.objs:
        o.set_state("running")
        set_aistate(o, 1)
    elif o.objs[0].state in ("dead", "blown_back_dead"):
        o.remove_object(o.objs[0])
    return True


# --- light.lsp -----------------------------------------------------------------------------

def _get_light_value(o) -> int:
    if o.lights:
        return o.lights[0].outer_radius
    return o.world.views[0].ambient


def _set_light_value(o, x: int) -> None:
    if o.lights:
        light = o.lights[0]
        if x > light.inner_radius:  # set_light_r2 (clisp.c case 105); calc_range only affects drawing
            light.outer_radius = x
    elif 0 <= x < 64:  # set_ambient_light (clisp.c case 179)
        o.world.views[0].ambient = x


def _general_dim_ai(o, activation, deactivation) -> bool:
    s = o.aistate
    if s == 0:
        if activation(o):
            if o.xvel * o.direction < 0 and o.yacel == 0:
                play_sound(o, "FADEON_SND")
            return go_state(o, 1)
        return True
    if s == 1:
        if state_time(o) > o.yvel:
            return go_state(o, 2)
        _set_light_value(o, _get_light_value(o) - o.xvel * o.direction)
        return True
    if s == 2:
        if o.objs:
            set_aistate(o.objs[0], 1)
        set_aistate(o, 3)
        return True
    if s == 3:
        if deactivation(o):
            if o.xvel * o.direction > 0 and o.yacel == 0:
                play_sound(o, "FADEON_SND")
            return go_state(o, 4)
        return True
    if s == 4:
        if state_time(o) > o.yvel:
            return go_state(o, 5)
        _set_light_value(o, _get_light_value(o) + o.xvel * o.direction)
        return True
    if s == 5:
        if o.objs:
            set_aistate(o.objs[0], 4)
        set_aistate(o, 0)
        return True
    return True


@lisp("switch_dim_ai")
def switch_dim_ai(o) -> bool:
    return _general_dim_ai(o, lambda s: bool(s.objs) and s.objs[0].aistate != 0,
                           lambda s: bool(s.objs) and s.objs[0].aistate == 0)


@lisp("dim_cons")
def dim_cons(o) -> None:
    o.xvel, o.yvel = 20, 5


# --- sfx.lsp: AMBIENT_SOUND -------------------------------------------------------------------

@lisp("amb_sound_ai")
def amb_sound_ai(o) -> bool:
    if activated(o):
        if o.aistate == 0:
            play_sound(o, f"AMB_SOUND{o.aitype}", o.yvel)
            set_aistate(o, o.xvel + random(o, 1 + o.xacel))
            return o.xvel > 0
        set_aistate(o, o.aistate - 1)
        return True
    set_aistate(o, 0)
    return True


@lisp("amb_sound_ct")
def amb_sound_ct(o) -> None:
    if o.aitype > 16:
        o.change_aitype(0)  # Lisp set_aitype runs this function again (clisp.c:1161)
    else:
        play_sound(o, f"AMB_SOUND{o.aitype}")


@lisp("ambs_cons")
def ambs_cons(o) -> None:
    o.xvel, o.yvel = 100, 127


# --- people.lsp: progress objects ---------------------------------------------------------------

@lisp("next_level_ai")
def next_level_ai(o) -> bool:
    """people.lsp:915-923: standing in the exit and pressing the action key ends the level."""
    if touching_bg(o) and pressing_action_key(o.world.bg(o)):
        o.world.emit("level_complete", next_level=o.aistate)
        o.world.globals["level_complete"] = True
    return True


@lisp("next_level_top_ai")
def next_level_top_ai(o) -> bool:
    """people.lsp:932-937: shifts the random table by 80 every tick it runs."""
    o.world.rng.shift(80)
    oldy = o.y
    from .lispfns import lisp_try_move

    lisp_try_move(o, 0, 100)
    o.lvars["floor_yoff"] = o.y - oldy
    o.y = oldy
    return True


@lisp("tele_beam_ai")
def tele_beam_ai(o) -> bool:
    o.next_picture()
    if o.direction > 0:
        if o.fade_count == 12:
            play_sound(o, "APPEAR_SND", 100)
            o.direction = -1
        else:
            o.set_fade_count(o.fade_count + 1)
    elif o.fade_count == 5:
        play_sound(o, "APPEAR_SND", 100)
        o.direction = 1
    else:
        o.set_fade_count(o.fade_count - 1)
    return True  # the Lisp's last form is an if whose value is non-nil here


@lisp("restart_ai")
def restart_ai(o) -> bool:
    """people.lsp:873-904: a save console. The original asks for a save slot; we save to one
    in-memory slot without the dialog (a `design` choice recorded in the rule map)."""
    s = o.aistate
    if s in (0, 1):
        o.next_picture()
        if touching_bg(o) and pressing_action_key(o.world.bg(o)):
            set_aistate(o, 2)
    elif s == 2:
        o.set_state("running")
        set_aistate(o, 3)
    elif s == 3:
        set_aistate(o, 4)
    elif s == 4:
        o.set_state("stopped")
        set_aistate(o, 1)
        player = o.world.bg(o)
        old_hp = player.hp
        if o.world.difficulty != "extreme":
            player.set_hp(100)
        play_sound(player, "SAVE_SND")
        player.lvars["has_saved_this_level"] = 1
        o.world.emit("checkpoint_saved", console=o.uid, station=o.xvel, x=o.x, y=o.y)
        save = o.world.globals.get("save_hook")
        if save is not None:
            save(o)
        player.set_hp(old_hp)
    return True
