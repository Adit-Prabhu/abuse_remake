"""Remastered's campaign: the shareware training level, Level 1 and Level 2, joined by the levels'
own exits. Classic mode and the agent evaluations stay Level 1 only."""

import hashlib
import json
import zipfile
from dataclasses import replace

import pygame
import pytest

from abuse_remake.engine import campaign
from abuse_remake.engine.game import Game, _tiles
from abuse_remake.engine.view import Inputs
from abuse_remake.engine.world import Event
from abuse_remake.formats.level_file import load_level
from abuse_remake.paths import level_path, repo_root
from abuse_remake.scope import LEVEL00_TYPES, LEVEL01_TYPES, LEVEL02_TYPES

# SHA-256 of LEVELS/LEVEL00.SPE and LEVELS/LEVEL02.SPE inside the pinned shareware v1.01 zip
SHAREWARE_101 = {
    "level00": "e10aa633ab8b44f5fbe04f09bb1dfb6fd344582964d111204206c527a4c4ae39",
    "level02": "1118ff4af411fb600ec9ed4058a4ae259a49d3a113e3d0ad44299f85277dffd3",
}


def settle(g, n=5):
    p = g.player
    for _ in range(n):
        g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20))


def press_down_at_exit(g, aistate=None, ticks=6):
    """Stand in the level's exit and press the action key (down), as next_level_ai wants."""
    ex = g.world.find_type("NEXT_LEVEL")
    if aistate is not None:
        ex.set_aistate(aistate)
    p = g.player
    events = []
    for _ in range(ticks):
        p.x, p.y = ex.x, ex.y
        g.step(Inputs(y=1, pointer_x=p.x + 100, pointer_y=p.y - 20))
        events += g.world.events
        if g.world.globals.get("level_complete"):
            break
    return events


# --- the data ----------------------------------------------------------------------------------
def test_the_new_levels_are_the_shareware_101_files():
    """The pinned hashes are those of LEVELS/LEVEL00.SPE and LEVEL02.SPE in the shareware zip.
    When the zip is cached (scripts/compare_original_data.py fetches it), compare the bytes."""
    for name, digest in SHAREWARE_101.items():
        assert hashlib.sha256(level_path(name).read_bytes()).hexdigest() == digest
    zip_path = repo_root() / "cache" / "original-releases" / "ABUSE101.zip"
    if not zip_path.exists():
        pytest.skip("the shareware zip is not cached; run scripts/compare_original_data.py")
    with zipfile.ZipFile(zip_path) as z:
        for name in SHAREWARE_101:
            assert z.read(f"LEVELS/{name.upper()}.SPE") == level_path(name).read_bytes()


def test_scope_lists_exactly_the_types_in_each_campaign_level():
    for name, types in (("level00", LEVEL00_TYPES), ("level01", LEVEL01_TYPES), ("level02", LEVEL02_TYPES)):
        assert {o.type_name for o in load_level(level_path(name)).live_objects()} == set(types)


def test_every_tile_the_campaign_levels_use_exists_and_none_is_a_saved_game():
    tiles = _tiles()
    for name in campaign.LEVELS:
        lf = load_level(level_path(name))
        assert {v & 0x3FFF for v in lf.fg} - {0} <= set(tiles.fore), name
        assert set(lf.bg) - {0} <= set(tiles.back), name
        assert not lf.has_player_info, name  # so a level change takes the level.c:1815-1835 path


def test_each_level_exit_names_the_next_level():
    # people.lsp:917-921 loads "levels/level" + (digstr (aistate) 2) + ".spe"; 22 ends the game
    assert campaign.exits("level00") == (1, 2, 3, 4)  # the training level's portal room
    assert campaign.exits("level01") == (2,)
    assert campaign.exits("level02") == (3,)
    assert [campaign.exit_level(n) for n in (1, 2, 3)] == ["level01", "level02", "level03"]
    assert campaign.exit_level(campaign.END_LEVEL) is None
    assert campaign.in_build("level02") and not campaign.in_build("level03")
    assert campaign.unported("level03") and not campaign.playable("level03")


def test_what_each_exit_does():
    two = "open" if campaign.playable("level02") else None
    assert campaign.exit_result("level00", 1) == "open"
    assert campaign.exit_result("level00", 2) == (two or "locked")  # portal 1 is open, so it waits
    assert campaign.exit_result("level00", 3) == "locked"
    assert campaign.exit_result("level01", 2) == (two or "end")  # Level 1 can always be finished
    assert campaign.exit_result("level02", 3) == "end"  # the end of this build's campaign
    assert campaign.exit_result("level02", campaign.END_LEVEL) == "end"


