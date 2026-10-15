"""Horde 2 (Remastered design): arenas, a mixed enemy roster, a boss every fifth wave, upgrade
cards between waves, and scoring with combos and local high scores. Deterministic per seed."""

import json

import pygame
import pytest

from abuse_remake.engine.game import Game
from abuse_remake.engine.horde import (
    ARENAS,
    BOSS_EVERY,
    CARDS,
    COMBO_TICKS,
    POINTS,
    roster,
    wave_size,
)
from abuse_remake.engine.view import Inputs


def idle(g, n=1, **kw):
    for _ in range(n):
        p = g.player
        g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20, **kw))


def clear_wave(g):
    st = g.horde.state
    for o in g.world.objects:
        if o.uid in st["alive"]:
            o.set_hp(0)
    idle(g, 2)


def in_tick(g, fn):
    """Run one tick with ``fn()`` done inside it, after the world's own step (Horde reads that
    tick's damage events)."""
    w = g.world
    real = w.step

    def step():
        real()
        fn()

    w.step = step
    try:
        idle(g)
    finally:
        del w.step


def player_kill(g, o):
    """Kill ``o`` with the player's damage, in a tick of its own, so the kill scores."""
    def kill():
        o.do_damage(max(1, o.hp), g.player, o.x, o.y, 0, 0)
        if o.hp > 0:
            o.set_hp(0)
    in_tick(g, kill)


def until(g, cond, limit=600):
    for _ in range(limit):
        if cond():
            return True
        idle(g)
    return cond()


# --- arenas --------------------------------------------------------------------------------------
@pytest.mark.parametrize("key", sorted(ARENAS))
def test_each_arena_starts_the_player_on_its_floor(key):
    a = ARENAS[key]
    g = Game(seed=1, horde=True, arena=key)
    assert g.level == a.level and g.horde.state["arena"] == key
    assert {o.ctype.name for o in g.world.objects} <= {"START", "DARNEL", "MGUN_TOP"}
    idle(g, 10)
    p = g.player
    assert a.x1 < p.x < a.x2 and abs(p.y - a.floor_y) <= 15 and not g.player_dead  # on the floor


def quiet_arena(key):
    """An arena with no waves (only the map), the player settled on its floor; and that floor."""
    g = Game(seed=1, horde=True, arena=key)
    g.horde.state["over"] = True
    idle(g, 12)
    return g, g.player.y


@pytest.mark.parametrize("key", sorted(ARENAS))
def test_every_spot_on_an_arena_floor_holds_the_player(key):
    """Level 2's arenas had drops at their ends into rooms with no way back up."""
    a = ARENAS[key]
    g, floor = quiet_arena(key)
    snap = g.snapshot()
    for x in range(a.x1 + 8, a.x2 - 7, 15):
        g.restore(snap)
        p = g.player
        p.x = p.last_x = x
        p.y = p.last_y = floor - 20
        idle(g, 20)
        assert g.player.y == floor, (key, x, g.player.y)


@pytest.mark.parametrize("key", sorted(ARENAS))
@pytest.mark.parametrize("power", ["none", "flight", "speed"])
def test_nobody_leaves_an_arena_by_walking_jumping_dashing_or_flying(key, power):
    from abuse_remake.engine.behaviors.player import FAST_POWER, FLY_POWER

    a = ARENAS[key]
    g, floor = quiet_arena(key)
    g.player.lvars["special_power"] = {"none": 0, "flight": FLY_POWER, "speed": FAST_POWER}[power]
    held = int(power != "none")
    for move in (dict(x=-1), dict(x=1), dict(x=-1, y=-1), dict(x=1, y=-1)):
        for t in range(110):
            if t % 20 == 0:
                g.remastered.request_dash(move["x"])
            idle(g, b1=held, **move)
            p = g.player
            assert a.x1 - 30 <= p.x <= a.x2 + 30 and p.y <= floor + 1, (key, power, move, p.x, p.y)
        g.player.lvars["special_power"] = 0
        idle(g, 30, x=-move["x"])  # flight can perch on a ledge: walking away drops back down
        idle(g, 40)
        assert g.player.y == floor, (key, power, move, g.player.x, g.player.y)  # back on the floor
        g.player.lvars["special_power"] = {"none": 0, "flight": FLY_POWER, "speed": FAST_POWER}[power]


