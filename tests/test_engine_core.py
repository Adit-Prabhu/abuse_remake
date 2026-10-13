"""Engine core: collision maths against the compiled original, physics rules, determinism."""

import random
import subprocess

import pytest

from abuse_remake.engine.cmath import RAND_TABLE, JRand, cdiv, cmod, lisp_atan2, lisp_cos, lisp_sin
from abuse_remake.engine.game import Game, WeaponCommand
from abuse_remake.engine.geometry import setback_intersect
from abuse_remake.engine.view import Inputs


def only_start(o):
    return o.type_name == "START"


def aim(g):
    return dict(pointer_x=g.player.x + 100, pointer_y=g.player.y - 20)


# --- C arithmetic and tables -------------------------------------------------------------

def test_c_division_truncates_toward_zero():
    assert cdiv(-7, 2) == -3 and cdiv(7, -2) == -3 and cdiv(-7, -2) == 3
    assert cmod(-7, 3) == -1 and cmod(7, -3) == 1


def test_trig_tables_and_atan2_quirk():
    assert lisp_sin(90) == 0x10000 and lisp_cos(0) == 0x10000 and lisp_cos(90) == lisp_sin(180)
    # negative angles index from the end (lisp.c:683-688); trig.c stores sin(270) as 0xffff0001
    assert lisp_sin(-90) == lisp_sin(270) == -0xFFFF
    assert lisp_atan2(0, 5) == 0 and lisp_atan2(5, 0) == 90 and lisp_atan2(-5, 0) == 270
    # lisp.c:727-731 returns 260, not 270, for steep down-right angles past the table
    assert lisp_atan2(-100000, 1) == 260


def test_random_table_is_the_fixed_original_sequence():
    # jrand.c: rseed = 'FUCK'; rseed = rseed*0x41c64e6d + 12345; entry = (rseed >> 16) & 0xffff
    assert RAND_TABLE[:5] == (976, 25285, 23126, 7218, 62995)
    r = JRand(0)
    assert [r.jrand() for _ in range(5)] == [976, 25285, 23126, 7218, 62995]
    r = JRand(1023)
    r.jrand()
    assert r.rand_on == 1024  # rand_on is an unsigned short; only the table index wraps
    r.jrand()
    assert RAND_TABLE[0] == 976  # index 1024 & 1023 == 0


# --- collision: differential against the original C ---------------------------------------

def test_setback_intersect_matches_compiled_original(c_reference):
    binary = c_reference("setback_intersect")
    rng = random.Random(1996)
    cases = []
    for _ in range(20000):
        x1, y1 = rng.randint(0, 120), rng.randint(0, 120)
        x2, y2 = x1 + rng.randint(-25, 25), y1 + rng.randint(-25, 25)
        xp1, yp1 = rng.randint(0, 120), rng.randint(0, 120)
        if rng.random() < 0.3:  # axis-aligned tile edges are the common case
            if rng.random() < 0.5:
                xp2, yp2 = xp1, yp1 + rng.randint(-30, 30)
            else:
                xp2, yp2 = xp1 + rng.randint(-30, 30), yp1
        else:
            xp2, yp2 = xp1 + rng.randint(-30, 30), yp1 + rng.randint(-30, 30)
        cases.append((x1, y1, x2, y2, xp1, yp1, xp2, yp2, rng.choice((-1, 0, 1))))
    out = subprocess.run([str(binary)], input="\n".join(" ".join(map(str, c)) for c in cases) + "\n",
                         capture_output=True, text=True, check=True).stdout.splitlines()
    assert len(out) == len(cases)
    mismatches = []
    for case, line in zip(cases, out, strict=True):
        r, cx2, cy2 = (int(v) for v in line.split())
        hit, px2, py2 = setback_intersect(*case)
        if (int(hit), px2, py2) != (r, cx2, cy2):
            mismatches.append((case, (r, cx2, cy2), (hit, px2, py2)))
    assert mismatches == []


