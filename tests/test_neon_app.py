"""Headless checks of the Neon Protocol front end: menus, help, recording and replay, read-only
rendering, aim mapping, transparent art, vendored assets, and silent fallback without audio.
Also keeps the two checks for the shared Remastered controls screen and ghost transparency."""

import hashlib
import json

import pygame
import pytest

from abuse_remake.engine.neon import NeonInput
from abuse_remake.game.app import parse_args
from abuse_remake.paths import assets_root


def make_app(*extra):
    from abuse_remake.game.neon.app import NeonApp

    return NeonApp(parse_args(["--mode", "neon", "--no-audio", "--scale", "1", "--seed", "7", *extra]))


@pytest.fixture(autouse=True)
def _quit_pygame(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path / "home"))
    yield
    pygame.quit()


def test_cli_selects_neon_and_its_variants():
    assert parse_args(["--mode", "neon"]).mode == "neon"
    assert parse_args(["--mode", "neon", "--horde"]).horde
    assert parse_args(["--tutorial"]).mode == "neon"
    with pytest.raises(SystemExit):
        parse_args(["--mode", "classic", "--tutorial"])


def test_title_menu_starts_every_mode_and_opens_the_manual():
    app = make_app()
    assert app.state == "title"
    app.draw(1 / 60)
    for key, variant in ((pygame.K_c, "campaign"), (pygame.K_h, "horde"), (pygame.K_t, "training")):
        app.to_title()
        app.on_key(key)
        assert app.state == "play" and app.game.variant == variant
        app.draw(1 / 60)
    app.to_title()
    app.on_key(pygame.K_F1)
    assert app.state == "manual"
    for page in range(4):
        app.on_key(pygame.K_1 + page)
        app.draw(1 / 60)
        assert app.page == page
    app.on_key(pygame.K_ESCAPE)
    assert app.state == "title"


def test_help_pause_and_map_freeze_the_simulation():
    app = make_app("--skip-title")
    for key, state in ((pygame.K_F1, "manual"), (pygame.K_TAB, "map"), (pygame.K_ESCAPE, "paused")):
        before = app.game.state_hash()
        app.on_key(key)
        assert app.state == state
        app.advance(1.0)
        app.draw(1 / 60)
        assert app.game.state_hash() == before
        app.on_key(pygame.K_ESCAPE)
        assert app.state in ("play", "paused")
        app.state = "play"


