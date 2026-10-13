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
    assert (x, y) == (480 + app.renderer.last_camera[0], 270 + app.renderer.last_camera[1])
    pygame.quit()


def test_neon_trace_round_trip_includes_checkpoint_dash_and_restart(tmp_path):
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