@pytest.mark.parametrize("key", sorted(ARENAS))
def test_arena_walls_are_built_from_the_levels_own_tiles_and_only_in_horde(key):
    from abuse_remake.engine.horde import SEALS

    a = ARENAS[key]
    horde = Game(seed=1, horde=True, arena=key).world.tiles
    plain = Game(seed=1, level=a.level, remastered=True).world.tiles
    changed = {(x, y) for y in range(plain.height) for x in range(plain.width) if horde.get(x, y) != plain.get(x, y)}
    sealed = {(x, y) for x1, x2, y1, y2, _ in SEALS[key] for y in range(y1, y2 + 1) for x in range(x1, x2 + 1)}
    assert changed and changed <= sealed  # nothing outside the seals changes
    used = set(plain.cells)
    assert all(horde.get(x, y) in used for x, y in changed)  # every new cell is a tile the level uses


@pytest.mark.parametrize("key", sorted(ARENAS))
def test_supplies_land_on_the_floor_within_reach(key):
    from abuse_remake.engine.horde import DROPS

    a = ARENAS[key]
    g, floor = quiet_arena(key)
    g.horde.state["wave"] = 6  # several drops
    g.horde._drops()
    idle(g, 40)
    drops = [o for o in g.world.objects if o.ctype.name in DROPS]
    assert len(drops) >= 3
    for o in drops:
        assert abs(o.y - floor) <= 2 and a.x1 <= o.x <= a.x2, (key, o.ctype.name, o.x, o.y, floor)


def test_the_prison_arena_is_the_original_horde_arena():
    from abuse_remake.engine.horde import ARENA_FLOOR_Y, ARENA_X1, ARENA_X2

    a = ARENAS["prison"]
    assert (a.level, a.x1, a.x2, a.floor_y) == ("level01", ARENA_X1, ARENA_X2, ARENA_FLOOR_Y)
    assert Game(seed=1, horde=True).horde.state["arena"] == "prison"  # still the default


# --- the roster ----------------------------------------------------------------------------------
def test_the_roster_grows_from_ants_to_flyers_robots_and_juggernauts():
    import random

    rng = random.Random(4)
    assert roster(1, rng) == ["ANT_ROOF"] * wave_size(1) and roster(2, rng) == ["ANT_ROOF"] * wave_size(2)
    seen = set()
    for wave in range(3, 12):
        if wave % BOSS_EVERY:
            kinds = roster(wave, rng)
            assert len(kinds) == wave_size(wave)
            seen |= set(kinds)
            assert "JUGGER" not in kinds or wave >= 6
            assert "ROB1" not in kinds or wave >= 4
    assert {"ANT_ROOF", "FLYER", "ROB1", "JUGGER"} <= seen


def test_every_fifth_wave_brings_a_boss_with_escorts():
    import random

    kinds = roster(BOSS_EVERY, random.Random(1))
    assert kinds[0] == "BOSS" and kinds.count("BOSS") == 1 and len(kinds) > 1


# --- waves, cards and the boss -------------------------------------------------------------------
def test_a_cleared_wave_offers_three_cards_and_the_next_wave_waits_for_a_choice():
    g = Game(seed=3, horde=True)
    st = g.horde.state
    assert until(g, lambda: st["wave"] == 1 and not st["to_spawn"] and st["alive"])
    clear_wave(g)
    assert st["cleared"] == 1 and len(st["cards"]) == 3 and len(set(st["cards"])) == 3
    assert set(st["cards"]) <= set(CARDS)
    idle(g, 200)
    assert st["wave"] == 1  # waits while the cards are up
    assert not g.horde.choose(5) and st["cards"]  # no such card
    assert g.horde.choose(0) and not st["cards"]
    assert until(g, lambda: st["wave"] == 2)