# --- strict loading ----------------------------------------------------------------------------
def test_strict_loading_checks_the_level_it_loads():
    assert campaign.unported("level01") == {}
    Game(level="level01")  # Level 1 is complete
    for name in ("level00", "level02"):
        missing = campaign.unported(name)
        if missing:
            with pytest.raises(NotImplementedError) as err:
                Game(level=name)
            assert all(t in str(err.value) for t in missing)
            assert not campaign.playable(name)
        else:
            Game(level=name, remastered=True)
            assert campaign.playable(name)


# --- a level change ----------------------------------------------------------------------------
def test_a_level_change_keeps_health_weapons_and_the_random_table():
    old = Game(seed=3, remastered=True)
    settle(old)
    old.player.set_hp(57)
    old.view.give_weapon(1)
    old.view.add_ammo(1, 7)
    old.view.select_weapon(1)
    settle(old, 2)
    old.player.lvars["special_power"] = 1  # FAST_POWER
    old.view.ambient = 12
    old.player.set_aistate_time(9)
    rand_on = old.world.rng.rand_on
    new = Game(seed=99, level="level01", remastered=True, carry=old)
    p = new.player
    assert p.hp == 57 and new.carried and not old.carried
    assert new.view.weapons == old.view.weapons and new.view.current_weapon == 1
    assert new.world.rng.rand_on == rand_on  # rand_on is global in the original
    # set_player_defaults runs on every level load (people.lsp:101-115)
    assert p.lvars["special_power"] == 0 and p.aistate == 0 and p.aistate_time == 0
    assert new.view.ambient == 35
    start = new.world.find_type("START")
    assert (p.x, p.y) == (start.x, start.y) and p.objs == []
    settle(new, 2)  # cop_mover makes a new top half; its top_ai picks the weapon on the next tick
    assert p.objs and p.objs[0].ctype is new.world.weapon_types[1]
    assert old.player.objs and old.player.hp == 57  # the old game is left as it was


def test_a_saved_game_level_cannot_be_carried_into(monkeypatch):
    import abuse_remake.engine.game as game_mod

    real = game_mod._level
    monkeypatch.setattr(game_mod, "_level", lambda name: replace(real(name), has_player_info=True))
    with pytest.raises(ValueError):
        Game(level="level01", remastered=True, carry=Game(seed=1, remastered=True))


def test_level_1_exit_ends_the_level_and_the_campaign_goes_on_only_if_level_2_plays():
    g = Game(seed=0, remastered=True)
    settle(g)
    events = press_down_at_exit(g)  # Level 1's exit has aistate 2
    assert g.world.globals["level_complete"] and not [e for e in events if e.kind == "level_locked"]
    if campaign.playable("level02"):
        assert g.world.globals["next_level"] == "level02"
    else:
        assert "next_level" not in g.world.globals  # the end of the campaign in this build


def test_an_exit_stays_shut_when_another_exit_of_the_level_can_be_played(monkeypatch):
    monkeypatch.setattr(campaign, "exits", lambda name: (1, 3))  # as in the training level
    g = Game(seed=0, remastered=True)
    settle(g)
    events = press_down_at_exit(g, aistate=3)
    assert not g.world.globals.get("level_complete") and "next_level" not in g.world.globals
    assert [e.data["level"] for e in events if e.kind == "level_locked"][:1] == ["level03"]
    # an open exit and a shut one touched in the same tick: the open one wins
    w = g.world
    w.events[:] = [Event("level_complete", {"next_level": 3}), Event("level_complete", {"next_level": 1})]
    w.globals["level_complete"] = True
    g.remastered._follow_exits()
    assert w.globals["level_complete"] and w.globals["next_level"] == "level01"


def test_classic_level_1_exit_still_just_ends_the_level():
    g = Game(seed=0)
    settle(g)
    press_down_at_exit(g, aistate=3)
    assert g.world.globals["level_complete"] and "next_level" not in g.world.globals


# --- the app -----------------------------------------------------------------------------------
@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    return tmp_path


def make_app(*extra):
    from abuse_remake.game.app import App, parse_args

    return App(parse_args(["--frames", "1", "--no-audio", "--seed", "1", "--scale", "1", *extra]))


