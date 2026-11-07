"""Level 2's objects (shareware level02), ported for Remastered's campaign. Each test exercises a
rule from the cited Lisp on the real level data."""

import pytest

from abuse_remake.engine import campaign
from abuse_remake.engine.behaviors import registry
from abuse_remake.engine.game import Game
from abuse_remake.engine.view import Inputs


def level2(seed=0, difficulty="hard"):
    g = Game(seed=seed, difficulty=difficulty, level="level02", remastered=True)
    idle(g, 2)
    return g


def idle(g, ticks=1, **kw):
    for _ in range(ticks):
        p = g.player
        g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20, **kw))


def obj(g, level_index):
    return next(o for o in g.world.objects if o.level_index == level_index)


def place(g, x, y):
    p = g.player
    p.x, p.y, p.last_x, p.last_y = x, y, x, y
    g.view.last_x, g.view.last_y = x, y


def ai(name):
    return registry()[name]


def test_level_2_is_playable_in_strict_mode():
    assert campaign.unported("level02") == {}
    assert campaign.playable("level02")
    assert campaign.exit_result("level01", 2) == "open"  # Level 1 now leads on to Level 2
    assert campaign.exit_result("level00", 2) == "open"  # and so does the training portal
    g = level2()
    idle(g, 200)


# --- blocks (duong.lsp:117-135) ----------------------------------------------------------------
def test_a_block_crumbles_when_its_health_runs_out():
    g = level2()
    block = obj(g, 147)
    assert ai("block_ai")(block) and block.state == "stopped"
    block.do_damage(30, g.player, block.x, block.y, 0, 0)
    assert block.hp == 0
    assert ai("block_ai")(block) and block.state == "dieing"
    frames = 0
    while ai("block_ai")(block):
        frames += 1
    assert frames == 6  # the 7-frame crumble, then the block is deleted


# --- steps (ladder.lsp:31-43) ------------------------------------------------------------------
def test_a_step_is_there_only_while_its_switch_is_on():
    g = level2()
    step = obj(g, 81)
    switch = step.objs[0]
    switch.set_aistate(0)
    ai("step_ai")(step)
    assert step.state == "running"  # "step_gone"
    switch.set_aistate(1)
    ai("step_ai")(step)
    assert step.state == "stopped"


# --- pushers (general.lsp:4-24) ----------------------------------------------------------------
def test_a_pusher_shoves_a_touching_player_by_its_speed():
    g = level2()
    pusher = obj(g, 113)
    assert pusher.aistate == 10 and pusher.direction == 1  # the saved speed
    place(g, pusher.x, pusher.y)
    x0 = g.player.x
    ai("pusher_ai")(pusher)
    assert 0 < g.player.x - x0 <= 10
    made = g.world.create("PUSHER", 0, 0)
    assert made.aistate == 4  # pusher_cons


# --- the tracking gun (guns.lsp:313-430) -------------------------------------------------------
def test_a_tracking_gun_opens_when_switched_on_turns_toward_the_player_and_fires():
    g = level2()
    gun = obj(g, 87)  # tracks 270..359, linked to a delay gate
    gate = gun.objs[0]
    gate.set_aistate(0)
    assert ai("track_ai")(gun) and gun.state == "stopped" and gun.targetable_on == 0
    gate.set_aistate(1)
    ai("track_ai")(gun)
    assert gun.state == "opening" and gun.targetable_on == 1
    place(g, gun.x + 60, gun.y + 120)  # below and to the right
    lv = gun.lvars
    angles = []
    for _ in range(40):
        ai("track_ai")(gun)
        angles.append(lv["angle"])
    fired = [o for o in g.world.objects if o.ctype.name == "ROCKET" and o.objs and o.objs[0] is gun]
    assert all(270 <= a <= 359 for a in angles)
    assert max(abs(b - a) for a, b in zip(angles, angles[1:], strict=False)) <= lv["track_speed"]
    assert fired  # aitype 3: rockets