@pytest.mark.parametrize("card", sorted(CARDS))
def test_each_card_does_what_it_says(card):
    g = Game(seed=3, horde=True)
    st = g.horde.state
    p, v = g.player, g.view
    p.set_hp(40)
    before = (list(v.weapons), p.lvars["special_power"], g.remastered.state.get("cooldown_max"))
    st["cards"] = [card, "medkit" if card != "medkit" else "ammo", "rockets" if card != "rockets" else "ammo"]
    assert g.horde.choose(0)
    sp = p.lvars["special_power"]
    if card == "speed":
        assert sp == 1
    elif card == "flight":
        assert sp == 2
    elif card == "ultra_health":
        assert sp == 4 and p.hp > 40
    elif card == "medkit":
        assert p.hp == 100
    elif card == "ammo":
        assert v.weapons[1] >= before[0][1] + 10 and v.weapons[3] >= 5
    elif card == "rockets":
        assert v.weapons[2] >= 10
    elif card == "dash":
        assert g.remastered.state["cooldown_max"] == 14


def test_a_card_power_lasts_until_the_end_of_the_next_wave():
    g = Game(seed=3, horde=True)
    g.view.god = 1  # an idle player would not survive wave 2; this test is about timing
    st = g.horde.state
    assert until(g, lambda: st["wave"] == 1 and not st["to_spawn"] and st["alive"])
    clear_wave(g)
    st["cards"] = ["flight", "medkit", "ammo"]
    g.horde.choose(0)
    assert g.player.lvars["special_power"] == 2
    assert until(g, lambda: st["wave"] == 2 and not st["to_spawn"] and st["alive"])
    assert g.player.lvars["special_power"] == 2
    clear_wave(g)
    assert g.player.lvars["special_power"] == 0


def test_the_boss_wave_spawns_a_juggernaut_with_extra_lives():
    from abuse_remake.engine.horde import BOSS_LIFE

    g = Game(seed=2, horde=True, arena="pit")
    g.view.god = 1
    st = g.horde.state
    st["wave"] = BOSS_EVERY - 1
    st["cards"] = []
    st["break"], st["spawn_in"] = True, 1
    assert until(g, lambda: st["boss"] is not None)
    boss = next(o for o in g.world.objects if o.uid == st["boss"])
    assert boss.ctype.name == "JUGGER" and boss.lvars["stationary"] == 0
    assert boss.hp == BOSS_LIFE == 200 and st["boss_lives"] == 1 and g.horde.boss_health() == (400, 400)
    player_kill(g, boss)
    idle(g)
    assert boss.hp == BOSS_LIFE and st["boss_lives"] == 0 and st["boss"] == boss.uid  # back up
    assert g.horde.boss_health() == (200, 400)
    score = st["score"]
    player_kill(g, boss)
    idle(g)
    assert st["boss"] is None and st["kills_by"].get("BOSS") == 1 and st["score"] >= score + 2500


def test_later_bosses_have_more_lives():
    from abuse_remake.engine.horde import boss_lives

    assert [boss_lives(w) for w in (5, 10, 15)] == [2, 3, 4]


# --- score ---------------------------------------------------------------------------------------
def first_wave(seed=3):
    g = Game(seed=seed, horde=True)
    g.view.god = 1  # this test is about scoring, not survival
    st = g.horde.state
    assert until(g, lambda: st["wave"] == 1 and not st["to_spawn"] and len(st["alive"]) == 4)
    return g, st, [o for o in g.world.objects if o.uid in st["alive"]]


def test_quick_kills_build_a_combo_within_45_ticks():
    g, st, ants = first_wave()
    player_kill(g, ants[0])
    assert st["score"] == POINTS["ANT_ROOF"] and st["combo"] == 1
    player_kill(g, ants[1])  # the next tick
    assert st["combo"] == 2 and st["score"] == POINTS["ANT_ROOF"] * 3
    idle(g, COMBO_TICKS - 1)
    player_kill(g, ants[2])
    assert st["combo"] == 3  # 45 ticks after the last kill: still in the window
    idle(g, COMBO_TICKS)
    player_kill(g, ants[3])
    assert st["combo"] == 1 and st["best_combo"] == 3  # 46 ticks: the combo starts again


