"""Each campaign level can be finished under the ported rules: every saved route in
evidence/routes (found by scripts/route_search.py) replays to the level's end, exactly."""

import importlib.util
import json
from pathlib import Path

import pytest

from abuse_remake.engine import campaign
from abuse_remake.paths import repo_root

ROUTES = [p for p in sorted((Path(repo_root()) / "evidence" / "routes").glob("*.json"))
          if json.loads(p.read_text())["format"] == "campaign-route-1"]


def _module():
    spec = importlib.util.spec_from_file_location("route_search", Path(repo_root()) / "scripts" / "route_search.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("path", ROUTES, ids=[p.stem for p in ROUTES])
def test_a_saved_route_finishes_its_level(path):
    route = json.loads(path.read_text())
    assert route["format"] == "campaign-route-1" and campaign.playable(route["level"])
    mod = _module()
    g = mod.replay_route(route)
    assert mod.finished(g, route["goal"])
    assert not g.player_dead and g.frames == route["ticks"]


def test_every_playable_campaign_level_except_level_1_has_a_route():
    have = {json.loads(p.read_text())["level"] for p in ROUTES}
    assert {n for n in campaign.playable_levels() if n != "level01"} <= have


def test_playing_the_training_route_in_the_app_carries_on_and_the_trace_replays(tmp_path, monkeypatch):
    """A real exit, a real level change and a recorded session that replays exactly, with the
    level change verified (it follows an exit to that level)."""
    import pygame

    from abuse_remake.engine.view import Inputs
    from abuse_remake.game.app import App, parse_args
    from abuse_remake.game.human_replay import replay_human

    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    route = json.loads((Path(repo_root()) / "evidence" / "routes" / "level00.json").read_text())
    rec = tmp_path / "session.jsonl"
    app = App(parse_args(["--frames", "1", "--no-audio", "--seed", str(route["seed"]), "--scale", "1",
                          "--level", "level00", "--difficulty", route["difficulty"], "--record", str(rec)]))
    steps = [r[1:] for r in route["inputs"] for _ in range(r[0])]

    def inputs(tick):
        x, y, special, fire, dx, dy = steps[tick] if tick < len(steps) else (0, 0, 0, 0, 100, 0)
        p = app.game.player
        return Inputs(x=x, y=y, b1=special, b2=fire, pointer_x=p.x + dx, pointer_y=p.y - 20 + dy)

    app.scripted_inputs = inputs
    app.state = "play"
    for i in range(len(steps)):
        app.tick(i)
        if app.state != "play":
            break
    assert app.state == "complete" and app.next_level == "level01"
    hp = app.game.player.hp
    app.on_key(pygame.K_RETURN)
    assert app.level == "level01" and app.game.player.hp == hp and app.game.carried
    app.scripted_inputs = lambda tick: Inputs(x=1, pointer_x=app.game.player.x + 100, pointer_y=app.game.player.y - 20)
    for i in range(30):
        app.tick(i)
    app._check("session end")
    app.trace.close()
    out = replay_human(rec)
    assert out["mismatches"] == 0 and out["unverified_level_changes"] == 0 and out["checks"] == 2
    assert [(g["level"], g["reached_exit"]) for g in out["games"]] == [("level00", True), ("level01", False)]


def test_the_training_route_picks_up_all_four_power_ups():
    from abuse_remake.engine.game import Game
    from abuse_remake.engine.view import Inputs

    route = json.loads((Path(repo_root()) / "evidence" / "routes" / "level00.json").read_text())
    g = Game(seed=route["seed"], difficulty=route["difficulty"], level="level00", remastered=True)
    items = []
    steps = [r[1:] for r in route["inputs"] for _ in range(r[0])]
    for x, y, special, fire, dx, dy in steps:
        p = g.player
        g.step(Inputs(x=x, y=y, b1=special, b2=fire, pointer_x=p.x + dx, pointer_y=p.y - 20 + dy))
        items += [e.data["item"] for e in g.world.events if e.kind == "pickup"]
        if g.world.globals.get("level_complete"):
            break
    powers = ["sneaky", "fast", "fly", "ultra health"]
    assert [i for i in items if i in powers] == powers
