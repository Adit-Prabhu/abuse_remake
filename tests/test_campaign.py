"""Remastered's campaign: the shareware training level, Level 1 and Level 2, joined by the levels'
own exits. Classic mode and the agent evaluations stay Level 1 only."""

import hashlib
import json

import pygame
import pytest

from abuse_remake.engine import campaign
from abuse_remake.engine.game import Game, _tiles
from abuse_remake.engine.view import Inputs
from abuse_remake.formats.level_file import load_level
from abuse_remake.paths import level_path
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
    for name, digest in SHAREWARE_101.items():
        assert hashlib.sha256(level_path(name).read_bytes()).hexdigest() == digest


def test_scope_lists_exactly_the_types_in_each_campaign_level():
    for name, types in (("level00", LEVEL00_TYPES), ("level01", LEVEL01_TYPES), ("level02", LEVEL02_TYPES)):
        assert {o.type_name for o in load_level(level_path(name)).live_objects()} == set(types)


def test_every_tile_the_campaign_levels_use_exists():
    tiles = _tiles()
    for name in campaign.LEVELS:
        lf = load_level(level_path(name))
        assert {v & 0x3FFF for v in lf.fg} - {0} <= set(tiles.fore), name
        assert set(lf.bg) - {0} <= set(tiles.back), name


def test_the_training_level_ends_in_the_original_portal_room():
    # people.lsp:921 loads "levels/level" + (digstr (aistate) 2) + ".spe"
    exits = load_level(level_path("level00")).objects_of("NEXT_LEVEL")
    assert {o.vars["aistate"] for o in exits} == {1, 2, 3, 4}
    assert [campaign.exit_level(n) for n in (1, 2, 3)] == ["level01", "level02", "level03"]
    assert campaign.in_build("level02") and not campaign.in_build("level03")


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
    rand_on = old.world.rng.rand_on
    new = Game(seed=99, level="level01", remastered=True, carry=old)
    p = new.player
    assert p.hp == 57
    assert new.view.weapons == old.view.weapons and new.view.current_weapon == 1
    assert new.world.rng.rand_on == rand_on  # rand_on is global in the original
    assert p.lvars["special_power"] == 0  # set_player_defaults runs on every level load
    start = new.world.find_type("START")
    assert (p.x, p.y) == (start.x, start.y) and p.objs == []  # unlinked from the old top half
    settle(new, 2)  # cop_mover makes a new top half; its top_ai picks the weapon on the next tick
    assert p.objs and p.objs[0].ctype is new.world.weapon_types[1]
    assert old.player.objs and old.player.hp == 57  # the old game is left as it was


def test_remastered_locks_exits_to_levels_outside_the_build():
    g = Game(seed=0, remastered=True)
    settle(g)
    events = press_down_at_exit(g, aistate=3)
    assert not g.world.globals.get("level_complete")
    assert [e.data["level"] for e in events if e.kind == "level_locked"][:1] == ["level03"]
    assert "next_level" not in g.world.globals


def test_remastered_records_where_an_open_exit_leads(monkeypatch):
    monkeypatch.setattr(campaign, "playable", lambda name: name in ("level01", "level02"))
    g = Game(seed=0, remastered=True)
    settle(g)
    press_down_at_exit(g)  # Level 1's exit has aistate 2
    assert g.world.globals["level_complete"] and g.world.globals["next_level"] == "level02"


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


def test_title_cycles_the_start_level_through_playable_levels_only(home, monkeypatch):
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


def test_the_app_carries_on_to_the_next_level(home, tmp_path, monkeypatch):
    # Level 2 is not playable yet, so let Level 1's exit lead back into Level 1 for this test
    monkeypatch.setattr(campaign, "exit_level", lambda n: "level01")
    rec = tmp_path / "session.jsonl"
    app = make_app("--record", str(rec))
    app.state = "play"
    for i in range(5):
        app.tick(i)
    app.game.player.set_hp(61)
    ex = app.game.world.find_type("NEXT_LEVEL")

    def to_exit(tick):
        p = app.game.player
        p.x, p.y = ex.x, ex.y  # a test shortcut, not an input
        return Inputs(y=1, pointer_x=p.x + 100, pointer_y=p.y - 20)

    app.scripted_inputs = to_exit
    for i in range(6):
        if app.state != "play":
            break
        app.tick(i)
    assert app.state == "complete" and app.next_level == "level01"
    first = app.game
    app.on_key(pygame.K_RETURN)
    assert app.state == "play" and app.game is not first and app.game.player.hp == 61
    assert app.stats["ticks"] == 0 and app.checkpoint is app.level_start
    app.trace.flush()
    rows = [json.loads(x) for x in rec.read_text().splitlines()]
    assert [r for r in rows if r["kind"] == "level"] == [{"kind": "level", "level": "level01"}]


def test_a_human_trace_follows_a_level_change(tmp_path):
    from abuse_remake.game.human_replay import replay_human

    def inputs(i, p):
        return Inputs(x=1 if i % 20 < 14 else -1, y=-1 if i % 17 == 0 else 0, b2=int(i % 5 == 0),
                      pointer_x=p.x + 100, pointer_y=p.y - 20)

    g = Game(seed=5, remastered=True)
    rows = [{"kind": "header", "game": "abuse_remake", "level": "level01", "player": "human",
             "format": "human-trace-1"},
            {"kind": "new_game", "seed": 5, "difficulty": "hard", "mode": "remastered", "horde": False,
             "rules": "remastered", "level": "level01"}]
    for i in range(40):
        inp = inputs(i, g.player)
        g.step(inp)
        rows.append({"kind": "input", "tick": i + 1, "x": inp.x, "y": inp.y, "b1": 0, "b2": inp.b2,
                     "px": inp.pointer_x, "py": inp.pointer_y})
    rows.append({"kind": "level", "level": "level01"})
    g = Game(seed=5, level="level01", remastered=True, carry=g)
    for i in range(30):
        inp = inputs(i + 7, g.player)
        g.step(inp)
        rows.append({"kind": "input", "tick": i + 1, "x": inp.x, "y": inp.y, "b1": 0, "b2": inp.b2,
                     "px": inp.pointer_x, "py": inp.pointer_y})
    rows.append({"kind": "check", "why": "session end", "frames": g.frames, "state_hash": g.state_hash()})
    rec = tmp_path / "t.jsonl"
    rec.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = replay_human(rec)
    assert out["checks"] == 1 and out["mismatches"] == 0
    assert [(x["level"], x["ticks"]) for x in out["games"]] == [("level01", 40), ("level01", 30)]


def test_a_finished_campaign_returns_to_the_title(home):
    app = make_app()
    app.state = "play"
    app.game.world.globals["level_complete"] = True
    app.tick(0)
    assert app.state == "complete" and app.next_level is None
    app.on_key(pygame.K_RETURN)
    assert app.state == "title"