def test_tile_prefilter_changes_no_result():
    g = Game(strict=False, object_filter=only_start)
    tiles = g.world.tiles
    rng = random.Random(7)
    for _ in range(3000):
        x1, y1 = rng.randint(0, 2999), rng.randint(0, 1799)
        x2, y2 = x1 + rng.randint(-40, 40), y1 + rng.randint(-40, 40)
        fast = tiles.foreground_intersect(x1, y1, x2, y2)
        assert fast == tiles.foreground_intersect_reference(x1, y1, x2, y2)


# --- physics derived from objects.c and people.lsp ------------------------------------------

def settle(g, ticks=12):
    for _ in range(ticks):
        g.step(Inputs(**aim(g)))


def test_player_spawns_at_start_and_lands():
    g = Game(strict=False, object_filter=only_start)
    assert (g.player.x, g.player.y, g.player.hp) == (167, 43, 100)  # START; DARNEL start_hp 100
    settle(g)
    assert g.player.gravity() == 0 and g.player.yvel == 0  # standing on the floor
    assert g.view.weapons[0] == 0 and g.view.weapons[1:] == [-1] * 6  # laser owned, no ammo


def test_running_right_reaches_top_speed_at_once_but_left_accelerates():
    # objects.c:1258-1272: from "stopped", right sets xvel = run_top_speed (9) directly,
    # while left only sets xacel; start_accel (8) then caps the first step at 8.
    g = Game(strict=False, object_filter=only_start)
    settle(g)
    x0 = g.player.x
    g.step(Inputs(x=1, **aim(g)))
    assert g.player.x - x0 == 9 and g.player.state == "running"
    for _ in range(4):
        g.step(Inputs(x=1, **aim(g)))
    assert g.player.xvel == 9  # run_top_speed
    g2 = Game(strict=False, object_filter=only_start)
    settle(g2)
    g2.step(Inputs(x=1, **aim(g2)))  # face right, move away from the start wall
    settle(g2, 4)
    x0 = g2.player.x
    g2.step(Inputs(x=-1, **aim(g2)))
    assert g2.player.direction == -1
    assert x0 - g2.player.x == 8


def test_releasing_the_key_stops_within_one_tick():
    g = Game(strict=False, object_filter=only_start)
    settle(g)
    for _ in range(5):
        g.step(Inputs(x=1, **aim(g)))
    g.step(Inputs(**aim(g)))  # stop_accel 9 >= xvel 9: stop_x() and "stopped" (objects.c:1306-1314)
    assert g.player.xvel == 0 and g.player.state == "stopped"


def test_jump_starts_at_jump_yvel():
    # objects.c:1341-1352: yvel = jump_yvel (-15). On the first tick gravity's fraction (200/256)
    # has not yet carried into yacel or yvel (objects.c:910-933), so yvel is still -15.
    g = Game(strict=False, object_filter=only_start)
    settle(g)
    for _ in range(8):  # walk out from under the low start ceiling
        g.step(Inputs(x=1, **aim(g)))
    y0 = g.player.y
    g.step(Inputs(y=-1, **aim(g)))
    assert g.player.state == "run_jump" and g.player.gravity() == 1
    assert g.player.yvel == -15
    assert g.player.y == y0 - 15


def test_fall_speed_grows_at_most_one_per_tick_past_ten():
    # cop.c:621-625: once yvel > 10, yacel is cleared and yvel loses 1 before the move. That
    # tick's gravity can add back 1 from yacel's carried fraction and 1 from the fyvel carry
    # (objects.c:910-933), so "terminal velocity" only slows the fall: yvel can still creep up
    # by at most 1 per tick. This is what the original does, not a hard cap.
    g = Game(strict=False, object_filter=only_start)
    p = g.player
    tiles = g.world.tiles

    def empty(bx, by):
        return not tiles.segments.get(tiles.get(bx, by))

    bx, by = next((bx, by) for by in range(tiles.height - 20) for bx in range(1, tiles.width - 1)
                  if all(empty(bx + dx, by + dy) for dx in (-1, 0, 1) for dy in range(20)))
    p.x, p.y = bx * 30 + 15, by * 15 + 60  # top of a 20-tile empty shaft
    speeds = []
    for _ in range(25):
        g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y))
        speeds.append(p.yvel)
    assert max(speeds) > 10
    past_ten = [(a, b) for a, b in zip(speeds, speeds[1:], strict=False) if a > 10]
    assert past_ten and all(b - a <= 1 for a, b in past_ten)
    below_ten = [b - a for a, b in zip(speeds, speeds[1:], strict=False) if a <= 10 and b <= 10]
    assert max(below_ten) >= 2  # without the cap, gravity adds more than 1 per tick


