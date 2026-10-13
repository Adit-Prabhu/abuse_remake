"""Level 1 objects: each test exercises a rule from the cited Lisp/C on the real level data."""

import pytest

from abuse_remake.engine.game import Game
from abuse_remake.engine.view import Inputs
from abuse_remake.scope import LEVEL01_TYPES


def idle(g, ticks=1, **kw):
    for _ in range(ticks):
        p = g.player
        g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20, **kw))


def place_player(g, x, y):
    p = g.player
    p.x, p.y = x, y
    p.last_x, p.last_y = x, y
    g.view.last_x, g.view.last_y = x, y


def test_every_level01_type_has_its_behaviours():
    g = Game(seed=0)  # strict mode raises if any in-scope Lisp function lacks a port
    for t in LEVEL01_TYPES:
        assert g.world.missing_behaviours(t) == [], t


def gate_world(gate_type):
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", gate_type))
    gate = g.world.find_type(gate_type)
    sources = [g.world.create("GATE_AND", 0, 0) for _ in range(2)]  # stand-ins holding a signal
    gate.objs[:] = sources
    return g, gate, sources


@pytest.mark.parametrize("a,b,and_out,xor_out", [(0, 0, 0, 0), (1, 0, 0, 1), (0, 1, 0, 1), (1, 1, 1, 0)])
def test_and_and_xor_gates_follow_their_truth_tables(a, b, and_out, xor_out):
    from abuse_remake.engine.behaviors.logic import and_ai, xor_ai
    g, gate, (s1, s2) = gate_world("GATE_AND")
    s1.aistate, s2.aistate = a, b
    and_ai(gate)
    assert gate.aistate == and_out
    xor_ai(gate)
    assert gate.aistate == xor_out


def test_not_gate_inverts_its_first_link():
    from abuse_remake.engine.behaviors.logic import not_ai
    g, gate, (s1, _) = gate_world("GATE_NOT")
    gate.objs[:] = [s1]
    s1.aistate = 0
    not_ai(gate)
    assert gate.aistate == 1 and gate.state == "on_state"
    s1.aistate = 1
    not_ai(gate)
    assert gate.aistate == 0


def test_delay_gate_copies_input_after_delay_time_ticks():
    from abuse_remake.engine.behaviors.logic import delay_ai
    g, gate, (s1, _) = gate_world("GATE_DELAY")
    gate.objs[:] = [s1]
    gate.aistate, gate.state, gate.xvel = 0, "stopped", 0
    gate.lvars["delay_time"] = 3
    s1.aistate = 1
    outputs = []
    for _ in range(5):
        delay_ai(gate)
        outputs.append(gate.aistate)
    assert outputs == [0, 0, 0, 1, 1]  # loads xvel=3, counts down 3 ticks, then switches on


def test_sensor_turns_on_inside_its_box_and_off_outside_the_larger_box():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "SENSOR"))
    s = g.world.find_type("SENSOR")
    s.hp = 0
    s.lvars["unoffable"] = 0
    s.xvel, s.yvel, s.xacel, s.yacel = 50, 50, 100, 100
    from abuse_remake.engine.behaviors.logic import sensor_ai
    place_player(g, s.x + 40, s.y)
    sensor_ai(s)
    assert s.aistate == 1 and s.state == "blocking"
    place_player(g, s.x + 80, s.y)  # outside the on box, inside the off box: stays on
    sensor_ai(s)
    assert s.aistate == 1
    place_player(g, s.x + 120, s.y)
    sensor_ai(s)
    assert s.aistate == 0


def test_switch_toggles_with_the_action_key_and_needs_a_release():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "SWITCH"))
    sw = g.world.find_type("SWITCH")
    place_player(g, sw.x + 5, sw.y)
    idle(g, 3)
    assert sw.aistate == 0
    idle(g, 1, y=1)  # press down (the action key)
    assert sw.aistate == 1 and sw.state == "running"
    idle(g, 2, y=1)  # still held: no second toggle
    assert sw.aistate == 1
    idle(g, 1)  # release
    assert sw.aistate == 2
    idle(g, 1, y=1)
    assert sw.aistate == 4 and sw.state == "stopped"


