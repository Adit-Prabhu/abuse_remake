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


def test_damage_and_shot_events_say_whether_the_player_caused_them():
    from abuse_remake.engine.behaviors.weapons import fire_object

    g = Game(seed=0)
    settle(g)
    w = g.world
    ant = w.find_type("ANT_ROOF")
    w.events = []
    mine = fire_object(g.player, 0, g.player.x, g.player.y - 20, 0, None)  # the player's laser shot
    theirs = fire_object(ant, 0, ant.x, ant.y, 180, None)  # an ant's shot
    assert mine.objs[0] is g.player  # projectiles link their creator first
    w.note_damage(ant, 5, mine)
    w.note_damage(g.player, 5, theirs)
    shots = [(e.data["uid"], e.data["by_player"]) for e in w.events if e.kind == "shot"]
    hits = [(e.data["source_uid"], e.data["by_player"]) for e in w.events if e.kind == "damage"]
    assert shots == [(mine.uid, True), (theirs.uid, False)]
    assert hits == [(mine.uid, True), (theirs.uid, False)]


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


def _saved_ghost(home):
    app = make_app("remastered", frames=30)
    app.run()
    app.ghost_rec.save("hard")
    return app.ghost_rec.rows


def test_with_the_ghost_off_it_is_not_drawn_but_the_run_is_still_recorded(home):
    """The student, 2026-10-27: a setting for the ghost; off hides it, and the best is still kept."""
    from abuse_remake.game.remaster import ghost_shown, save_setting

    _saved_ghost(home)
    assert ghost_shown()  # on unless switched off
    save_setting("ghost", False)
    app = make_app("remastered", frames=20)
    assert app.ghost and not app.show_ghost
    app.run()
    assert app.ghost_painter is None  # never drawn
    assert len(app.ghost_rec.rows) == app.stats["ticks"] > 0  # still recorded, to save a new best
    assert not any("GHOST" in m[0].upper() for m in app.hud.messages)


def test_g_switches_the_ghost_setting_and_it_is_kept(home):
    import pygame

    app = make_app("remastered", frames=1)
    app.state = "play"
    assert app.show_ghost
    app.on_key(pygame.K_g)
    assert not app.show_ghost
    assert make_app("remastered", frames=1).show_ghost is False  # kept for the next session


def test_the_ghost_is_red_outlined_and_labelled_and_announced_once(home, monkeypatch):
    import numpy as np
    import pygame

    from abuse_remake.game.remaster import GhostPainter

    _saved_ghost(home)
    app = make_app("remastered", frames=1)
    painter = GhostPainter(pygame, app.sprites)
    fig = app.game.world.types["DARNEL"].sequences["running"][0]
    img = painter._image(fig, 1)
    w, h = img.get_size()
    px = np.frombuffer(pygame.image.tobytes(img, "RGBA"), np.uint8).reshape(h, w, 4).astype(int)
    seen = px[..., 3] > 0
    r, g, b = px[..., 0][seen], px[..., 1][seen], px[..., 2][seen]
    assert (r > g + 60).mean() > 0.9 and (r > b + 60).mean() > 0.9  # red, not the old light blue
    body = pygame.mask.from_surface(app.sprites.figure(fig)[0])
    outline = seen.copy()
    for y, x in zip(*np.nonzero(seen), strict=True):
        if 0 < x <= body.get_size()[0] and 0 < y <= body.get_size()[1] and body.get_at((x - 1, y - 1)):
            outline[y, x] = False
    assert outline.sum() > 20  # a bright rim around the figure, outside its own pixels
    said = []
    monkeypatch.setattr(app.mhud.t, "text", lambda surf, text, *a, **k: said.append(text) or pygame.Rect(0, 0, 1, 1))
    app.state = "play"
    for i in range(3):
        app.tick(i)
        app.draw()
    assert "GHOST" in said  # its label, over its head
    hints = [m for m in app.hud.messages if "GHOST" in m[0].upper()]
    assert len(hints) == 1  # said once, as the level starts


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
    app.stats.update(ticks=2400, shots=10, enemies_hit=4)
    lines = app.stats_lines()
    assert "shots fired 10   enemies hit 4" in " ".join(lines) and any("NEW BEST TIME" in x for x in lines)


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
    assert "shots fired" not in " ".join(app.stats_lines())


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