def test_track_set_angle_keeps_the_gun_inside_its_arc():
    from abuse_remake.engine.behaviors.campaign_objects import track_set_angle

    g = level2()
    gun = obj(g, 86)  # 180..270
    gun.lvars["angle"] = 200
    track_set_angle(gun, 300)
    assert gun.lvars["angle"] == 200
    track_set_angle(gun, 250)
    assert gun.lvars["angle"] == 250


# --- the cleaner robot (jugger.lsp:103-159) ----------------------------------------------------
def test_a_cleaner_robot_waits_then_rolls_forward_and_blows_up():
    g = level2()
    rob = obj(g, 195)
    sensor = rob.objs[0]
    sensor.set_aistate(0)
    place(g, rob.x + 300, rob.y)
    assert ai("rob1_ai")(rob) and rob.aistate == 0 and rob.targetable_on == 1
    sensor.set_aistate(1)
    ai("rob1_ai")(rob)
    assert rob.aistate == 1
    x0 = rob.x
    ai("rob1_ai")(rob)
    assert rob.x in (x0 - rob.xvel, x0)  # facing left, 2 px per tick unless a wall is near
    hp = rob.hp
    before = len(g.world.objects)
    rob.do_damage(10, g.player, rob.x, rob.y, 0, 0)  # explo_damage
    assert rob.hp == hp - 10 and any(o.ctype.name == "EXPLODE6" for o in g.world.objects[before - 1:])
    rob.set_hp(0)
    ai("rob1_ai")(rob)
    assert rob.aistate == 2 and sum(o.ctype.name == "EXPLODE1" for o in g.world.objects) >= 8
    rob.set_aistate_time(3)
    assert not ai("rob1_ai")(rob)


def test_a_hidden_robot_fades_in_when_switched_on():
    g = level2()
    rob = obj(g, 326)
    assert rob.lvars["rob_hiden"] == 1
    sensor = rob.objs[0]
    sensor.set_aistate(0)
    ai("rob1_ai")(rob)
    assert rob.state == "rob_hiding" and rob.targetable_on == 0
    sensor.set_aistate(1)
    ai("rob1_ai")(rob)
    assert rob.fade_count == 15 and rob.aistate == 1
    ai("rob1_ai")(rob)
    assert rob.fade_count == 14


# --- the Juggernaut (jugger.lsp:4-90, weapons.lsp:120-132) -------------------------------------
def test_a_stationary_juggernaut_throws_a_grenade_every_so_often():
    g = level2()
    jug = obj(g, 206)  # stationary, throws after 10 ticks
    assert jug.lvars["stationary"] == 1 and jug.aitype == 10
    place(g, jug.x - 120, jug.y)
    thrown = []
    for _ in range(30):
        jug.decide()  # the AI plus the engine's state-time count
        thrown = [o for o in g.world.objects if o.ctype.name == "GRENADE"]
        if thrown:
            break
    assert len(thrown) == 1 and jug.aistate == 3
    grenade = thrown[0]
    assert grenade.xvel == 13 * jug.direction and grenade.yvel == -10  # the jug's own throw
    assert grenade.objs and grenade.objs[0] is jug and grenade.direction == jug.direction


def test_a_walking_juggernaut_heads_for_the_player():
    g = level2()
    jug = obj(g, 209)  # not stationary, linked to a sensor
    assert not jug.lvars["stationary"]
    place(g, jug.x - 200, jug.y)
    jug.objs[0].set_aistate(0)
    ai("jug_ai")(jug)
    assert jug.state == "stopped" and jug.targetable_on == 0  # off until its sensor is on
    jug.objs[0].set_aistate(1)
    ai("jug_ai")(jug)
    assert jug.state == "running" and jug.aistate == 1 and jug.direction == -1


