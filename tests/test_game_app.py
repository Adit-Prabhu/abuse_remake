"""The playable game's front end: restarts, traces and their replay, input mapping, timing, the
camera, Classic lighting and sound. Headless (SDL dummy drivers)."""

import json

import numpy as np
import pygame
import pytest

from abuse_remake.engine.game import Game
from abuse_remake.engine.view import Inputs
from abuse_remake.engine.world import LightSource
from abuse_remake.game.lighting import light_levels, mul_div


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    return tmp_path


def make_app(*extra):
    from abuse_remake.game.app import App, parse_args

    return App(parse_args(["--frames", "1", "--no-audio", "--seed", "1", "--scale", "1", *extra]))


def settle(app, n=3):
    app.state = "play"
    for i in range(n):
        app.tick(i)


def save_at_console(game):
    """Stand on the first restart console and press down until it saves (restart_ai)."""
    console = game.world.find_type("RESTART_POSITION")
    p = game.player
    p.x, p.y = console.x, console.y
    for _ in range(8):
        game.step(Inputs(y=1, pointer_x=p.x + 100, pointer_y=p.y - 20))
        game.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20))
    return console


def walk_to_console(app):
    """Inputs (as a player would give them) that walk to the nearest console and press down."""
    consoles = [(o.x, o.y) for o in app.game.world.objects if o.ctype.name == "RESTART_POSITION"]

    def inputs(tick):
        p = app.game.player
        cx, cy = min(consoles, key=lambda c: abs(c[0] - p.x) + abs(c[1] - p.y))
        x = -1 if p.x > cx + 2 else (1 if p.x < cx - 2 else 0)
        return Inputs(x=x, y=1 if (x == 0 and tick % 2 == 0) else 0, pointer_x=p.x - 100, pointer_y=p.y - 20)
    return inputs


# --- restarts ------------------------------------------------------------------------------------
def test_a_console_save_becomes_the_checkpoint_at_full_health(home):
    app = make_app("--mode", "classic")
    settle(app)
    app.game.player.hp = 40
    app.scripted_inputs = walk_to_console(app)
    settle(app, 30)
    assert app.checkpoint is not app.level_start
    p = app.checkpoint[2]
    assert p.hp == 100 and p.lvars["has_saved_this_level"] == 1  # restart_ai saves at 100 (people.lsp:885-901)
    assert app.game.player.hp == 40  # and gives the old health back afterwards
    assert "save_hook" not in app.checkpoint[0].globals  # the front end is not inside the save


def test_restores_can_be_repeated_any_number_of_times(home):
    app = make_app("--mode", "remastered")
    settle(app)
    save_at_console(app.game)
    for _ in range(3):
        app.tick(0)
        app.on_key(pygame.K_r)  # Remastered quick restart
        app.state = "paused"
        app.on_key(pygame.K_r)  # pause, restart the level
        app.tick(1)
        app.game.player.aistate = 3
        app.state = "dead"
        app.on_key(pygame.K_SPACE)  # death, back to the last save
        assert app.state == "play"
    assert app.game.world.globals["save_hook"] == app._on_console_save


def test_restarting_the_level_forgets_the_old_runs_console(home):
    app = make_app("--mode", "classic")
    settle(app)
    save_at_console(app.game)
    assert app.checkpoint is not app.level_start
    app.state = "paused"
    app.on_key(pygame.K_r)
    assert app.checkpoint is app.level_start  # a restarted level has no save yet (people.lsp:516-520)
    app.game.player.aistate = 3
    app.state = "dead"
    app.on_key(pygame.K_RETURN)
    assert app.state == "dead"  # only space restarts, as in the original
    app.on_key(pygame.K_SPACE)
    start = Game(seed=1).player
    assert (app.game.player.x, app.game.player.y) == (start.x, start.y)


# --- human traces --------------------------------------------------------------------------------
def test_human_trace_round_trip_with_a_save_restarts_and_a_level_restart(home, tmp_path):
    from abuse_remake.game.human_replay import replay_human

    rec = tmp_path / "session.jsonl"
    app = make_app("--mode", "classic", "--record", str(rec))
    app.scripted_inputs = walk_to_console(app)
    settle(app, 30)  # walk to the console and save, through the game's own rules
    assert app.checkpoint is not app.level_start
    wander = app.__class__.scripted_inputs.__get__(app)
    app.scripted_inputs = wander
    settle(app, 25)
    app.state = "dead"  # the restart screen; space goes back to the save
    app.on_key(pygame.K_SPACE)
    settle(app, 20)
    app.state = "paused"
    app.on_key(pygame.K_r)  # restart the level
    settle(app, 20)
    app._check("session end")
    app.trace.close()
    rows = [json.loads(x) for x in rec.read_text().splitlines()]
    assert [r["to"] for r in rows if r["kind"] == "restore"] == ["checkpoint", "level_start"]
    out = replay_human(rec)
    assert out["checks"] == 3 and out["mismatches"] == 0  # two restores and the end all match
    g = out["games"][0]
    assert g["ticks"] == app.stats["ticks"] and g["console_saves"] >= 1 and 0.0 < g["progress"] <= 1.0
    i = next(k for k, r in enumerate(rows) if r["kind"] == "input" and r["tick"] == 40)
    rows[i]["x"] = 1 if rows[i]["x"] != 1 else -1  # tamper with one input
    rec.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert replay_human(rec)["mismatches"] > 0


def test_title_toggles_do_not_truncate_the_session_trace(home, tmp_path):
    rec = tmp_path / "session.jsonl"
    app = make_app("--record", str(rec))
    settle(app, 5)
    app.state = "title"
    app.on_key(pygame.K_d)  # a new game with another difficulty
    app.on_key(pygame.K_m)  # and another mode
    settle(app, 5)
    app.trace.flush()
    kinds = [json.loads(x)["kind"] for x in rec.read_text().splitlines()]
    assert kinds.count("header") == 1 and kinds.count("new_game") == 3 and kinds.count("input") == 10


