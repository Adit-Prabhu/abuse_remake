"""Remastered mode: the dash, its invulnerability and cooldown, and that Classic is untouched;
plus headless checks of the app's Remastered features (ghost, records, stats, quick restart)."""

import pytest

from abuse_remake.agent.interface import PLAYER_ID, AbuseEpisode
from abuse_remake.engine.game import Game
from abuse_remake.engine.remastered import DASH_COOLDOWN, DASH_IFRAMES
from abuse_remake.engine.view import Inputs


def settle(g, n=5):
    p = g.player
    for _ in range(n):
        g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20))


def run_left(g, ticks, dash_at=None):
    p = g.player
    xs = []
    for i in range(ticks):
        if i == dash_at:
            assert g.remastered.request_dash(-1)
        g.step(Inputs(x=-1, pointer_x=p.x - 100, pointer_y=p.y - 20))
        xs.append(p.x)
    return xs


# --- Classic stays Classic ---------------------------------------------------------------------
def test_classic_games_and_agent_episodes_never_build_remastered_rules():
    g = Game(seed=0)
    assert g.remastered is None
    settle(g, 30)
    assert "remastered" not in g.world.globals and "player_iframes" not in g.world.globals
    ep = AbuseEpisode("level01", seed=0)
    ep.step(PLAYER_ID, "explore right")
    assert ep._game.remastered is None  # evaluations always run Classic rules


def test_remastered_without_a_dash_plays_exactly_like_classic():
    a, b = Game(seed=4), Game(seed=4, remastered=True)
    for g in (a, b):
        for i in range(120):
            p = g.player
            g.step(Inputs(x=1 if i % 40 < 30 else -1, y=-1 if i % 25 == 0 else 0, b2=int(i % 3 == 0),
                          pointer_x=p.x + 100, pointer_y=p.y - 20))
    assert a.state_hash() == b.state_hash()


# --- the dash -----------------------------------------------------------------------------------
def test_dash_covers_more_ground_than_running():
    plain, dashed = Game(seed=0, remastered=True), Game(seed=0, remastered=True)
    settle(plain)
    settle(dashed)
    a = run_left(plain, 6)
    b = run_left(dashed, 6, dash_at=1)
    assert b[1] <= a[1] - 10  # the dash tick adds DASH_SPEED (13 px) to the running step
    assert b[5] < a[5] - 40


def test_dash_stops_at_walls():
    g = Game(seed=0, remastered=True)
    p = g.player
    for _ in range(20):  # run right into the wall blocks next to the start
        g.step(Inputs(x=1, pointer_x=p.x + 100, pointer_y=p.y - 20))
    x_wall = p.x
    assert g.remastered.request_dash(1)
    settle(g, 4)
    assert p.x == x_wall


def test_dash_gives_invulnerability_then_wears_off():
    g = Game(seed=0, remastered=True)
    settle(g)
    p = g.player
    hp = p.hp
    assert g.remastered.request_dash(1)
    g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20))
    p.do_damage(10, None, p.x, p.y, 0, 0)
    assert p.hp == hp  # ignored during the dash's invulnerability
    settle(g, DASH_IFRAMES)
    assert g.world.globals["player_iframes"] == 0
    p.do_damage(10, None, p.x, p.y, 0, 0)
    assert p.hp == hp - 10


def test_dash_has_a_cooldown_and_survives_save_and_restore():
    g = Game(seed=0, remastered=True)
    settle(g)
    assert g.remastered.request_dash(1)
    assert not g.remastered.request_dash(1)
    snap = g.snapshot()
    settle(g, DASH_COOLDOWN)
    assert g.remastered.request_dash(-1)
    g.restore(snap)
    assert g.remastered.state["cooldown"] == DASH_COOLDOWN and not g.remastered.request_dash(1)


def test_damage_events_say_whether_the_player_caused_them():
    g = Game(seed=0)
    w = g.world
    ant = w.find_type("ANT_ROOF")
    w.events = []
    w.note_damage(ant, 5, g.player)
    w.note_damage(g.player, 5, ant)
    assert [e.data["by_player"] for e in w.events] == [True, False]


# --- the app, headless --------------------------------------------------------------------------
@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    return tmp_path


def make_app(mode, frames=40):
    from abuse_remake.game.app import App, parse_args

    return App(parse_args(["--mode", mode, "--frames", str(frames), "--no-audio", "--seed", "1", "--scale", "1"]))


def test_records_keep_the_best_time(home):
    from abuse_remake.game.remaster import load_records, record_finish

    base = {"kills": 3, "secrets": 1, "deaths": 0, "damage_taken": 40}
    assert record_finish("hard", {**base, "ticks": 900}) == {"best": None, "new_best": True}
    assert record_finish("hard", {**base, "ticks": 1200})["new_best"] is False
    assert record_finish("hard", {**base, "ticks": 600})["new_best"] is True
    assert load_records()["level01-hard"]["ticks"] == 600


def test_ghost_is_recorded_saved_loaded_and_drawn(home):
    from abuse_remake.game.remaster import load_ghost

    app = make_app("remastered", frames=30)
    app.run()
    rows = app.ghost_rec.rows
    assert len(rows) == app.stats["ticks"] > 0 and len(rows[0]) == 9
    app.ghost_rec.save("hard")
    assert load_ghost("hard") == rows
    again = make_app("remastered", frames=20)
    assert again.ghost == rows
    again.run()  # draws the ghost every frame; must not fail
    assert again.ghost_painter is not None


def test_dash_key_quick_restart_and_stats_screen(home):
    import pygame

    app = make_app("remastered", frames=1)
    app.state = "play"
    for i in range(3):  # the player starts in JUST_START; it cannot dash until play begins
        app.tick(i)
    app.on_key(pygame.K_f)
    app.tick(3)
    assert app.stats["dashes"] == 1 and app.game.remastered.state["iframes"] == DASH_IFRAMES - 1
    before = app.checkpoint
    app.on_key(pygame.K_r)  # quick restart at the last console (here, the level start)
    assert app.game.frames == before[3]
    app.finish = {"best": {"ticks": 3000}, "new_best": True}
    app.stats.update(ticks=2400, shots=10, hits=4)
    lines = app.stats_lines()
    assert "accuracy 40%" in " ".join(lines) and any("NEW BEST TIME" in x for x in lines)


def test_classic_app_has_no_remastered_features(home):
    import pygame

    app = make_app("classic", frames=10)
    assert app.game.remastered is None and app.ghost_rec is None and app.ghost is None
    app.state = "play"
    app.on_key(pygame.K_f)
    app.on_key(pygame.K_r)
    app.tick(0)
    assert app.stats["dashes"] == 0
    app.run()
    assert "accuracy" not in " ".join(app.stats_lines())
