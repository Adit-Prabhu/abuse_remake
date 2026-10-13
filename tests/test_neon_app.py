"""Headless integration checks for mode selection, readable UI and replayable input."""

import json

import pygame
import pytest

from abuse_remake.engine.view import Inputs
from abuse_remake.game.app import parse_args


def make_app(*extra):
    from abuse_remake.game.neon_app import NeonApp

    return NeonApp(parse_args(["--mode", "neon", "--no-audio", "--scale", "1", "--seed", "7", *extra]))


def test_cli_accepts_campaign_horde_and_tutorial_and_refuses_ambiguous_modes():
    assert parse_args(["--mode", "neon"]).mode == "neon"
    assert parse_args(["--mode", "neon", "--horde"]).horde
    assert parse_args(["--mode", "neon", "--tutorial"]).tutorial
    with pytest.raises(SystemExit):
        parse_args(["--mode", "classic", "--tutorial"])
    with pytest.raises(SystemExit):
        parse_args(["--mode", "neon", "--tutorial", "--horde"])


def test_neon_controls_pause_without_advancing_simulation():
    app = make_app("--skip-title")
    app.on_key(pygame.K_F1)
    before = app.game.state_hash()
    app.advance(2)
    app.draw()
    assert app.state == "controls" and app.game.state_hash() == before
    app.on_key(pygame.K_ESCAPE)
    assert app.state == "play"
    pygame.quit()


def test_all_menu_variants_start_the_corresponding_engine():
    app = make_app()
    for variant in ("campaign", "horde", "tutorial"):
        app.start(variant)
        assert app.state == "play" and app.game.variant == variant
        app.draw()
    pygame.quit()


def test_rendering_is_read_only_and_mouse_aim_uses_interpolated_camera():
    app = make_app("--skip-title")
    app.game.player.x = 1000
    app.renderer.reset(app.game)
    app.draw()
    before = app.game.state_hash()
    app.draw()
    assert before == app.game.state_hash()
    x, y = app.screen_to_game(480, 270)
    assert (x, y) == (320 + app.renderer.last_camera[0], 180 + app.renderer.last_camera[1])
    pygame.quit()


def test_neon_trace_round_trip_includes_dash_and_restart(tmp_path):
    from abuse_remake.game.human_replay import replay_human

    path = tmp_path / "neon.jsonl"
    app = make_app("--skip-title", "--record", str(path))
    app.start("tutorial")
    for _ in range(20):
        app.tick(Inputs(x=1))
    app.pending_dash = True
    app.tick(Inputs(x=1))
    app.restore("level_start")
    for _ in range(8):
        app.tick(Inputs(x=-1))
    app.close_trace()
    assert json.loads(path.read_text().splitlines()[0])["format"] == "neon-trace-1"
    result = replay_human(path)
    assert result["mismatches"] == 0 and result["checks"] >= 2
    assert result["games"][-1]["rules"] == "neon"
    pygame.quit()