def test_only_the_players_kills_score():
    g, st, ants = first_wave()
    in_tick(g, lambda: ants[0].do_damage(ants[0].hp, None, ants[0].x, ants[0].y, 0, 0))
    assert ants[0].hp == 0 and st["kills"] == 1
    assert st["score"] == 0 and st["combo"] == 0  # not the player's kill: counted, not scored


@pytest.mark.parametrize("hurt", [False, True])
def test_a_clean_wave_earns_a_bonus_and_damage_withholds_it(hurt):
    g, st, ants = first_wave()
    st["wave_hp_lost"] = 0  # whatever the ants did before this test takes over
    g.view.god = 0
    if hurt:
        in_tick(g, lambda: g.player.do_damage(4, ants[0], g.player.x, g.player.y, 0, 0))
        assert st["wave_hp_lost"] > 0
    for a in ants[:-1]:
        player_kill(g, a)
    st["last_kill"] = -10 ** 6  # the last kill alone: x1
    if not hurt:
        st["wave_hp_lost"] = 0
    score = st["score"]
    player_kill(g, ants[-1])
    assert st["cleared"] == 1
    assert st["score"] - score == POINTS["ANT_ROOF"] + 200 + (0 if hurt else 300)


def test_horde_2_is_deterministic_per_seed_and_arena():
    def run(seed, arena):
        g = Game(seed=seed, horde=True, arena=arena)
        st = g.horde.state
        for i in range(500):
            if st["cards"]:
                g.horde.choose(i % 3)
            p = g.player
            g.step(Inputs(x=1 if i % 50 < 25 else -1, b2=1, pointer_x=p.x + 100 * p.direction, pointer_y=p.y - 20))
        return g.state_hash(), dict(st)

    for arena in ARENAS:
        assert run(7, arena) == run(7, arena)


# --- records and the app -------------------------------------------------------------------------
@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    return tmp_path


def test_high_scores_keep_a_top_10_per_arena_and_difficulty(home):
    from abuse_remake.game.remaster import horde_top, record_horde

    for score in (500, 2000, 100, 900, 3000, 50, 700, 1200, 800, 650, 400, 999):
        record_horde("hard", 1, 2, arena="pit", score=score)
    top = horde_top("hard", "pit")
    assert [r["score"] for r in top] == [3000, 2000, 1200, 999, 900, 800, 700, 650, 500, 400]
    out = record_horde("hard", 9, 40, arena="pit", score=2500)
    assert out["rank"] == 2 and horde_top("hard", "rooftop") == []
    assert record_horde("hard", 0, 0, arena="pit", score=10)["rank"] is None  # off the table


def make_app(*extra):
    from abuse_remake.game.app import App, parse_args

    return App(parse_args(["--frames", "1", "--no-audio", "--seed", "2", "--scale", "1", "--horde", *extra]))


def test_the_title_picks_the_arena(home):
    app = make_app()
    app.state = "title"
    seen = []
    for _ in range(len(ARENAS)):
        app.on_key(pygame.K_a)
        seen.append(app.game.horde.state["arena"])
    assert set(seen) == set(ARENAS)


def shooter(app):
    """Scripted inputs that shoot the nearest enemy (and jump when one is close)."""
    def inputs(tick):
        g = app.game
        p, st = g.player, g.horde.state
        foes = [o for o in g.world.objects if o.uid in st["alive"]]
        if not foes:
            return Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20)
        f = min(foes, key=lambda o: abs(o.x - p.x))
        return Inputs(b2=1, y=-1 if abs(f.x - p.x) < 40 else 0, pointer_x=f.x, pointer_y=f.y - 15)
    return inputs