@pytest.mark.parametrize("difficulty,gain", [("easy", 20), ("medium", 15), ("hard", 10), ("extreme", 4)])
def test_health_pickup_is_scaled_by_difficulty(difficulty, gain):
    g = Game(seed=0, difficulty=difficulty, strict=False,
             object_filter=lambda o: o.type_name in ("START", "HEALTH"))
    h = g.world.find_type("HEALTH")
    idle(g, 2)
    g.player.set_hp(50)
    place_player(g, h.x, h.y)
    idle(g, 1)
    assert g.player.hp == 50 + gain
    assert h.deleted


def test_health_pickup_is_left_when_health_is_full():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "HEALTH"))
    h = g.world.find_type("HEALTH")
    idle(g, 2)
    place_player(g, h.x, h.y)
    idle(g, 1)
    assert g.player.hp == 100 and not h.deleted


def test_ammo_pickup_gives_weapon_selects_it_and_adds_ammo():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "GRENADE_ICON10"))
    icon = g.world.find_type("GRENADE_ICON10")
    idle(g, 2)
    place_player(g, icon.x, icon.y)
    idle(g, 1)
    assert g.view.weapons[1] == 10  # GRENADE_ICON10: start_hp 10 is the ammo amount
    assert g.view.current_weapon == 1  # change_on_pickup selects a newly found weapon


def test_hidden_wall_cracks_then_breaks_when_its_saved_hp_runs_out():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "HIDDEN_WALL1"))
    w = g.world.find_type("HIDDEN_WALL1")
    from abuse_remake.engine.behaviors.world_objects import hwall_ai
    assert w.hp == 20  # the level file saves 20; the type's start_hp of 25 applies only to new walls
    w.objs.clear()  # unlinked walls are always "activated"
    max_hp, frames = w.ability("start_hp"), w.total_frames()
    for _ in range(3):
        w.do_damage(5, None, w.x, w.y, 0, 0)
        assert w.current_frame == frames * (max_hp - w.hp) // max_hp  # cracks (doors.lsp:159-161)
        assert hwall_ai(w)
    w.do_damage(5, None, w.x, w.y, 0, 0)
    assert w.hp == 0 and hwall_ai(w) is False  # explodes and is removed


def test_ant_dies_after_fifteen_damage_and_flinches_when_hit():
    g = Game(seed=4, strict=False, object_filter=lambda o: o.type_name == "START")
    ant = g.world.spawn("ANT_ROOF", g.player.x + 60, g.player.y)
    ant.change_aitype(0)  # ant_ct: aitype 0 has 15 hp
    assert ant.hp == 15
    ant.set_aistate(2)
    ant.do_damage(5, g.player, ant.x, ant.y, 0, 0)
    assert ant.state in ("flinch_up", "flinch_down") and ant.hp == 10
    ant.do_damage(10, g.player, ant.x, ant.y, 0, 0)
    assert ant.hp == 0 and ant.state == "dead"
    assert any(e.kind == "enemy_killed" for e in g.world.events)


def test_hanging_ant_ignores_damage():
    g = Game(seed=4, strict=False, object_filter=lambda o: o.type_name == "START")
    ant = g.world.spawn("ANT_ROOF", g.player.x + 60, g.player.y)
    ant.set_aistate(15)  # ANT_HANGING
    ant.do_damage(5, g.player, ant.x, ant.y, 0, 0)
    assert ant.hp == ant.ability("start_hp")


def test_ants_do_not_hurt_each_other():
    g = Game(seed=4, strict=False, object_filter=lambda o: o.type_name == "START")
    a = g.world.spawn("ANT_ROOF", 300, 76)
    b = g.world.spawn("ANT_ROOF", 340, 76)
    b.set_aistate(2)
    hp = b.hp
    b.do_damage(5, a, b.x, b.y, 0, 0)
    assert b.hp == hp