def test_campaign_checkpoint_restores_repeatedly_and_trace_replays(tmp_path):
    from abuse_remake.game.human_replay import replay_human

    path = tmp_path / "checkpoint.jsonl"
    app = make_app("--skip-title", "--record", str(path))
    for tick in range(400):
        p = app.game.player
        targets = [e for e in app.game.enemies if e.x < app.game.doors[0][0]]
        enemy = min(targets, key=lambda e: abs(e.x - p.x)) if targets else None
        goal = app.game.relays[0].x - 10
        move = 1 if p.x < goal - 5 else -1 if p.x > goal + 5 else 0
        app.tick(Inputs(x=move, y=1 if not move and tick % 2 == 0 else -1 if tick % 30 == 0 else 0,
                        b2=int(enemy is not None), pointer_x=enemy.x + enemy.w // 2 if enemy else goal,
                        pointer_y=enemy.y + enemy.h // 2 if enemy else 480))
        if app.game.relays[0].active:
            break
    assert app.game.relays[0].active
    checkpoint_hash = app.game.state_hash()
    for _ in range(3):
        app.tick(Inputs(x=1))
        app.restore()
        assert app.game.state_hash() == checkpoint_hash
    app.close_trace()
    result = replay_human(path)
    assert result["mismatches"] == 0 and result["games"][0]["console_saves"] == 1
    pygame.quit()


def test_title_difficulty_change_keeps_finished_trace_replayable(tmp_path):
    from abuse_remake.game.human_replay import replay_human

    path = tmp_path / "title-config.jsonl"
    app = make_app("--skip-title", "--record", str(path))
    for _ in range(12):
        app.tick(Inputs(x=1))
    app.on_key(pygame.K_ESCAPE)
    app.on_key(pygame.K_t)
    before = app.game.state_hash()
    app.on_key(pygame.K_d)
    assert app.game.state_hash() == before
    app.close_trace()
    assert replay_human(path)["mismatches"] == 0
    pygame.quit()


def test_mode_switch_preserves_all_games_in_one_recording(tmp_path):
    from abuse_remake.game.app import App
    from abuse_remake.game.human_replay import replay_human
    from abuse_remake.game.neon_app import NeonApp

    path = tmp_path / "mixed.jsonl"
    args = parse_args(["--mode", "neon", "--frames", "2", "--no-audio", "--scale", "1", "--record", str(path)])
    NeonApp(args).run()
    first = path.read_text()
    args._append_trace = True  # same handoff flag the main loop sets
    args.mode = "remastered"
    App(args).run()
    assert path.read_text().startswith(first)
    args.mode = "neon"
    NeonApp(args).run()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert sum(r["kind"] == "header" for r in rows) == 1
    result = replay_human(path)
    assert result["mismatches"] == 0 and len(result["games"]) == 3


def test_recording_a_mode_handoff_and_quitting_at_title_matches(tmp_path):
    from abuse_remake.game.app import App
    from abuse_remake.game.human_replay import replay_human
    from abuse_remake.game.neon_app import NeonApp

    path = tmp_path / "idle-handoff.jsonl"
    args = parse_args(["--frames", "2", "--no-audio", "--scale", "1", "--record", str(path)])
    App(args).run()
    args.mode, args.frames, args._append_trace = "neon", 0, True
    app = NeonApp(args)
    app.close_trace()
    assert replay_human(path)["mismatches"] == 0
    pygame.quit()


def test_legacy_controls_are_accessible_from_title_and_pause():
    from abuse_remake.game.app import App

    app = App(parse_args(["--mode", "remastered", "--no-audio", "--scale", "2"]))
    app.on_key(pygame.K_c)
    assert app.state == "controls"
    app.draw()
    app.on_key(pygame.K_ESCAPE)
    assert app.state == "title"
    app.state = "paused"
    app.on_key(pygame.K_F1)
    assert app.state == "controls"
    app.on_key(pygame.K_ESCAPE)
    assert app.state == "paused"
    pygame.quit()


def test_ghost_preserves_exact_alpha_mask():
    import numpy as np

    from abuse_remake.engine.game import Game
    from abuse_remake.game.remaster import GhostPainter
    from abuse_remake.game.sprites import SpriteCache

    pygame.init()
    pygame.display.set_mode((64, 64))
    game = Game()
    sprites = SpriteCache()
    fig = game.player.figure()
    source = sprites.figure(fig)[0]
    ghost = GhostPainter(pygame, sprites)._image(fig, 1)
    assert ghost.get_alpha() == 255  # opacity is baked into per-pixel alpha, no blanket surface alpha
    src_alpha = pygame.surfarray.array_alpha(source)
    got_alpha = pygame.surfarray.array_alpha(ghost)
    assert np.all(got_alpha[src_alpha == 0] == 0)
    assert np.all(got_alpha[src_alpha > 0] == 110)
    pygame.quit()


def test_neon_uses_shaded_animated_assets_with_transparent_silhouettes():
    import numpy as np

    app = make_app()
    art = app.renderer.art
    for group in ("courier_idle", "courier_run", "drone", "stalker_run", "sentry", "titan_idle"):
        frames = art.animations[group]
        assert len(frames) >= 2
        first = frames[0]
        alpha = pygame.surfarray.array_alpha(first)
        colors = pygame.surfarray.array3d(first)[alpha > 0]
        assert np.any(alpha == 0) and np.any(alpha == 255)
        assert len(np.unique(colors, axis=0)) >= 5  # five-color palettes include dark/midtone/highlight clusters
    pygame.quit()


def test_sentry_muzzle_faces_the_same_direction_as_its_shield():
    import numpy as np

    app = make_app()
    art = app.renderer.art
    source = art.animations["sentry"][0]
    assert np.array_equal(pygame.surfarray.array3d(art.frame("sentry", 0, -1)),
                          pygame.surfarray.array3d(source))
    assert np.array_equal(pygame.surfarray.array_alpha(art.frame("sentry", 0, 1)),
                          pygame.surfarray.array_alpha(pygame.transform.flip(source, True, False)))
    pygame.quit()


def test_floating_platform_material_matches_authoritative_collision_height(monkeypatch):
    app = make_app()
    game, art = app.game, app.renderer.art
    painted = []
    monkeypatch.setattr(art, "_tile_rect", lambda image, rect: painted.append(rect.copy()))
    art.environment(game, (0, 235))
    x, y, width, height = game.platforms[1]
    rects = [r for r in painted if r.x == x and r.width == width]
    assert rects and min(r.y for r in rects) == y - 235
    assert max(r.bottom for r in rects) == y - 235 + height
    pygame.quit()
