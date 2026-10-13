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
