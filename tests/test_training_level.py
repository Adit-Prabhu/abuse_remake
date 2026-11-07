"""The training level's objects (shareware level00) and the four original power-ups, ported for
Remastered's campaign. Each test exercises a rule from the cited Lisp or C on the real level data."""

import re

import pytest

from abuse_remake.engine import campaign
from abuse_remake.engine.behaviors import registry
from abuse_remake.engine.game import Game
from abuse_remake.engine.view import Inputs
from abuse_remake.paths import data_root

FAST_POWER, FLY_POWER, SNEAKY_POWER, HEALTH_POWER = 1, 2, 3, 4  # people.lsp enum


def training(seed=0, difficulty="hard"):
    g = Game(seed=seed, difficulty=difficulty, level="level00", remastered=True)
    idle(g, 2)  # the player's first tick moves it from JUST_START to NORMAL_PLAY
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


def open_floor(g):
    """Stand the player on the floor of the flyers' room, which is open 150 px each way."""
    place(g, 1250, 691)
    idle(g, 2)
    return g.player


# --- the level ---------------------------------------------------------------------------------
def test_the_training_level_is_playable_in_strict_mode():
    assert campaign.unported("level00") == {}
    assert campaign.playable("level00")
    g = training()
    idle(g, 200)
    assert not g.player_dead


# --- ladders (ladder.lsp:5-29) -----------------------------------------------------------------
def test_a_ladder_lets_the_player_climb_and_centres_them():
    g = training()
    top, bottom = obj(g, 151), obj(g, 185)  # the ladder's area runs from top to its link
    mid = (top.x + bottom.x) // 2
    place(g, mid + 3, bottom.y - 1)
    start_y = g.player.y
    states = []
    for _ in range(25):
        idle(g, y=-1)
        states.append(g.player.state)
    assert "climbing" in states
    assert g.player.y < start_y - 30
    assert g.player.x == mid  # latter_check_area: a climbing player is set to the middle


def test_up_outside_a_ladder_is_a_jump_not_a_climb():
    g = training()
    bottom = obj(g, 185)
    place(g, bottom.x + 60, bottom.y - 1)
    states = set()
    for _ in range(10):
        idle(g, y=-1)
        states.add(g.player.state)
    assert "climbing" not in states and g.player.lvars["in_climbing_area"] == 0


# --- lava (duong.lsp:206-227) ------------------------------------------------------------------
def test_lava_burns_6_every_20_ticks_while_touched():
    g = training(difficulty="hard")
    lava = obj(g, 85)
    place(g, lava.x, lava.y)
    p = g.player
    lava.set_aistate(0)
    lava.set_aistate_time(20)
    hp = p.hp
    ai("lava_ai")(lava)
    assert p.hp == hp - 6  # hard: bottom_damage passes 6 through
    lava.set_aistate(0)
    lava.set_aistate_time(21)
    hp = p.hp
    ai("lava_ai")(lava)
    assert p.hp == hp


def test_lava_bubbles_hurt_nearby_at_state_time_5():
    g = training()
    lava = obj(g, 85)
    place(g, lava.x + 15, lava.y)
    p = g.player
    p.set_hp(100)
    lava.set_aistate(1)
    lava.set_aistate_time(5)
    ai("lava_ai")(lava)
    assert lava.aistate == 0 and p.hp < 100  # hurt_radius 20 at 20 damage


# --- springs (general.lsp:26-58) ---------------------------------------------------------------
def test_a_spring_adds_its_yvel_to_the_player_and_bounces():
    g = training()
    spring = obj(g, 152)
    assert spring.yvel == -20  # saved in the level
    place(g, spring.x, spring.y)
    p = g.player
    p.yvel = 0
    p.set_gravity(0)
    ai("spring_ai")(spring)
    assert p.yvel == -20 and p.state == "run_jump" and p.gravity() == 1
    assert spring.aistate == 1 and spring.state == "running"
    place(g, spring.x + 200, spring.y)
    for _ in range(4):  # the 4 bounce frames
        ai("spring_ai")(spring)
    assert spring.aistate == 0 and spring.state == "stopped"


def test_a_spring_does_nothing_when_untouched_and_a_new_one_pushes_15():
    g = training()
    spring = obj(g, 152)
    place(g, spring.x + 200, spring.y)
    ai("spring_ai")(spring)
    assert spring.aistate == 0
    made = g.world.create("SPRING", 0, 0)
    assert made.yvel == -15  # spring_cons