def test_a_juggernaut_dies_in_its_own_animation_and_counts_as_a_kill():
    g = level2()
    jug = obj(g, 207)
    kills = g.view.kills
    jug.do_damage(jug.hp, g.player, jug.x, jug.y, 0, 0)
    assert jug.hp == 0
    assert ai("jug_ai")(jug) and jug.state == "dieing"
    while ai("jug_ai")(jug):
        pass
    assert g.view.kills == kills + 1


@pytest.mark.parametrize("aitype,base,yvel", [(1, 13, -4), (2, 7, -10)])
@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("draw", [0, 1])
def test_a_thrown_grenade_takes_its_creators_direction_and_speed(aitype, base, yvel, direction, draw):
    from abuse_remake.engine.behaviors.campaign_objects import grenade_ufun
    from abuse_remake.engine.cmath import RAND_TABLE

    g = level2()
    jug = obj(g, 206)
    jug.direction, jug.xvel = direction, 3
    gr = g.world.spawn("GRENADE", jug.x, jug.y - 24, aitype)
    rng = g.world.rng
    rng.rand_on = next(i for i in range(len(RAND_TABLE)) if RAND_TABLE[i] % 2 == draw)  # (random 2) gives draw
    before = rng.rand_on
    grenade_ufun(gr, jug, None)
    assert rng.rand_on == before + 1  # exactly one draw
    expected = (base if direction > 0 else -base) + draw + 3  # (+ +-base (random 2)), then + the thrower's xvel
    assert gr.direction == direction and gr.yvel == yvel and gr.xvel == expected
    assert gr.objs[0] is jug


def test_a_cleaner_robot_rolls_its_speed_each_tick_when_the_way_is_clear():
    g = level2()
    rob = obj(g, 195)
    rob.x, rob.y = 2300, 481  # the open rooftop ledge
    rob.set_aistate(1)
    rob.direction = -1
    place(g, 2500, 481)
    xs = []
    for _ in range(5):
        ai("rob1_ai")(rob)
        xs.append(rob.x)
    assert [a - b for a, b in zip(xs, xs[1:], strict=False)] == [rob.xvel] * 4 and rob.xvel == 2


def test_a_tracking_gun_turns_the_short_way_toward_the_player():
    from abuse_remake.engine.behaviors.lispfns import atan2

    g = level2()
    gun = obj(g, 87)  # arc 270..359, 10 degrees a tick
    gun.objs[0].set_aistate(1)
    gun.set_state("spinning")
    lv = gun.lvars
    lv["angle"] = 359
    lv["fire_delay_left"] = lv["continue_time_left"] = 0
    place(g, gun.x + 20, gun.y + 200)  # nearly straight below: about 275 degrees
    p = g.player
    target = atan2(gun.y - p.y + 8, p.x - gun.x)
    gaps = []
    for _ in range(12):
        ai("track_ai")(gun)
        gaps.append(abs(lv["angle"] - target))
    assert 270 <= target <= 280 and gaps[0] < 359 - target
    assert all(b <= a for a, b in zip(gaps, gaps[1:], strict=False)) and gaps[-1] < lv["track_speed"]


def test_track_set_angle_takes_either_order_of_its_arc():
    from abuse_remake.engine.behaviors.campaign_objects import track_set_angle

    g = level2()
    gun = obj(g, 86)
    gun.lvars["track_start_angle"], gun.lvars["track_end_angle"] = 270, 180  # start > end
    gun.lvars["angle"] = 220
    track_set_angle(gun, 300)
    assert gun.lvars["angle"] == 220
    track_set_angle(gun, 200)
    assert gun.lvars["angle"] == 200


def test_a_pusher_whose_link_is_off_leaves_the_player_alone():
    g = level2()
    pusher = obj(g, 113)
    sw = g.world.create("SWITCH", 0, 0)
    pusher.objs[:] = [sw]
    sw.set_aistate(0)
    place(g, pusher.x, pusher.y)
    x0 = g.player.x
    ai("pusher_ai")(pusher)
    assert g.player.x == x0