def test_the_spectator_panel_numbers_the_decision_being_played(home):
    from abuse_remake.agent.interface import PLAYER_ID, AbuseEpisode
    from abuse_remake.game.spectate import Spectator

    ep = AbuseEpisode("level01-cp1", seed=0)
    spec = Spectator(ep, None, "test", scale=1, headless=True)
    shown = []
    real = spec._text

    def capture(text, *a, **k):
        if text.startswith("decision "):
            shown.append(text.split()[1])
        return real(text, *a, **k)

    spec._text = capture
    ep.step(PLAYER_ID, "wait")
    assert shown and set(shown) == {f"1/{ep.budgets.max_decisions}"}  # never "0/..." while it runs


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
    first = app.game
    app.on_key(pygame.K_RETURN)  # play again: a new run in the same arena
    assert app.state == "play" and app.game is not first and app.game.horde.state["wave"] == 0
    app.game.player.hp = 0
    app.game.player.aistate = 3
    app.tick(0)
    app.on_key(pygame.K_ESCAPE)  # or back to the title
    assert app.state == "title"



# --- review fixes (PR #7) --------------------------------------------------------------------
def test_remastered_without_a_dash_matches_classic_even_when_the_player_is_hurt():
    games = [Game(seed=6), Game(seed=6, remastered=True)]
    for g in games:
        ant = g.world.find_type("ANT_ROOF")
        for i in range(90):
            p = g.player
            if i == 30:
                p.do_damage(12, ant, p.x, p.y, 3, -2)  # through bottom_damage, the one Classic hook
            g.step(Inputs(x=1 if i % 30 < 20 else -1, b2=int(i % 4 == 0), pointer_x=p.x + 100, pointer_y=p.y - 20))
    a, b = games
    assert a.player.hp == b.player.hp < 100
    assert a.state_hash() == b.state_hash()


def test_the_dash_event_survives_the_step_and_a_teleport_or_death_cancels_the_dash():
    g = Game(seed=0, remastered=True)
    settle(g)
    assert g.remastered.request_dash(-1)
    g.step(Inputs(pointer_x=g.player.x - 100, pointer_y=g.player.y - 20))
    assert [e.kind for e in g.world.events].count("dash") == 1
    assert g.remastered.state["dash_left"] == 3
    g.player.lvars["is_teleporting"] = 1
    x = g.player.x
    g.step(Inputs(pointer_x=g.player.x - 100, pointer_y=g.player.y - 20))
    assert g.remastered.state["dash_left"] == 0 and abs(g.player.x - x) < 13


def test_the_dash_is_refused_before_play_starts_while_teleporting_and_when_dead():
    g = Game(seed=0, remastered=True)
    assert not g.remastered.request_dash(1)  # JUST_START, before the first tick
    settle(g)
    g.player.lvars["is_teleporting"] = 1
    assert not g.remastered.request_dash(1)
    g.player.lvars["is_teleporting"] = 0
    g.player.aistate = 2
    assert not g.remastered.request_dash(1)


@pytest.mark.parametrize("ticks", range(1, DASH_IFRAMES + 2))
def test_invulnerability_lasts_exactly_dash_iframes_ticks(ticks):
    g = Game(seed=0, remastered=True)
    settle(g)
    p = g.player
    assert g.remastered.request_dash(1)
    for _ in range(ticks):
        g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20))
    hp = p.hp
    p.do_damage(10, None, p.x, p.y, 0, 0)
    assert (p.hp == hp) == (ticks < DASH_IFRAMES)


def test_horde_state_survives_save_and_restore():
    g = Game(seed=2, horde=True)
    for _ in range(80):
        g.step(Inputs(pointer_x=g.player.x + 100, pointer_y=g.player.y - 20))
    snap = g.snapshot()
    before = (dict(g.horde.state), g.state_hash())
    for _ in range(40):
        g.step(Inputs(pointer_x=g.player.x + 100, pointer_y=g.player.y - 20))
    g.restore(snap)
    assert g.horde.state == before[0] and g.state_hash() == before[1]
    after = []
    for g2 in (g, Game(seed=2, horde=True)):
        if g2 is not g:
            for _ in range(80):
                g2.step(Inputs(pointer_x=g2.player.x + 100, pointer_y=g2.player.y - 20))
        for _ in range(40):
            g2.step(Inputs(pointer_x=g2.player.x + 100, pointer_y=g2.player.y - 20))
        after.append(g2.state_hash())
    assert after[0] == after[1]  # a restored run continues exactly like an unbroken one


def test_playtests_default_to_classic_and_horde_needs_remastered():
    from abuse_remake.game.app import parse_args

    assert parse_args(["--playtest"]).mode == "classic"
    assert parse_args([]).mode == "remastered"
    with pytest.raises(SystemExit):
        parse_args(["--horde", "--mode", "classic"])


