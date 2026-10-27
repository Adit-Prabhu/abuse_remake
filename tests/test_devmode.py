"""Developer test mode: the student's testing tool (no damage, unlimited ammo for guns 1-4, any
power-up from a menu), locked to the machine that holds the key. Headless (SDL dummy drivers)."""

import hashlib
import subprocess
from pathlib import Path

import pygame
import pytest

from abuse_remake.engine.game import Game
from abuse_remake.engine.view import MAX_AMMO, Inputs

ROOT = Path(__file__).resolve().parents[1]
SECRET = b"a test secret, not the student's"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    return tmp_path


@pytest.fixture
def key(home, monkeypatch):
    """This test's own key: the committed hash is the student's, whose secret never leaves their
    machine."""
    from abuse_remake.game import devmode

    monkeypatch.setattr(devmode, "KEY_SHA256", hashlib.sha256(SECRET).hexdigest())
    (home / "dev.key").write_bytes(SECRET + b"\n")
    return home


def make_app(*extra):
    from abuse_remake.game.app import App, parse_args

    return App(parse_args(["--frames", "1", "--no-audio", "--seed", "3", "--scale", "2", *extra]))


def key_down(app, k):
    return app.on_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))


# --- the lock --------------------------------------------------------------------------------------
def test_without_the_key_dev_is_an_unknown_option_and_never_mentioned(home, capsys):
    from abuse_remake.game.app import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--dev"])
    assert "unrecognized arguments: --dev" in capsys.readouterr().err  # as for any made-up option
    with pytest.raises(SystemExit):
        parse_args(["--help"])
    assert "dev" not in capsys.readouterr().out.lower()
    assert make_app().dev is False


def test_a_wrong_or_empty_key_does_not_unlock_it(home, capsys):
    from abuse_remake.game import devmode
    from abuse_remake.game.app import parse_args

    for content in (b"guess", b"", devmode.KEY_SHA256.encode()):  # not even the hash itself
        (home / "dev.key").write_bytes(content)
        assert not devmode.unlocked()
        with pytest.raises(SystemExit):
            parse_args(["--dev"])
        assert "unrecognized arguments: --dev" in capsys.readouterr().err


def test_the_key_unlocks_dev_for_remastered_only_and_never_with_traces(key, capsys):
    from abuse_remake.game.app import parse_args

    assert parse_args(["--dev"]).dev is True
    assert parse_args(["--dev", "--horde"]).dev is True
    assert parse_args([]).dev is False  # the key alone changes nothing
    for extra in (["--mode", "classic"], ["--playtest"], ["--record", str(key / "t.jsonl")]):
        with pytest.raises(SystemExit):
            parse_args(["--dev", *extra])
        assert "--dev" in capsys.readouterr().err


def test_no_key_is_ever_in_the_repository():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert not [p for p in tracked.splitlines() if p.endswith(".key")]
    from abuse_remake.game import devmode

    assert len(devmode.KEY_SHA256) == 64 and int(devmode.KEY_SHA256, 16) >= 0  # a hash, not a secret


# --- the rules (engine) ----------------------------------------------------------------------------
def settle(g, n):
    for _ in range(n):
        g.step(Inputs())


def test_dev_rules_need_remastered_and_classic_and_agents_never_have_them():
    from abuse_remake.agent.interface import PLAYER_ID, AbuseEpisode

    with pytest.raises(ValueError):
        Game(seed=0, dev=True)
    assert Game(seed=0, remastered=True).remastered.dev is None
    ep = AbuseEpisode("level01", seed=0)
    ep.step(PLAYER_ID, "explore right")
    assert ep._game.remastered is None  # evaluations: Classic rules, so never dev


def test_dev_health_takes_no_damage_and_stays_full_and_can_be_switched_off():
    g = Game(seed=0, remastered=True, dev=True)
    settle(g, 3)
    p = g.player
    p.do_damage(60, None, p.x, p.y, 0, 0)
    g.step(Inputs())
    p.do_damage(60, None, p.x, p.y, 0, 0)
    settle(g, 3)
    assert p.hp == 100 and p.aistate < 3  # two hits that would have killed: nothing
    g.remastered.dev["health"] = False
    settle(g, 1)
    p.do_damage(30, None, p.x, p.y, 0, 0)
    assert p.hp < 100  # off: damage applies again
    plain = Game(seed=0, remastered=True)
    settle(plain, 3)
    plain.player.do_damage(30, None, plain.player.x, plain.player.y, 0, 0)
    assert plain.player.hp < 100


def test_dev_ammo_gives_guns_1_to_4_and_keeps_them_full_while_firing():
    g = Game(seed=0, remastered=True, dev=True)
    g.step(Inputs())
    assert g.view.weapons[:4] == [MAX_AMMO] * 4
    assert g.view.weapons[4:] == [-1] * (len(g.view.weapons) - 4)  # the unported add-on weapons stay out
    p = g.player
    for _ in range(30):
        g.step(Inputs(b2=1, pointer_x=p.x + 80, pointer_y=p.y - 20), None)
    assert g.view.weapons[:4] == [MAX_AMMO] * 4
    g.remastered.dev["ammo"] = False
    from abuse_remake.engine.game import WeaponCommand

    g.step(Inputs(), WeaponCommand(select=1))  # grenades
    for _ in range(30):
        g.step(Inputs(b2=1, pointer_x=p.x + 80, pointer_y=p.y - 20))
    assert g.view.weapons[1] < MAX_AMMO  # off: shots use ammo again