# --- the switch ball (general.lsp:96-109) ------------------------------------------------------
def test_shooting_the_switch_ball_turns_it_on_once():
    g = training()
    ball = obj(g, 188)
    ball.do_damage(5, g.player, ball.x, ball.y, 0, 0)
    assert ball.aistate == 1 and ball.state == "running"
    hp = ball.hp
    ball.set_aistate(7)
    ball.do_damage(5, g.player, ball.x, ball.y, 0, 0)
    assert ball.aistate == 7 and ball.hp == hp  # only a stopped ball reacts; it never loses hp


# --- training messages (general.lsp:66-94, english.lsp:226-243) --------------------------------
def test_training_messages_match_the_original_text():
    from abuse_remake.engine.behaviors.campaign_objects import TRAIN_MSGS

    text = (data_root() / "lisp" / "english.lsp").read_text(encoding="latin-1")
    table = text[text.index("(defun get_train_msg"):]
    table = table[:table.index("))")]
    original = {int(n): s for n, s in re.findall(r'^\s*\((\d+) "([^"]*)"\)', table, re.M)}
    assert TRAIN_MSGS == original and len(original) == 12


def test_a_training_message_waits_for_its_sensor_then_shows_for_100_ticks():
    g = training()
    msg = obj(g, 167)  # aitype 0, linked to a sensor
    sensor = msg.objs[0]
    sensor.set_aistate(0)
    g.world.events.clear()
    assert ai("train_ai")(msg) and msg.aistate == 0
    assert not [e for e in g.world.events if e.kind == "help"]
    sensor.set_aistate(1)
    assert ai("train_ai")(msg) and msg.aistate == 1
    helps = [e for e in g.world.events if e.kind == "help"]
    assert helps[-1].data["text"] == "Aim gun with mouse, fire with left mouse button"
    calls = 1
    while ai("train_ai")(msg):
        calls += 1
    assert calls == 100 and msg.aistate == 100  # aistates 1..99 show it, 100 deletes the object


# --- flyers (flyer.lsp, jugger.lsp:200-222, ant.lsp:63-104, guns.lsp:166-172) ------------------
def test_a_flyer_waits_unhittable_until_switched_on():
    g = training()
    who = obj(g, 196)
    sensor = who.objs[0]
    sensor.set_aistate(0)
    assert ai("flyer_ai")(who)
    assert who.state == "stopped" and who.targetable_on == 0
    who.do_damage(10, g.player, who.x, who.y, 0, 0)
    assert who.hp == 20  # a stopped flyer ignores damage
    sensor.set_aistate(1)
    calls = 0
    while who.aistate == 0:
        ai("flyer_ai")(who)
        calls += 1
    assert calls == 3 and who.state == "running" and who.targetable_on == 1  # after its 3 frames


def test_a_flyer_hunts_the_player_and_fires_straight_rockets():
    g = training(seed=3)
    p = open_floor(g)
    who = g.world.spawn("WHO", p.x + 90, p.y - 60)  # flyer_cons: aitype 9, 2-shot bursts
    assert (who.aitype, who.lvars["fire_delay"], who.lvars["burst_total"]) == (9, 20, 2)
    who.set_aistate(1)
    who.set_state("running")
    rockets = []
    for _ in range(40):
        idle(g)
        rockets += [e for e in g.world.events if e.kind == "shot" and e.data["weapon"] == 9]
    assert rockets
    assert any(o.ctype.name in ("STRAIT_ROCKET", "EG_EXPLO") for o in g.world.objects) or p.hp < 100


def test_a_straight_rocket_flies_at_its_angle_and_explodes_on_a_hit():
    g = training(difficulty="hard")
    p = open_floor(g)
    r = g.world.spawn("STRAIT_ROCKET", p.x - 60, p.y - 15)
    r.set_aistate(0)  # flying right, at the player
    x0 = r.x
    assert ai("strait_rocket_ai")(r)
    assert r.x - x0 == 17  # hard: 17 px per tick
    hp = p.hp
    for _ in range(6):
        if not ai("strait_rocket_ai")(r):
            break
    else:
        pytest.fail("the rocket never hit")
    assert p.hp < hp
    assert any(o.ctype.name == "EG_EXPLO" for o in g.world.objects)