# --- input, timing and camera --------------------------------------------------------------------
class Keys(dict):
    def __getitem__(self, k):
        return self.get(k, False)


def test_input_mapping_left_wins_and_the_aim_follows_the_drawn_camera(home, monkeypatch):
    app = make_app("--mode", "classic")
    settle(app)
    keys = Keys({pygame.K_LEFT: True, pygame.K_RIGHT: True, pygame.K_s: True})
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: keys)
    monkeypatch.setattr(pygame.mouse, "get_pressed", lambda n=3: (True, False, True))
    sw, sh = app.screen.get_size()
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (sw // 2, sh // 4))
    app.renderer.last_cam = (100.0, 40.0)
    inp = app.read_inputs()
    assert (inp.x, inp.y, inp.b1, inp.b2) == (-1, 1, 1, 1)  # left wins; down is the action key
    assert (inp.pointer_x, inp.pointer_y) == (100 + app.view_w // 2, 40 + app.view_h // 4)


def test_original_weapon_keys(home):
    app = make_app("--mode", "classic")
    settle(app)
    for key, cycle in ((pygame.K_LCTRL, -1), (pygame.K_HOME, -1), (pygame.K_INSERT, 1), (pygame.K_PAGEUP, 1)):
        app.pending_weapon = None
        app.on_key(key)
        assert app.pending_weapon is not None and app.pending_weapon.cycle == cycle


def test_a_long_stall_runs_only_a_few_ticks(home):
    app = make_app("--mode", "classic")
    settle(app)
    before = app.stats["ticks"]
    app.advance(3600.0)  # an hour asleep
    assert app.stats["ticks"] - before <= 4


def test_the_camera_is_interpolated_between_ticks(home):
    app = make_app("--mode", "classic")
    settle(app)
    moved = 0
    for i in range(40):
        app.tick(i)
        r = app.renderer
        if r.cam_prev != r.cam_cur:
            moved += 1
            (px, py), (cx, cy) = r.cam_prev, r.cam_cur
            mx, my = r.camera(0.5)
            assert min(px, cx) <= mx <= max(px, cx) and min(py, cy) <= my <= max(py, cy)
    assert moved > 0  # the view really moves between frames, not in 15 Hz steps


def test_classic_draws_only_active_objects(home, monkeypatch):
    app = make_app("--mode", "classic")
    settle(app)
    drawn = []
    monkeypatch.setattr(app.renderer, "_draw_object", lambda surf, o, *a: drawn.append(o))
    app.renderer.render(0.5)
    active = {id(o) for o in app.game.world.active}
    assert drawn and all(id(o) in active for o in drawn)


# --- light and sound -----------------------------------------------------------------------------
def test_light_levels_follow_light_c():
    lamp = LightSource(type=0, x=100, y=50, inner_radius=10, outer_radius=60, xshift=0, yshift=0)
    lv = light_levels([lamp], 20, 0, 0, 200, 100)
    assert lv[5, 199] == 20  # far away: the ambient level
    assert lv[50, 100] == 63  # at the light: capped at 63
    md = mul_div(lamp)
    assert md == (65536 // 50) * 64
    dx, dy = 30, 10  # octagonal distance 30 + 10 - 5 = 35
    assert lv[50 + dy, 100 + dx] == min(63, 20 + ((60 - 35) * md >> 16))
    rect = LightSource(type=9, x=0, y=0, inner_radius=7, outer_radius=0, xshift=20, yshift=20)
    assert light_levels([rect, lamp], 20, 0, 0, 200, 100)[10, 10] == 7  # a rectangle sets the level
    assert (light_levels([], 63, 0, 0, 4, 4) == 63).all()


def test_classic_darkening_subtracts_from_each_channel(home):
    app = make_app("--mode", "classic")
    surf = pygame.Surface((app.view_w, app.view_h))
    surf.fill((200, 100, 10))
    app.game.view.ambient = 35
    app.game.world.lights = []
    app.renderer._apply_lighting(surf, 0, 0)
    assert tuple(surf.get_at((5, 5)))[:3] == (172, 72, 0)  # 63 - 35 = 28 off each channel (light.c:230-245)


def test_sound_volume_follows_game_play_sound():
    from abuse_remake.game.audio import original_volume

    assert original_volume(127, 0, 0) == 127 and original_volume(127, 90, 0) == 127
    assert original_volume(127, 300, 0) == (400 - 200) * 127 // 400
    assert original_volume(127, 200, 200) == (400 - 200) * 127 // 400  # octagonal: 200 + 200 - 100 = 300
    assert original_volume(127, 501, 0) == 0 and original_volume(14, 0, 0) == 0
    assert original_volume(100, 0, 0) == 100


def test_the_front_end_never_touches_the_engine_random_table(home):
    a = Game(seed=5)
    app = make_app("--mode", "remastered")
    app.game = Game(seed=5, remastered=True)
    app._rebind()
    for g in (a, app.game):
        for i in range(60):
            p = g.player
            inp = Inputs(x=1 if i % 20 < 14 else -1, b2=int(i % 3 == 0), pointer_x=p.x + 100, pointer_y=p.y - 20)
            g.step(inp)
            if g is app.game:
                app.renderer.note_tick()
                app.renderer.render(0.5)
                app.particles.on_events(g.world.events)
    assert a.world.rng.rand_on == app.game.world.rng.rand_on
    assert np.array_equal([a.player.x, a.player.y], [app.game.player.x, app.game.player.y])
