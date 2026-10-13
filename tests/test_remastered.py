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


# --- the spectator and trace replay ---------------------------------------------------------------
def _short_trace(tmp_path, decisions=10):
    from abuse_remake.agent.interface import Budgets
    from abuse_remake.agent.players.baselines import ScriptedPlayer
    from abuse_remake.agent.protocol import InProcessPlayer
    from abuse_remake.agent.runner import run_episode

    path = tmp_path / "t.jsonl"
    run_episode(InProcessPlayer(ScriptedPlayer()), "level01-cp1", 2,
                budgets=Budgets(max_ticks=2700, max_decisions=decisions), trace_path=path, label="scripted")
    return path


def test_replay_reproduces_every_observation(home, tmp_path):
    from abuse_remake.game.spectate import main

    assert main(["--trace", str(_short_trace(tmp_path)), "--headless", "--scale", "1"]) == 0


def test_replay_detects_a_trace_that_does_not_match_the_game(home, tmp_path):
    import json

    from abuse_remake.game.spectate import main

    path = _short_trace(tmp_path)
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    steps = [r for r in rows if r["kind"] == "step"]
    steps[3]["action"] = "wait" if steps[3]["action"] != "wait" else "move left"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert main(["--trace", str(path), "--headless", "--scale", "1"]) == 1


def test_spectating_does_not_change_the_game(home):
    from abuse_remake.agent.players.baselines import ScriptedPlayer
    from abuse_remake.agent.protocol import InProcessPlayer
    from abuse_remake.game.spectate import Spectator

    def play(watch):
        ep = AbuseEpisode("level01-cp1", seed=1)
        ep.budgets.max_decisions = 8
        if watch:
            sp = Spectator(ep, InProcessPlayer(ScriptedPlayer()), "scripted", scale=1, headless=True)
            sp.run()
            sp.close()
        else:
            p = ScriptedPlayer()
            while ep.outcome()["status"] == "ongoing":
                ep.step(PLAYER_ID, p.decide(ep.observe(PLAYER_ID), ep.legal_actions(PLAYER_ID))["action"])
        return ep._game.state_hash()

    assert play(True) == play(False)


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="needs ffmpeg")
def test_replay_renders_a_video(home, tmp_path):
    from abuse_remake.game.spectate import main

    out = tmp_path / "v.mp4"
    assert main(["--trace", str(_short_trace(tmp_path, 3)), "--headless", "--scale", "1", "--video", str(out)]) == 0
    assert out.stat().st_size > 1000


# --- Horde -----------------------------------------------------------------------------------------
def test_horde_waves_drops_and_the_end():
    from abuse_remake.engine.horde import ARENA_X1, ARENA_X2, FIRST_BREAK, SPAWN_EVERY, wave_size

    g = Game(seed=3, horde=True)
    assert g.remastered is not None and g.horde is not None
    assert {o.ctype.name for o in g.world.objects} <= {"START", "DARNEL"}  # the level's objects are gone
    assert ARENA_X1 < g.player.x < ARENA_X2 and g.view.weapons[0] > 0  # starts in the arena, with ammo
    kinds = []
    for _ in range(FIRST_BREAK + wave_size(1) * SPAWN_EVERY + 2):
        g.step(Inputs(pointer_x=g.player.x + 100, pointer_y=g.player.y - 20))
        kinds += [e.kind for e in g.world.events if e.kind.startswith("horde")]
    st = g.horde.state
    assert kinds == ["horde_wave"] and st["wave"] == 1 and len(st["alive"]) == wave_size(1)
    for o in g.world.objects:  # clear the wave
        if o.uid in st["alive"]:
            o.hp = 0
    g.step(Inputs(pointer_x=g.player.x + 100, pointer_y=g.player.y - 20))
    g.step(Inputs(pointer_x=g.player.x + 100, pointer_y=g.player.y - 20))
    assert st["cleared"] == 1 and st["break"] and st["kills"] == wave_size(1)
    drops = [o.ctype.name for o in g.world.objects if o.ctype.name in ("HEALTH", "MBULLET_ICON20", "GRENADE_ICON10",
                                                                       "ROCKET_ICON5", "FBOMB_ICON5")]
    assert "HEALTH" in drops and len(drops) == 2  # health plus one ammo drop after wave 1
    g.player.hp = 0
    g.player.aistate = 3
    g.step(Inputs(pointer_x=g.player.x + 100, pointer_y=g.player.y - 20))
    assert st["over"]


def test_horde_is_deterministic_and_never_in_classic():
    def run(seed):
        g = Game(seed=seed, horde=True)
        for i in range(260):
            p = g.player
            g.step(Inputs(x=1 if i % 50 < 25 else -1, b2=1, pointer_x=p.x + 100 * p.direction, pointer_y=p.y - 20))
        return g.state_hash()

    assert run(5) == run(5)
    assert Game(seed=5).horde is None and AbuseEpisode("level01", seed=5)._game.horde is None


def test_horde_app_shows_results_and_keeps_the_best(home):
    import pygame

    from abuse_remake.game.app import App, parse_args

    app = App(parse_args(["--horde", "--frames", "1", "--no-audio", "--seed", "2", "--scale", "1"]))
    assert app.horde and app.modern and app.ghost_rec is None
    app.state = "play"
    app.game.horde.state.update(cleared=3, kills=17)
    app.game.player.hp = 0
    app.game.player.aistate = 3
    app.tick(0)
    assert app.state == "horde_over" and app.finish["new_best"]
    app.draw()
    app.on_key(pygame.K_RETURN)
    assert app.state == "title"