def test_exit_needs_touch_and_action_key():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "NEXT_LEVEL"))
    ex = g.world.find_type("NEXT_LEVEL")
    place_player(g, ex.x, ex.y)
    idle(g, 2)
    assert not g.world.globals.get("level_complete")
    idle(g, 1, y=1)
    assert g.world.globals.get("level_complete")


def test_next_level_top_shifts_the_random_table_by_80_each_tick():
    from abuse_remake.engine.behaviors.logic import next_level_top_ai
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "NEXT_LEVEL_TOP"))
    top = g.world.find_type("NEXT_LEVEL_TOP")
    before = g.world.rng.rand_on
    next_level_top_ai(top)
    assert g.world.rng.rand_on == (before + 80) & 0xFFFF


def test_full_level_runs_deterministically_per_seed():
    def run(seed):
        g = Game(seed=seed)
        for i in range(400):
            p = g.player
            g.step(Inputs(x=1 if (i // 40) % 3 != 2 else -1, y=-1 if i % 25 == 0 else 0,
                          b2=1 if i % 3 == 0 else 0, pointer_x=p.x + 100, pointer_y=p.y - 10))
        return g.state_hash()
    assert run(11) == run(11)
    assert run(11) != run(12)  # the seed reaches the enemies through the random table


# --- review follow-ups: ant AI, random draws, walls, doors, turret, boulder rocks -------------

from abuse_remake.engine.cmath import RAND_TABLE  # noqa: E402


def lone(type_name, seed=0):
    g = Game(seed=seed, strict=False, object_filter=lambda o: o.type_name == "START")
    o = g.world.spawn(type_name, g.player.x + 60, g.player.y)
    return g, o


def test_hanging_ant_waits_until_the_player_passes_below_within_130_px():
    from abuse_remake.engine.behaviors.enemies import ANT_FALL_DOWN, ANT_HANGING, ant_ai
    g, ant = lone("ANT_ROOF")
    ant.set_aistate(ANT_HANGING)
    ant.lvars["hide_flag"] = 0
    ant.y = g.player.y + 50  # player above the ant: keep hanging
    ant_ai(ant)
    assert ant.aistate == ANT_HANGING and ant.targetable_on == 0
    ant.y = g.player.y - 80
    ant.x = g.player.x + 200  # below-left but too far
    ant_ai(ant)
    assert ant.aistate == ANT_HANGING
    ant.x = g.player.x + 100
    ant_ai(ant)
    assert ant.aistate == ANT_FALL_DOWN and ant.state == "fall_start" and ant.targetable_on == 1


def test_hanging_ant_draws_one_random_number_per_tick():
    from abuse_remake.engine.behaviors.enemies import ANT_HANGING, ant_ai
    g, ant = lone("ANT_ROOF", seed=9)
    ant.set_aistate(ANT_HANGING)
    ant.y = g.player.y + 50
    rng = g.world.rng
    start = rng.rand_on
    for _ in range(5):
        ant_ai(ant)  # (jrand()%128)==0 picks the scare sound (ant.c:178)
    assert rng.rand_on == (start + 5) & 0xFFFF


def test_switch_once_draws_a_random_number_from_its_debug_print():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "SWITCH_ONCE"))
    sw = g.world.find_type("SWITCH_ONCE")
    place_player(g, sw.x + 5, sw.y)
    idle(g, 2)
    from abuse_remake.engine.behaviors.logic import switch_once_ai
    g.view.y_suggestion = 1  # holding the action key
    start = g.world.rng.rand_on
    switch_once_ai(sw)
    assert sw.aistate == 1 and g.world.rng.rand_on == (start + 1) & 0xFFFF
    switch_once_ai(sw)  # already on: no further draws
    assert g.world.rng.rand_on == (start + 1) & 0xFFFF