def test_level_choice_is_remastered_only():
    from abuse_remake.game.app import parse_args

    assert parse_args([]).level == "level01"
    for name in campaign.LEVELS:
        if campaign.playable(name):
            assert parse_args(["--level", name]).level == name
        else:
            with pytest.raises(SystemExit):
                parse_args(["--level", name])
    with pytest.raises(SystemExit):
        parse_args(["--mode", "classic", "--level", "level02"])
    with pytest.raises(SystemExit):
        parse_args(["--horde", "--level", "level00"])
    with pytest.raises(SystemExit):
        parse_args(["--playtest", "--level", "level00"])


def to_exit(app):
    """Scripted inputs that stand the player in the level's exit and press down (a test
    shortcut: the teleport is not an input, so such a session cannot be replayed)."""
    ex = app.game.world.find_type("NEXT_LEVEL")

    def inputs(tick):
        p = app.game.player
        p.x, p.y = ex.x, ex.y
        return Inputs(y=1, pointer_x=p.x + 100, pointer_y=p.y - 20)
    return inputs


def play_until_not_playing(app, ticks=8):
    for i in range(ticks):
        if app.state != "play":
            break
        app.tick(i)


def test_title_cycles_the_start_level_through_playable_levels_only(home):
    app = make_app()
    app.state = "title"
    seen = []
    for _ in range(4):
        app.on_key(pygame.K_l)
        seen.append(app.level)
    assert set(seen) == {n for n in campaign.LEVELS if campaign.playable(n)}
    classic = make_app("--mode", "classic")
    classic.state = "title"
    classic.on_key(pygame.K_l)
    assert classic.level == "level01" and classic.game.world.level.path.endswith("level01.spe")
    playtest = make_app()
    playtest.args.playtest = True  # a playtest session that switched to Remastered stays on Level 1
    playtest.state = "title"
    playtest.on_key(pygame.K_l)
    assert playtest.level == "level01"


def test_the_app_carries_on_to_the_next_level_and_a_restart_there_is_at_full_health(home, tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "exit_level", lambda n: "level01")  # Level 1 leads to itself here
    rec = tmp_path / "session.jsonl"
    app = make_app("--record", str(rec))
    app.state = "play"
    for i in range(5):
        app.tick(i)
    app.game.player.set_hp(61)
    app.scripted_inputs = to_exit(app)
    play_until_not_playing(app)
    assert app.state == "complete" and app.next_level == "level01"
    first = app.game
    app.on_key(pygame.K_RETURN)
    assert app.state == "play" and app.game is not first and app.game.player.hp == 61
    assert app.stats["ticks"] == 0 and app.checkpoint is app.level_start and app.record_level == "campaign-level01"
    app.trace.flush()
    rows = [json.loads(x) for x in rec.read_text().splitlines()]
    assert [r for r in rows if r["kind"] == "level"] == [{"kind": "level", "level": "level01"}]
    app.state = "dead"  # no console save in this level: back to its start, at full health
    app.on_key(pygame.K_SPACE)
    assert app.game.player.hp == 100  # restart_player (people.lsp:515-520)


def test_app_trace_replay_round_trip_across_a_level_change_and_a_restart(home, tmp_path, monkeypatch):
    from abuse_remake.game.human_replay import replay_human

    monkeypatch.setattr(campaign, "exit_level", lambda n: "level01")
    rec = tmp_path / "session.jsonl"
    app = make_app("--record", str(rec))
    app.state = "play"
    for i in range(30):
        app.tick(i)  # the app's own wandering inputs, all recorded
    app.game.world.globals.update(level_complete=True, next_level="level01")  # outputs, not hashed
    play_until_not_playing(app, 1)
    assert app.state == "complete"
    app.on_key(pygame.K_RETURN)  # change_level: carry, snap the camera, a level row
    for i in range(25):
        app.tick(i)
    app.state = "paused"
    app.on_key(pygame.K_r)  # restart this level: its carried start, at full health
    for i in range(20):
        app.tick(i)
    app._check("session end")
    app.trace.close()
    out = replay_human(rec)
    assert out["checks"] == 3 and out["mismatches"] == 0  # level end, before the restart, session end
    assert [g["level"] for g in out["games"]] == ["level01", "level01"]
    assert "progress" in out["games"][0] and "progress" not in out["games"][1]  # carried: not scored


def test_a_finished_campaign_returns_to_the_title(home, monkeypatch):
    monkeypatch.setattr(campaign, "playable", lambda name: name == "level01")  # nothing after Level 1
    app = make_app()
    app.state = "play"
    app.scripted_inputs = to_exit(app)
    play_until_not_playing(app)
    assert app.state == "complete" and app.next_level is None and app.finish["new_best"]
    app.on_key(pygame.K_RETURN)
    assert app.state == "title"