def zap_ticks(g, ticks):
    out = []
    for t in range(ticks):
        g.step(Inputs(b2=1, **aim(g)))
        if any(e.kind == "sound" and e.data["name"] == "ZAP_SND" for e in g.world.events):
            out.append(t)
    return out


def test_laser_fires_without_ammo_every_five_ticks():
    # cop.c:247-262: no ammo -> fire_delay1 = 5; top_ai counts it down each tick
    g = Game(strict=False, object_filter=only_start)
    settle(g)
    shots = zap_ticks(g, 30)
    assert {b - a for a, b in zip(shots, shots[1:], strict=False)} == {5}
    assert g.view.weapons[0] == 0  # nothing is taken


def test_laser_with_ammo_fires_every_three_ticks_and_uses_ammo():
    g = Game(strict=False, object_filter=only_start)
    settle(g)
    g.view.weapons[0] = 20
    shots = zap_ticks(g, 30)
    assert {b - a for a, b in zip(shots, shots[1:], strict=False)} == {3}
    assert g.view.weapons[0] == 20 - len(shots)


@pytest.mark.parametrize("seed", [0, 5, 1023])
def test_same_seed_and_inputs_give_identical_state(seed):
    def run():
        g = Game(seed=seed, strict=False, object_filter=only_start)
        script = [Inputs(x=1), Inputs(x=1, y=-1), Inputs(b2=1), Inputs(x=-1, b2=1), Inputs()]
        for i in range(60):
            inp = script[i % len(script)]
            inp.pointer_x, inp.pointer_y = g.player.x + 80, g.player.y - 30
            g.step(inp)
        return g.state_hash()
    assert run() == run()


# --- weapons, ammo and damage rules ----------------------------------------------------------

def test_ammo_is_capped_at_999_and_empty_weapon_switches_to_the_most_powerful():
    # view.c:40-69: cap at 999; when the current weapon runs dry, switch_to_powerful picks the
    # highest slot with ammo, skipping slot 3 (the firebomb)
    g = Game(strict=False, object_filter=only_start)
    v = g.view
    v.give_weapon(1)
    v.add_ammo(1, 5000)
    assert v.weapons[1] == 999
    v.give_weapon(3)
    v.add_ammo(3, 5)
    v.current_weapon = 1
    v.add_ammo(1, -999)
    assert v.pending_weapon == 0  # slot 3 is skipped, slot 2 is not owned -> back to the laser
    v.give_weapon(2)
    v.add_ammo(2, 4)
    v.add_ammo(1, 1)
    v.current_weapon = 1
    v.add_ammo(1, -1)
    assert v.pending_weapon == 2


def test_ammo_for_a_weapon_you_do_not_have_is_ignored_and_empty_weapons_cannot_be_selected():
    g = Game(strict=False, object_filter=only_start)
    v = g.view
    v.add_ammo(2, 10)  # view.c:47: no weapon, no ammo
    assert v.weapons[2] == -1
    assert v.select_weapon(2) is False and v.pending_weapon is None
    v.give_weapon(2)
    assert v.select_weapon(2) is False  # owned but empty: number keys need ammo (view.c:599)
    v.add_ammo(2, 3)
    assert v.select_weapon(2) is True and v.pending_weapon == 2


@pytest.mark.parametrize("difficulty,taken", [("easy", 5), ("medium", 7), ("hard", 10), ("extreme", 30)])
def test_player_damage_is_scaled_by_difficulty(difficulty, taken):
    # people.lsp:330-336: easy /2, medium *3/4, hard *1, extreme *3
    g = Game(strict=False, difficulty=difficulty, object_filter=only_start)
    settle(g)
    g.player.do_damage(10, None, g.player.x, g.player.y, 0, 0)
    assert g.player.hp == 100 - taken