def test_flyers_shrug_off_other_flyers_fire_and_die_in_an_explosion():
    g = training()
    p = g.player
    flyer = g.world.spawn("FLYER", p.x + 300, p.y - 80)
    flyer.set_aistate(1)
    flyer.set_state("running")
    other = g.world.spawn("FLYER", p.x + 340, p.y - 80)
    shot = g.world.spawn("STRAIT_ROCKET", flyer.x, flyer.y)
    shot.add_object(other)
    flyer.do_damage(10, shot, flyer.x, flyer.y, 0, 0)
    assert flyer.hp == 20
    kills = g.view.kills
    flyer.do_damage(20, p, flyer.x, flyer.y, 0, 0)
    assert flyer.state == "flinch_up" and flyer.lvars["smoke_time"] == 30 and flyer.hp == 0
    assert not ai("flyer_ai")(flyer)  # dead: explodes and is deleted
    assert g.view.kills == kills + 1
    assert sum(o.ctype.name == "EXPLODE1" for o in g.world.objects) == 3


# --- the power-ups (powerup.lsp:39-108, people.lsp:49-66, cop.c:422-490) -----------------------
@pytest.mark.parametrize("kind,power", [("POWER_FAST", FAST_POWER), ("POWER_FLY", FLY_POWER),
                                        ("POWER_SNEAKY", SNEAKY_POWER), ("POWER_HEALTH", HEALTH_POWER)])
def test_touching_a_power_up_gives_its_power_and_removes_it(kind, power):
    g = training()
    p = g.player
    item = g.world.spawn(kind, p.x + 200, p.y)
    idle(g)
    assert p.lvars["special_power"] == 0 and not item.deleted  # not touching yet
    item.x, item.y = p.x, p.y
    idle(g)
    assert p.lvars["special_power"] == power and item.deleted


def test_speed_flashes_the_view_white():
    g = training()
    p = g.player
    item = g.world.spawn("POWER_FAST", p.x, p.y)
    assert ai("fast_ai")(item) is False
    assert g.view.draw_solid == 0xFFFFFF  # make_view_solid (find_rgb 255 255 255)


def test_ultra_health_raises_the_cap_to_200_and_heals():
    g = training(difficulty="easy")
    p = g.player
    p.set_hp(100)
    item = g.world.spawn("POWER_HEALTH", p.x, p.y)
    assert ai("health_power_ai")(item) is False
    assert p.lvars["special_power"] == HEALTH_POWER and p.hp == 200  # easy: the full 100


def test_held_special_key_uses_the_power():
    def run(power, ticks=12, special=1):
        g = training(seed=1)
        p = open_floor(g)
        p.lvars["special_power"] = power
        x0, y0 = p.x, p.y
        for _ in range(ticks):
            g.step(Inputs(x=1, b1=special, pointer_x=p.x + 100, pointer_y=p.y - 20))
        return g, p.x - x0, p.y - y0

    _, plain_dx, _ = run(0)
    _, fast_dx, _ = run(FAST_POWER)
    assert fast_dx > plain_dx + 20  # the fast power moves the player twice per tick
    g, _, fly_dy = run(FLY_POWER)
    assert fly_dy < -20 and any(o.ctype.name == "CLOUD" for o in g.world.objects)
    g, _, _ = run(SNEAKY_POWER, ticks=20)
    assert g.player.lvars["used_special_power"] == 15  # fully faded after 15 ticks
    g.step(Inputs(pointer_x=g.player.x + 100, pointer_y=g.player.y - 20))
    assert g.player.lvars["used_special_power"] == 14  # and fades back in when released


# --- drawing and the HUD (presentation; cop.c:758-878, game.c:724-729) -------------------------
@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    return tmp_path


def make_app(*extra):
    from abuse_remake.game.app import App, parse_args

    return App(parse_args(["--frames", "1", "--no-audio", "--seed", "1", "--scale", "1", "--level", "level00", *extra]))


def test_powered_players_are_drawn_from_their_power_sequences_and_fade_when_invisible(home):
    from abuse_remake.game.render import sneaky_alpha

    app = make_app()
    p = app.game.player
    p.set_state("running")
    plain = app.renderer._player_figure(p)
    p.lvars["special_power"] = FAST_POWER
    assert app.renderer._player_figure(p) is p.ctype.sequences["fast_running"][p.current_frame]
    p.lvars["special_power"] = FLY_POWER
    assert app.renderer._player_figure(p) is p.ctype.sequences["fly_running"][p.current_frame]
    p.lvars["special_power"] = 0
    assert app.renderer._player_figure(p) is plain
    p.lvars["special_power"] = SNEAKY_POWER
    alphas = []
    for used in (0, 4, 14, 15):
        p.lvars["used_special_power"] = used
        alphas.append(sneaky_alpha(p))
    assert alphas[0] == 255 and alphas[0] > alphas[1] > alphas[2] > alphas[3] > 0