def test_force_field_shifts_the_random_table_every_tick():
    from abuse_remake.engine.behaviors.world_objects import ff_ai
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "FORCE_FIELD"))
    ff = g.world.find_type("FORCE_FIELD")
    rng = g.world.rng
    start = rng.rand_on
    ff_ai(ff)  # (shift_rand_table (random 80)): draw one, then add it to rand_on
    assert rng.rand_on == (start + 1 + RAND_TABLE[start & 1023] % 80) & 0xFFFF


def test_bounce_move_returns_nil_on_landing_and_t_in_the_air():
    from abuse_remake.engine.behaviors.world_objects import small_rock_ai
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name == "START")
    tiles = g.world.tiles

    def empty(bx, by):
        return not tiles.segments.get(tiles.get(bx, by))

    bx, by = next((bx, by) for by in range(tiles.height - 12) for bx in range(1, tiles.width - 1)
                  if all(empty(bx + dx, by + dy) for dx in (-1, 0, 1) for dy in range(8)))
    rock = g.world.spawn("SMALL_BOLDER", bx * 30 + 15, by * 15 + 20)
    rock.xvel, rock.yvel = 0, 0
    results = []
    for _ in range(60):
        r = small_rock_ai(rock)
        results.append(r)
        if not r:
            break
    assert results[0] is True and results[-1] is False and len(results) > 3  # flies, then goes on landing


def test_linked_wall_ignores_damage_until_its_signal_then_explodes():
    from abuse_remake.engine.behaviors.world_objects import hwall_ai
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "HIDDEN_WALL1"))
    w = g.world.find_type("HIDDEN_WALL1")
    signal = g.world.create("GATE_AND", 0, 0)
    w.objs[:] = [signal]
    signal.aistate = 0
    hp = w.hp
    w.do_damage(5, None, w.x, w.y, 0, 0)
    assert w.hp == hp  # hwall_damage: not activated, no damage
    assert hwall_ai(w) is True
    signal.aistate = 1
    assert hwall_ai(w) is False  # signalled: it explodes even at full health


def test_switch_door_follows_its_signal():
    from abuse_remake.engine.behaviors.world_objects import sdoor_ai
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "SWITCH_DOOR"))
    door = g.world.find_type("SWITCH_DOOR")
    signal = g.world.create("GATE_AND", 0, 0)
    door.objs[:] = [signal]
    door.set_aistate(0)
    signal.aistate = 1
    sdoor_ai(door)
    assert door.aistate == 1 and door.state == "running"  # opening
    for _ in range(10):
        sdoor_ai(door)
    assert door.aistate == 2 and door.state == "blocking"  # open
    signal.aistate = 0
    sdoor_ai(door)
    assert door.aistate == 3  # closing
    for _ in range(10):
        sdoor_ai(door)
    assert door.aistate == 0 and door.state == "stopped"


def test_active_turret_fires_every_five_ticks_and_slower_at_turns():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "SPRAY_GUN"))
    gun = g.world.find_type("SPRAY_GUN")
    gun.objs.clear()  # unlinked: always activated
    place_player(g, gun.x - 60, gun.y + 40)
    fired = []
    for t in range(40):
        idle(g)
        if any(e.kind == "sound" and e.data["name"] == "ZAP_SND" for e in g.world.events):
            fired.append(t)
    gaps = [b - a for a, b in zip(fired, fired[1:], strict=False)]
    # state_time > 4 with the timer reset each shot: every 5 ticks; turning round adds 1 or 2
    assert fired and set(gaps) <= {5, 6, 7} and gaps.count(5) >= 2


def test_crack_releases_an_ant_when_the_player_comes_near():
    g = Game(seed=0, strict=False, object_filter=lambda o: o.type_name in ("START", "ANT_CRACK"))
    crack = g.world.find_type("ANT_CRACK")
    crack.objs.clear()
    before = sum(1 for o in g.world.objects if o.ctype.name == "ANT_ROOF")
    place_player(g, crack.x + 30, crack.y)
    idle(g, 8)
    after = sum(1 for o in g.world.objects if o.ctype.name == "ANT_ROOF")
    assert after > before