def test_player_damage_draws_random_numbers_in_the_original_order():
    # bottom_damage: (random 2) picks the flinch, damage_fun's do_flinch draws jrandom(2),
    # and a hit of more than 8 picks a pain sound with (random 4) (people.lsp:338-368, objects.c:443)
    g = Game(seed=17, strict=False, object_filter=only_start)
    settle(g)
    rng = g.world.rng
    start = rng.rand_on
    g.player.do_damage(20, None, g.player.x, g.player.y, 0, 0)
    assert (rng.rand_on - start) & 0xFFFF == 3
    pain = [e.data["name"] for e in g.world.events
            if e.kind == "sound" and e.data["name"].startswith("PLAYER_PAIN")]
    from abuse_remake.engine.cmath import RAND_TABLE
    assert pain == [f"PLAYER_PAIN{RAND_TABLE[(start + 2) & 1023] % 4}"]


@pytest.mark.parametrize("difficulty,gain", [("easy", 20), ("medium", 15), ("hard", 10), ("extreme", 4)])
def test_give_player_health_scales_and_caps_at_100(difficulty, gain):
    from abuse_remake.engine.behaviors.player import give_player_health
    g = Game(strict=False, difficulty=difficulty, object_filter=only_start)
    p = g.player
    p.set_hp(50)
    assert give_player_health(p, 20) is True and p.hp == 50 + gain
    p.set_hp(98)
    give_player_health(p, 20)
    assert p.hp == 100
    assert give_player_health(p, 20) is False  # full: the pickup stays


def test_hurt_radius_falls_off_with_distance_and_pushes_away():
    # level.c:2979-3019: damage (r - d) * m / r with an octagonal distance; push away from x,y
    g = Game(strict=False, object_filter=only_start)
    w = g.world
    near = w.spawn("ANT_ROOF", 1000, 500)
    far = w.spawn("ANT_ROOF", 1030, 500)
    for a in (near, far):
        a.set_hp(100)
        a.set_aistate(2)
        a.set_state("stopped")
    w.active = [near, far]
    w.hurt_radius(990, 500, 60, 40, None, None, 20)
    # near: cx=10, cy1=0 -> d=10; far: cx=40 -> d=40 (the head distance is larger for both)
    assert near.hp == 100 - (60 - 10) * 40 // 60
    assert far.hp == 100 - (60 - 40) * 40 // 60
    assert near.xvel > 0 and far.xvel > 0  # pushed away from the blast to the left


def test_grenade_explodes_on_hitting_the_floor():
    g = Game(strict=False, object_filter=only_start)
    settle(g)
    g.view.give_weapon(1)
    g.view.add_ammo(1, 5)
    g.step(Inputs(**aim(g)), WeaponCommand(select=1))
    p = g.player
    for _ in range(3):
        g.step(Inputs(b2=1, pointer_x=p.x + 30, pointer_y=p.y + 40))  # throw at the floor
    booms = 0
    for _ in range(30):
        g.step(Inputs(**aim(g)))
        booms += sum(1 for e in g.world.events if e.kind == "explosion")
    assert g.view.weapons[1] < 5 and booms >= 1


def test_player_rocket_accelerates_by_two_up_to_fifteen():
    # guns.lsp:96-99: player rockets start at 5 with max_speed 14; rocket_ai adds 2 while
    # speed < max_speed, so the speed runs 7, 9, 11, 13, 15 and stops at 15
    from abuse_remake.engine.behaviors.weapons import fire_object
    g = Game(strict=False, object_filter=only_start)
    settle(g)
    r = fire_object(g.player, 3, g.player.x, g.player.y - 300, 90, None)  # straight up, in the air
    speeds = []
    from abuse_remake.engine.behaviors.weapons import rocket_ai
    for _ in range(7):
        if not rocket_ai(r):
            break
        speeds.append(r.lvars["speed"])
    assert r.lvars["max_speed"] == 14
    assert speeds[:5] == [7, 9, 11, 13, 15]