def test_nothing_runs_after_the_level_ends_and_the_best_is_recorded_once(home):
    app = make_app("remastered", frames=1)
    app.state = "play"
    app.game.world.globals["level_complete"] = True
    calls = []
    import abuse_remake.game.remaster as remaster

    real = remaster.record_finish
    remaster.record_finish = lambda *a: calls.append(a) or real(*a)
    try:
        app.advance(0.5)  # a slow frame owes 7 ticks
    finally:
        remaster.record_finish = real
    assert app.state == "complete" and len(calls) == 1 and app.finish["new_best"] and app.stats["ticks"] == 1


def test_bad_record_and_ghost_files_do_not_crash_or_wipe(home):
    import json

    from abuse_remake.game.remaster import load_ghost, load_records, record_finish

    (home / "records.json").write_text("{not json")
    assert load_records() == {} and (home / "records.unreadable.json").exists()  # moved aside, not lost
    (home / "records.json").write_text(json.dumps({"level01-hard": {"ticks": "fast"}, "horde-hard": [1]}))
    assert load_records() == {}
    assert record_finish("hard", {"ticks": 900, "kills": 1, "secrets": 0, "deaths": 0, "damage_taken": 0})["new_best"]
    for rows in ([[1, 2]], [["x", 2, 1, "stopped", 0]], "rows"):
        (home / "ghost-level01-hard.json").write_text(json.dumps({"version": 1, "rows": rows}))
        assert load_ghost("hard") is None


def test_recorded_human_traces_say_which_rules_and_include_dashes(home, tmp_path):
    import json

    import pygame

    from abuse_remake.game.app import App, parse_args

    rec = tmp_path / "h.jsonl"
    app = App(parse_args(["--frames", "1", "--no-audio", "--seed", "1", "--scale", "1", "--record", str(rec)]))
    app.state = "play"
    for i in range(3):
        app.tick(i)
    app.on_key(pygame.K_f)
    app.tick(3)
    app.trace.close()
    rows = [json.loads(x) for x in rec.read_text().splitlines()]
    game = next(r for r in rows if r["kind"] == "new_game")
    assert rows[0]["format"] == "human-trace-1" and game["rules"] == "remastered" and game["horde"] is False
    assert [r.get("dash") for r in rows if r["kind"] == "input"] == [None, None, None, 1]


def _replay(path, *extra):
    from abuse_remake.game.spectate import main

    return main(["--trace", str(path), "--headless", "--scale", "1", *extra])


def test_replay_rejects_truncated_and_edited_traces_and_reports_an_interrupted_replay(home, tmp_path):
    import json

    path = _short_trace(tmp_path, 8)
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    cut = tmp_path / "cut.jsonl"
    cut.write_text("\n".join(json.dumps(r) for r in rows[:-3] + rows[-1:]) + "\n")  # two steps missing
    assert _replay(cut) == 1
    edited = tmp_path / "edited.jsonl"
    rows[-1]["score"] = 1
    edited.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert _replay(edited) == 1  # the outcome row is checked too
    assert _replay(path, "--max-frames", "3") == 2  # stopped early: not a pass


def test_a_runner_stopped_trace_replays_and_spectating_enforces_budgets(home, tmp_path):
    import json
    import sys

    from abuse_remake.agent.interface import Budgets
    from abuse_remake.agent.protocol import ProcessPlayer
    from abuse_remake.agent.runner import run_episode
    from abuse_remake.game.spectate import main

    script = tmp_path / "token_player.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    m = json.loads(line)\n"
        "    if m['type'] == 'decide':\n"
        "        meta = {'calls': 1, 'input_tokens': 100, 'output_tokens': 1}\n"
        "        print(json.dumps({'id': m['id'], 'action': 'wait', 'meta': meta}), flush=True)\n"
        "    elif m['type'] == 'end':\n"
        "        break\n")
    trace = tmp_path / "stopped.jsonl"
    out = run_episode(ProcessPlayer([sys.executable, str(script)]), "level01-cp1", 0,
                      budgets=Budgets(max_ticks=2700, max_decisions=50, max_input_tokens=250), trace_path=trace)
    assert out["reason"] == "token budget exhausted" and out["decisions"] == 3
    assert _replay(trace) == 0  # the replay ends where the runner ended it
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(["--player", f"cmd:{sys.executable} {script}", "--scenario", "level01-cp1", "--headless",
                     "--scale", "1", "--max-input-tokens", "250"])
    watched = json.loads(buf.getvalue())
    assert code == 0 and watched["reason"] == "token budget exhausted" and watched["decisions"] == 3