def test_rendering_never_changes_the_game_and_aim_maps_through_the_camera():
    app = make_app("--skip-title")
    for _ in range(10):
        app.tick(NeonInput(x=1, px=500, py=300))
    before = app.game.state_hash()
    for _ in range(3):
        app.draw(1 / 60)
    assert app.game.state_hash() == before
    cx, cy = app.renderer.last_camera
    sw, sh = app.screen.get_size()
    x, y = app.screen_to_world(sw // 2, sh // 2)
    assert (x, y) == (int(320 + cx), int(180 + cy))


def test_trace_round_trip_replays_with_restores_and_sector_change(tmp_path):
    from abuse_remake.engine.neon.autopilot import Autopilot
    from abuse_remake.game.human_replay import replay_human

    path = tmp_path / "neon.jsonl"
    app = make_app("--skip-title", "--record", str(path))
    bot = Autopilot(app.game, fight=True)
    for _ in range(1500):
        inp = bot.step()
        app.pending_select = bot.select
        app.tick(inp)
        if app.game.sector == 1:
            break
    assert app.game.sector == 1  # the sector change happened under recording
    for _ in range(20):
        app.tick(NeonInput(x=1, fire=True, px=app.game.player.cx + 90, py=app.game.player.cy))
    app.restore()
    app.restore()
    app.close_trace()
    rows = [json.loads(r) for r in path.read_text().splitlines()]
    assert rows[0]["format"] == "neon-trace-2"
    result = replay_human(path)
    assert result["mismatches"] == 0 and result["checks"] >= 3
    assert result["games"][-1]["rules"] == "neon" and result["games"][-1]["sector"] == 1


def test_checkpoint_restores_exactly_every_time():
    app = make_app("--skip-title")
    g = app.game
    console = g.consoles[0]
    p = g.player
    p.x, p.y = console.x - p.w // 2, console.y - p.h
    app.tick(NeonInput(interact=True, px=p.cx + 50, py=p.cy))
    saved = app.game.state_hash()
    for _ in range(3):
        for _ in range(30):
            app.tick(NeonInput(x=1, fire=True, px=app.game.player.cx + 80, py=app.game.player.cy))
        app.restore()
        assert app.game.state_hash() == saved


def test_horde_upgrade_choice_is_offered_and_recorded(tmp_path):
    from abuse_remake.game.human_replay import replay_human

    path = tmp_path / "horde.jsonl"
    app = make_app("--horde", "--skip-title", "--record", str(path))
    g = app.game
    for _ in range(95):
        app.tick(NeonInput(px=g.player.cx + 50, py=g.player.cy))
    for e in g.enemies:
        if e.kind != "nest":
            e.dead = True
    g.horde.queue.clear()
    app.tick(NeonInput(px=g.player.cx + 50, py=g.player.cy))
    app.tick(NeonInput(px=g.player.cx + 50, py=g.player.cy))
    assert app.state == "upgrade"
    app.draw(1 / 60)
    app.on_key(pygame.K_2)
    assert app.state == "play" and len(g.horde.taken) == 1
    app.close_trace()
    # direct state edits above (killing the wave) are not inputs, so only check the format here
    assert any(json.loads(r).get("upgrade") == 1 for r in path.read_text().splitlines()[1:])
    assert replay_human(path)["games"][0]["rules"] == "neon"


def test_art_keeps_transparency_and_the_hero_is_recoloured_not_boxed():
    import numpy as np

    app = make_app()
    art = app.renderer.art
    for frames in (art.hero["run"], art.crawler_walk, art.stinger, art.strider, art.warden, art.turret):
        alpha = pygame.surfarray.array_alpha(frames[0])
        assert np.any(alpha == 0) and np.any(alpha == 255)
        colours = pygame.surfarray.array3d(frames[0])[alpha > 0]
        assert len(np.unique(colours, axis=0)) >= 5
    gun = art.gun(2, 300)
    assert np.any(pygame.surfarray.array_alpha(gun) == 0)
    glow = art.premul(art.projectile["pulse"])
    assert glow.get_at((0, 0))[:3] == (0, 0, 0)  # transparent corners add nothing to the glow layer


def test_vendored_assets_match_the_manifest_and_carry_licences():
    root = assets_root() / "neon"
    manifest = json.loads((root / "manifest.json").read_text())
    assert {"city", "sideview", "weapons", "sfx_scifi", "sfx_creature", "music_specular", "fonts"} <= set(
        manifest["packs"])
    for pack in manifest["packs"].values():
        assert pack["licence"] and pack["page"].startswith("https://")
    paths = {f["path"] for f in manifest["files"]}
    for licence in ("city/public-license.txt", "sideview/public-license.txt", "sfx_scifi/License.txt",
                    "weapons/!info Eradication Wars Weapon Sprite Pack.txt", "fonts/Orbitron-OFL.txt"):
        assert licence in paths
    for f in manifest["files"]:
        assert hashlib.sha256((root / f["path"]).read_bytes()).hexdigest() == f["sha256"], f["path"]


def test_sound_degrades_silently_without_a_mixer(monkeypatch):
    from abuse_remake.game.neon import sound

    def boom(*a, **k):
        raise pygame.error("no audio device")

    monkeypatch.setattr(pygame.mixer, "get_init", lambda: False)
    monkeypatch.setattr(pygame.mixer, "init", boom)
    s = sound.Sound(enabled=True)
    assert not s.enabled
    s.play("pulse")
    s.music("combat")
    s.tick(0.1)


def test_every_event_sound_and_music_track_exists():
    from abuse_remake.game.neon import sound

    root = assets_root() / "neon"
    for name, (pattern, variants) in sound.BANKS.items():
        files = [root / (pattern.format(v) if v is not None else pattern) for v in variants]
        assert any(f.exists() for f in files), name
    for bank, _vol, _gap in sound.EVENTS.values():
        assert bank in sound.BANKS
    for track in sound.MUSIC.values():
        assert (root / track).exists(), track


def test_neon_handoff_to_classic_and_back_shares_one_recording(tmp_path):
    from abuse_remake.game.app import App
    from abuse_remake.game.human_replay import replay_human
    from abuse_remake.game.neon.app import NeonApp

    path = tmp_path / "mixed.jsonl"
    args = parse_args(["--mode", "neon", "--frames", "2", "--no-audio", "--scale", "1", "--record", str(path)])
    NeonApp(args).run()
    args._append_trace = True
    args.mode = "remastered"
    App(args).run()
    args.mode = "neon"
    NeonApp(args).run()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert sum(r["kind"] == "header" for r in rows) == 1
    assert replay_human(path)["mismatches"] == 0


# ---------------------------------------------------------------- shared screens (Remastered)
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