def test_cards_are_chosen_with_1_2_3_and_the_trace_replays(home, tmp_path):
    from abuse_remake.game.human_replay import replay_human

    rec = tmp_path / "horde.jsonl"
    app = make_app("--record", str(rec), "--arena", "rooftop")
    app.scripted_inputs = shooter(app)
    app.state = "play"
    st = app.game.horde.state
    i = 0
    while not st["cards"] and i < 1500:
        app.tick(i)
        i += 1
    assert st["cards"] and st["cleared"] == 1  # wave 1 cleared through the inputs alone
    app.on_key(pygame.K_2)
    app.tick(i)
    assert not st["cards"] and app.pending_weapon is None  # 2 chose a card, not a weapon
    for k in range(100):  # the 90-tick break
        app.tick(i + 1 + k)
    assert st["wave"] == 2
    app._check("session end")
    app.trace.close()
    rows = [json.loads(x) for x in rec.read_text().splitlines()]
    assert [r["card"] for r in rows if r["kind"] == "input" and "card" in r] == [1]
    assert rows[1]["arena"] == "rooftop"
    out = replay_human(rec)
    assert out["checks"] == 1 and out["mismatches"] == 0
    assert st["score"] > 0  # wave 1 was cleared with real laser shots, and they score
    # a game recorded before the arenas were sealed played on other maps: refused, not mismatched
    old = rec.with_name("old.jsonl")
    old.write_text("\n".join(json.dumps({**r, "horde_version": 2} if r["kind"] == "new_game" else r)
                             for r in rows) + "\n")
    with pytest.raises(SystemExit, match="another version of Horde"):
        replay_human(old)


def test_every_flyer_release_height_is_clear_in_every_arena():
    """Flyers are released fly to fly + 19 px above the floor: none of those heights, at either
    end of any arena, may start a flyer wedged in the map."""
    for key, a in ARENAS.items():
        g = Game(seed=1, horde=True, arena=key)
        w = g.world
        for kind in ("FLYER", "GREEN_FLYER"):
            for x in (a.x1 + 20, a.x2 - 20):
                for r in range(20):
                    o = w.spawn(kind, x, a.floor_y - a.fly - r)
                    o.set_state("running")
                    _, _, up = o.try_move(o.x, o.y, 0, -1, 3)
                    _, _, down = o.try_move(o.x, o.y, 0, 1, 3)
                    _, left, _ = o.try_move(o.x, o.y, -1, 0, 3)
                    _, right, _ = o.try_move(o.x, o.y, 1, 0, 3)
                    assert up == -1 and down == 1 and (left == -1 or right == 1), (key, kind, x, r)
                    w.remove_object(o)


def test_the_horde_over_screen_shows_the_score_and_the_table(home):
    app = make_app("--arena", "pit")
    app.state = "play"
    st = app.game.horde.state
    st.update(cleared=6, kills=31, score=4321, best_combo=4)
    app.game.player.set_hp(0)
    app.game.player.set_aistate(3)
    app.tick(0)
    assert app.state == "horde_over" and app.finish["rank"] == 1
    lines = app.horde_over_lines()
    assert any("4321" in line for line in lines) and any("x4" in line for line in lines)
    app.draw()


def test_the_dash_card_really_shortens_the_dash_and_stops_at_a_safe_floor():
    from abuse_remake.engine.horde import DASH_FLOOR
    from abuse_remake.engine.remastered import DASH_IFRAMES

    g = Game(seed=3, horde=True)
    idle(g, 3)
    st = g.horde.state
    for expected in (14, 10, 10):
        st["cards"] = ["dash", "medkit", "ammo"]
        g.horde.choose(0)
        assert g.remastered.state["cooldown_max"] == expected
    assert DASH_FLOOR > DASH_IFRAMES and "dash" not in g.horde.card_pool()
    assert g.remastered.request_dash(1)
    ready = None
    for t in range(1, 20):
        idle(g)
        if g.remastered.can_dash():
            ready = t
            break
    assert ready == DASH_FLOOR
    vulnerable = 0
    g2 = Game(seed=3, horde=True)
    idle(g2, 3)
    g2.remastered.state["cooldown_max"] = DASH_FLOOR
    for _ in range(60):  # dash whenever possible: there are still ticks it can be hurt in
        g2.remastered.request_dash(1)
        idle(g2)
        vulnerable += g2.world.globals["player_iframes"] == 0
    assert vulnerable >= 10