def test_a_stationary_juggernaut_keeps_throwing():
    g = level2()
    jug = obj(g, 206)
    place(g, jug.x - 120, jug.y)
    throws = 0
    for _ in range(80):
        before = sum(o.ctype.name == "GRENADE" for o in g.world.objects)
        jug.decide()
        throws += sum(o.ctype.name == "GRENADE" for o in g.world.objects) > before
    assert throws >= 3  # every aitype (10) ticks, plus the throw animation


def test_every_gun_in_level_2_fires_a_ported_weapon():
    from abuse_remake.engine.behaviors import weapons
    from abuse_remake.formats.level_file import load_level
    from abuse_remake.paths import level_path

    g = level2()
    guns = [o for o in load_level(level_path("level02")).live_objects() if o.type_name in ("TRACK_GUN", "SPRAY_GUN")]
    kinds = {o.vars.get("aitype", 0) for o in guns}
    assert guns and kinds == {0, 1, 3}
    p = g.player
    for kind in sorted(kinds):  # each one really fires (an unported type raises)
        shot = weapons.fire_object(g.player, kind, p.x + 30, p.y - 20, 0, None)
        assert shot is not None and not shot.deleted


def test_a_cleaner_robot_waits_at_a_wall():
    g = level2()
    rob = obj(g, 195)
    rob.x, rob.y = 2400, 481  # the rooftop ledge, rolling right toward its end wall
    rob.set_aistate(1)
    rob.direction = 1
    place(g, 2100, 481)
    xs = []
    for _ in range(200):
        ai("rob1_ai")(rob)
        xs.append(rob.x)
    assert xs[0] > 2400 and len(set(xs[-20:])) == 1  # it rolled, then stopped: no room 23 px ahead
    from abuse_remake.engine.behaviors.lispfns import can_see
    assert not can_see(rob, rob.x, rob.y, rob.x + rob.xvel + 23, rob.y, False)


def test_a_walking_juggernaut_over_nothing_steps_back_and_drops():
    g = level2()
    jug = obj(g, 209)
    jug.objs[0].set_aistate(1)
    jug.x, jug.y = 2300, 441  # 40 px above the rooftop floor: nothing 5 px below
    place(g, 2100, 481)
    jug.direction = -1
    jug.set_state("running")
    jug.set_aistate(1)
    x0, y0 = jug.x, jug.y
    ai("jug_ai")(jug)
    assert jug.x == x0 and jug.y == y0 + 10  # put back where it was, then try_move 0 10


def test_a_slow_tracking_gun_fires_even_when_it_cannot_reach_the_player(monkeypatch):
    import abuse_remake.engine.behaviors.campaign_objects as co

    g = level2()
    gun = obj(g, 87)  # arc 270..359
    gun.objs[0].set_aistate(1)
    gun.set_state("spinning")
    lv = gun.lvars
    lv["track_speed"] = 1
    lv["angle"] = 359
    lv["fire_delay_left"] = lv["continue_time_left"] = 0
    place(g, gun.x - 200, gun.y + 40)  # down to the left: outside the arc
    shots = []
    monkeypatch.setattr(co, "fire_object", lambda *a: shots.append(a))
    ai("track_ai")(gun)
    assert shots and lv["angle"] in (358, 359)  # angle_add is capped at 1 < 5: it fires anyway


def test_remastered_places_the_missing_power_ups_in_level_2():
    from abuse_remake.engine.campaign import EXTRA_OBJECTS

    g = Game(level="level02", remastered=True)
    placed = sorted((o.ctype.name, o.x, o.y) for o in g.world.objects
                    if o.ctype.name in ("POWER_FLY", "POWER_SNEAKY", "POWER_HEALTH"))
    assert placed == sorted(EXTRA_OBJECTS["level02"])
    assert {k for k, _, _ in EXTRA_OBJECTS["level02"]} == {"POWER_FLY", "POWER_SNEAKY", "POWER_HEALTH"}