def test_dev_settings_live_in_the_snapshot():
    g = Game(seed=0, remastered=True, dev=True)
    snap = g.snapshot()
    g.remastered.dev["ammo"] = False
    g.restore(snap)
    assert g.remastered.dev == {"health": True, "ammo": True}


# --- the app ---------------------------------------------------------------------------------------
def test_tab_opens_the_dev_menu_only_in_dev_mode(key):
    plain = make_app()
    plain.state = "play"
    key_down(plain, pygame.K_TAB)
    assert plain.state == "play"
    app = make_app("--dev")
    app.state = "play"
    key_down(app, pygame.K_TAB)
    assert app.state == "dev"
    frames = app.game.frames
    app.advance(1.0)
    assert app.game.frames == frames  # the game waits while the menu is up
    key_down(app, pygame.K_ESCAPE)
    assert app.state == "play"


def go_to(app, key, power=None):
    """Down the dev menu to a line; it must be there."""
    from abuse_remake.game.screens import dev_items

    for _ in range(len(dev_items(app))):
        if (app.dev_item()["key"], app.dev_item().get("power")) == (key, power):
            return
        key_down(app, pygame.K_DOWN)
    raise AssertionError(f"no {key} {power} line in the dev menu")


def test_the_dev_menu_gives_any_power_up_and_switches_health_and_ammo(key):
    from abuse_remake.engine.behaviors.player import FAST_POWER, FLY_POWER, HEALTH_POWER, NO_POWER, SNEAKY_POWER

    app = make_app("--dev")
    app.state = "play"
    p = app.game.player
    for power in (FAST_POWER, FLY_POWER, SNEAKY_POWER, HEALTH_POWER, NO_POWER):
        key_down(app, pygame.K_TAB)
        go_to(app, "power", power)
        key_down(app, pygame.K_RETURN)
        assert app.state == "play" and p.lvars["special_power"] == power  # given, and back to the game
        if power:
            assert app.mhud.banner is not None and app.mhud.banner["power"] == power  # how to use it
    key_down(app, pygame.K_TAB)
    go_to(app, "ammo")
    key_down(app, pygame.K_RIGHT)
    assert app.game.remastered.dev["ammo"] is False and app.dev_item()["value"] == "OFF"
    go_to(app, "health")
    key_down(app, pygame.K_RETURN)
    assert app.game.remastered.dev["health"] is False and app.state == "dev"


def test_dev_settings_carry_on_through_restarts_and_into_the_next_level(key):
    app = make_app("--dev", "--level", "level00")
    app.state = "play"
    app.dev_opts["ammo"] = False
    app._apply_dev()
    app._restore("level_start")
    assert app.game.remastered.dev == {"health": True, "ammo": False}
    app.change_level("level01")
    assert app.game.remastered.dev == {"health": True, "ammo": False}


def test_dev_runs_never_save_times_ghosts_or_scores(key):
    from abuse_remake.game.remaster import data_dir

    app = make_app("--dev")
    app.state = "play"
    app.game.world.globals["level_complete"] = True
    app.tick(0)
    assert app.state == "complete" and app.finish == {"dev": True}
    h = make_app("--dev", "--horde")
    h.state = "play"
    h.game.horde.state["over"] = True
    h.tick(0)
    assert h.state == "horde_over" and h.finish == {"dev": True}
    assert any("NOT RECORDED" in line for line in h.horde_over_lines())
    saved = {p.name for p in data_dir().iterdir()}
    assert not saved & {"records.json", "horde.json"} and not any(n.startswith("ghost-") for n in saved)


def test_classic_on_the_title_plays_without_dev_rules(key):
    app = make_app("--dev")
    app._set_mode("classic")
    assert app.game.remastered is None
    app._set_mode("remastered")
    assert app.game.remastered.dev == {"health": True, "ammo": True}


def test_the_hud_says_dev_mode_and_shows_endless_ammo(key, monkeypatch):
    def drawn(app):
        said = []
        real = app.mhud.t.text
        monkeypatch.setattr(app.mhud.t, "text",
                            lambda surf, text, *a, **k: said.append(text) or real(surf, text, *a, **k))
        app.state = "play"
        app.tick(0)
        app.draw()
        return said

    plain = drawn(make_app())
    assert "DEV MODE" not in plain and chr(236) in plain  # the laser's own infinity, as before
    app = make_app("--dev")
    said = drawn(app)
    assert "DEV MODE" in said and "TAB" in said
    assert said.count(chr(236)) == 4 and str(MAX_AMMO) not in said  # guns 1-4: endless, not "999"
    app.dev_opts["ammo"] = False
    app._apply_dev()
    assert str(MAX_AMMO) in drawn(app)


@pytest.mark.parametrize("scale", ["1", "2", "3"])
def test_every_dev_screen_draws(key, scale):
    from abuse_remake.game.app import App, parse_args

    for extra in ([], ["--horde"]):
        app = App(parse_args(["--frames", "1", "--no-audio", "--seed", "3", "--scale", scale, "--dev", *extra]))
        for state in ("title", "play", "dev", "paused"):
            app.state = state
            app.draw()