def test_ultra_health_ends_with_its_wave_and_full_health_never_lowers_health():
    g = Game(seed=3, horde=True)
    g.view.god = 1
    st = g.horde.state
    assert until(g, lambda: st["wave"] == 1 and not st["to_spawn"] and st["alive"])
    clear_wave(g)
    st["cards"] = ["ultra_health", "medkit", "ammo"]
    g.horde.choose(0)
    g.player.set_hp(170)
    st["cards"] = ["medkit", "ammo", "rockets"]
    g.horde.choose(0)
    assert g.player.hp == 200  # full health under the 200 cap
    st["card_power"] = 4
    assert until(g, lambda: st["wave"] == 2 and not st["to_spawn"] and st["alive"])
    clear_wave(g)
    assert g.player.lvars["special_power"] == 0 and g.player.hp == 100


@pytest.mark.parametrize("arena", sorted(ARENAS))
@pytest.mark.parametrize("kind", ["FLYER", "GREEN_FLYER", "ROB1", "JUGGER", "ANT_ROOF"])
def test_every_enemy_kind_spawns_free_in_every_arena_and_can_be_killed(arena, kind):
    g = Game(seed=5, horde=True, arena=arena)
    g.view.god = 1
    st = g.horde.state
    st["wave"] = 7
    g.horde._spawn(kind)
    o = next(x for x in g.world.objects if x.uid == st["alive"][-1])
    assert o.ctype.name == ("JUGGER" if kind == "JUGGER" else kind)
    idle(g, 15)
    _, xv, _ = o.try_move(o.x, o.y, 4 * o.direction, 0, 3)
    _, _, yv = o.try_move(o.x, o.y, 0, -4, 3)
    assert xv or yv, (arena, kind, o.x, o.y)  # not stuck inside the walls
    a = ARENAS[arena]
    assert a.x1 - 60 <= o.x <= a.x2 + 60
    score = st["score"]
    player_kill(g, o)
    idle(g, 2)
    assert st["kills_by"].get(kind) == 1 and st["score"] > score


def test_the_upgrade_message_reaches_the_screen(home):
    app = make_app()
    app.state = "play"
    st = app.game.horde.state
    st["cards"] = ["rockets", "medkit", "ammo"]
    app.on_key(pygame.K_1)
    app.tick(0)
    assert any("Rocket launcher" in m[0] for m in app.hud.messages)


def test_cards_can_be_chosen_with_a_gamepad_or_the_mouse(home):
    app = make_app()
    app.state = "play"
    st = app.game.horde.state
    st["cards"] = ["rockets", "medkit", "ammo"]
    pygame.event.post(pygame.event.Event(pygame.JOYBUTTONDOWN, button=1, joy=0, instance_id=0))
    app.args.frames = 3  # each scripted frame is half a tick
    app.run()
    assert app.pending_card is None and not st["cards"]  # B chose card 2 during that frame
    app = make_app()
    app.state = "play"
    st = app.game.horde.state
    st["cards"] = ["rockets", "medkit", "ammo"]
    app.draw()
    r = app.hud.card_rects[2]
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=r.center))
    app.args.frames = 3
    app.run()
    assert not st["cards"] and app.game.view.weapons[3] >= 5  # the ammo card


def test_an_unreadable_scores_file_is_moved_aside(home):
    from abuse_remake.game.remaster import horde_top, record_horde

    (home / "horde_scores.json").write_text("{not json")
    record_horde("hard", 1, 2, arena="pit", score=50)
    assert (home / "horde_scores.unreadable.json").read_text() == "{not json"
    assert horde_top("hard", "pit")[0]["score"] == 50