def test_the_white_flash_is_drawn_once(home):
    app = make_app()
    app.game.view.draw_solid = 0xFFFFFF
    surf = app.renderer.render(1.0)
    assert surf.get_at((5, 5))[:3] == (255, 255, 255) and app.game.view.draw_solid == -1
    surf = app.renderer.render(1.0)
    assert surf.get_at((5, 5))[:3] != (255, 255, 255)


def test_training_messages_reach_the_hud_with_the_modern_keys(home):
    app = make_app()
    app.state = "play"
    app.game.world.events.clear()
    app.game.world.emit("help", number=5, text="Hold down the right mouse button to use special powers")

    real_step = app.game.step

    def step_keeping_help(*a, **kw):
        real_step(*a, **kw)
        app.game.world.emit("help", number=5, text="Hold down the right mouse button to use special powers")

    app.game.step = step_keeping_help
    app.tick(0)
    assert app.hud.help_text == "Hold down the right mouse button to use special powers  (or Shift)"
    from abuse_remake.game.hud import POWER_IMAGES

    assert all(app.sprites.image("art/misc.spe", name) is not None for name in POWER_IMAGES.values())
    app.game.player.lvars["special_power"] = HEALTH_POWER
    app.draw()  # the power icon and help line draw without error


def test_strict_mode_refuses_to_spawn_an_object_with_missing_behaviour():
    g = training()
    w = g.world
    silent = next(t for t in sorted(w.types) if [m for m in w.missing_behaviours(t) if not m.startswith("user_fun=")])
    with pytest.raises(NotImplementedError):
        w.spawn(silent, g.player.x, g.player.y)
    only_user_fun = next(t for t in sorted(w.types)
                         if w.missing_behaviours(t) and all(m.startswith("user_fun=") for m in w.missing_behaviours(t)))
    w.spawn(only_user_fun, g.player.x, g.player.y)  # only explicit calls reach a user_fun
    loose = Game(level="level00", remastered=True, strict=False)
    loose.world.spawn(silent, 0, 0)  # development and test worlds may still build anything


def test_remastered_places_the_missing_power_ups_in_the_training_level_not_level_1():
    from abuse_remake.engine.campaign import EXTRA_OBJECTS

    def extras(g):
        return sorted((o.ctype.name, o.x, o.y) for o in g.world.objects
                      if o.ctype.name in ("POWER_FLY", "POWER_SNEAKY", "POWER_HEALTH"))

    assert extras(Game(level="level00", remastered=True)) == sorted(EXTRA_OBJECTS["level00"])
    assert {k for k, _, _ in EXTRA_OBJECTS["level00"]} == {"POWER_FLY", "POWER_SNEAKY", "POWER_HEALTH"}
    assert extras(Game(level="level01", remastered=True)) == []  # Level 1 keeps its own objects


# --- review follow-ups: pinned flyer, rocket and lava timing -----------------------------------
def frozen_flyer(g, monkeypatch, dx=100, dy=-60):
    """A flyer that stays put, always sees the player and never jitters, so the firing logic can
    be read tick by tick."""
    import abuse_remake.engine.behaviors.campaign_objects as co

    monkeypatch.setattr(co, "bounce_move", lambda *a, **k: True)
    monkeypatch.setattr(co, "can_see", lambda *a: True)
    monkeypatch.setattr(co, "random", lambda o, n: 1)  # (random 5) is never 0
    shots = []
    monkeypatch.setattr(co, "fire_object",
                        lambda o, kind, x, y, angle, target: shots.append((g.frames, kind, x, y, angle)))
    p = open_floor(g)
    f = g.world.spawn("FLYER", p.x + dx, p.y + dy)
    f.set_aistate(1)
    f.set_state("running")
    return f, shots


def test_a_flyer_fires_one_rocket_then_bursts_of_burst_total(monkeypatch):
    g = training()
    f, shots = frozen_flyer(g, monkeypatch)
    for _ in range(60):
        ai("flyer_ai")(f)
        g.frames += 1  # a tick counter for the shots; the world itself is not stepped
    ticks = [t for t, *_ in shots]
    # flyer.lsp:73-96: counters start at 0, so the first burst is one rocket; then fire_delay+1
    # ticks to the next burst of burst_total rockets, burst_delay+1 ticks apart
    fd, bd = f.lvars["fire_delay"], f.lvars["burst_delay"]
    first = ticks[0]
    assert ticks[:4] == [first, first + fd + 1, first + fd + 1 + bd + 1, first + 2 * (fd + 1) + bd + 1]
    assert all(kind == 9 for _, kind, *_ in shots)


def test_a_flyer_aims_where_the_player_will_be_and_only_within_150_px(monkeypatch):
    from abuse_remake.engine.behaviors.lispfns import atan2

    g = training()
    f, shots = frozen_flyer(g, monkeypatch, dx=120)
    p = g.player
    p.xvel, p.yvel = 3, -2
    ai("flyer_ai")(f)
    _, _, firex, firey, angle = shots[0]
    assert (firex, firey) == (f.x + f.direction * 10, f.y)
    assert angle == atan2(firey - (p.y - 15 + p.yvel * 2), (p.x + p.xvel * 4) - firex)
    for dx, fires in ((149, True), (150, False)):  # (< (distx) 150)
        g2 = training()
        f2, shots2 = frozen_flyer(g2, monkeypatch, dx=dx)
        ai("flyer_ai")(f2)
        assert bool(shots2) is fires, dx


def test_a_flyer_holds_fire_without_a_clear_line(monkeypatch):
    import abuse_remake.engine.behaviors.campaign_objects as co

    for blocked in (0, 1):  # the barrel's own line, then the line to the player (flyer.lsp:86)
        g = training()
        f, shots = frozen_flyer(g, monkeypatch)
        calls = []

        def see(*args, blocked=blocked, calls=calls):
            calls.append(args)
            return len(calls) - 1 != blocked

        monkeypatch.setattr(co, "can_see", see)
        ai("flyer_ai")(f)
        assert shots == [] and len(calls) == blocked + 1


@pytest.mark.parametrize("dy,change", [(-200, 1), (-60, 0), (0, -1)])
def test_a_flyer_holds_between_50_and_70_px_above_the_player(monkeypatch, dy, change):
    g = training()
    f, _ = frozen_flyer(g, monkeypatch, dy=dy)
    f.yvel = 0
    ai("flyer_ai")(f)
    assert f.yvel == change


def test_a_straight_rocket_explodes_in_order_and_hurts_around_20_px_below(monkeypatch):
    import abuse_remake.engine.behaviors.campaign_objects as co
    from abuse_remake.engine.cmath import JRand

    g = training(difficulty="hard")
    p = open_floor(g)
    calls = []
    monkeypatch.setattr(co, "hurt_radius", lambda o, *args: calls.append(args))
    r = g.world.spawn("STRAIT_ROCKET", p.x - 20, p.y - 15)
    r.set_aistate(0)
    rng = JRand(0)
    rng.rand_on = g.world.rng.rand_on
    before = len(g.world.objects)
    assert ai("strait_rocket_ai")(r) is False  # hits the player this tick
    made = [(o.ctype.name, o.aitype, o.x, o.y) for o in g.world.objects[before:] if o.ctype.name.startswith("EXPLODE")]
    expected = []
    for name, sign, aitype in (("EXPLODE3", 1, 0), ("EXPLODE2", 1, 2), ("EXPLODE3", -1, 1), ("EXPLODE3", -1, 2)):
        ex = r.x + sign * rng.jrandom(5)
        ey = r.y + sign * rng.jrandom(5)
        expected.append((name, aitype, ex, ey))
    assert sorted(made) == sorted(expected)  # x before y, in ant.lsp:77-80's order
    assert calls == [(r.x, r.y + 20, 25, 15, None, 10)]


def test_lava_burns_every_20_ticks_through_the_engines_own_timer():
    g = training(difficulty="hard")
    lava = obj(g, 85)
    p = g.player
    p.set_hp(200)
    from abuse_remake.engine.behaviors.lispfns import set_aistate

    burns, changes = [], []
    for t in range(80):
        p.x, p.y = lava.x, lava.y
        if t == 30 and lava.aistate == 0:
            set_aistate(lava, 1)  # start a bubble, as a 1-in-100 draw would
            changes.append(t - 1)  # the timer restarts as from a change on the tick before
        before = lava.aistate
        hp = p.hp
        lava.decide()
        if lava.aistate != before:  # a bubble starting or ending restarts the timer (decide)
            changes.append(t)
        if hp - p.hp == 6:
            burns.append(t)
    gaps = [b - a for a, b in zip(burns, burns[1:], strict=False) if not any(a <= c < b for c in changes)]
    assert burns and gaps and all(gap == 20 for gap in gaps)
    assert changes and all(c + 1 in burns for c in changes)  # each restart burns on the next tick


def test_toward_and_facing():
    from abuse_remake.engine.behaviors.lispfns import facing, toward

    g = training()
    w = g.world.spawn("WHO", g.player.x + 50, g.player.y)
    assert toward(w) == -1
    w.x = g.player.x - 50
    assert toward(w) == 1
    w.direction = -1
    assert facing(w) == -1
