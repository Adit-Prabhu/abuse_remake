"""Each level can be finished under the ported rules: every saved route in evidence/routes
replays to the level's end, exactly. Level 1's (the graded level) is under Classic rules, from
START. The training route was found by scripts/route_search.py; Level 1's and Level 2's were
built from searched segments. evidence/routes/solver/ holds the solver's result for each of the
evaluation's checkpoint situations, from the scenario's own start."""

import importlib.util
import json
from pathlib import Path

import pytest

from abuse_remake.engine import campaign
from abuse_remake.paths import repo_root

ROUTES = [p for p in sorted((Path(repo_root()) / "evidence" / "routes").glob("*.json"))
          if json.loads(p.read_text())["format"] == "campaign-route-1"]
SOLVER = sorted((Path(repo_root()) / "evidence" / "routes" / "solver").glob("*.json")) + [
    Path(repo_root()) / "evidence" / "routes" / "level01.json"]  # the full level is the `level01` situation, seed 0


def _situation(path: Path) -> str:
    """solver/<scenario>-s<seed>.json, or the full-level route itself."""
    return path.stem.rsplit("-s", 1)[0] if path.parent.name == "solver" else "level01"


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
    assert mod.finished(g, route["goal"], route.get("mode", "remastered"))
    assert not g.player_dead and g.frames == route["ticks"]


def test_every_playable_level_has_a_route_and_level_1_s_is_classic():
    have = {json.loads(p.read_text())["level"]: json.loads(p.read_text()) for p in ROUTES}
    assert set(campaign.playable_levels()) <= set(have)
    assert have["level01"]["mode"] == "classic" and "start" not in have["level01"]


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
    assert app.state == "complete" and app.next_level == route["goal"]
    hp = app.game.player.hp
    app.on_key(pygame.K_RETURN)
    assert app.level == route["goal"] and app.game.player.hp == hp and app.game.carried
    app.scripted_inputs = lambda tick: Inputs(x=1, pointer_x=app.game.player.x + 100, pointer_y=app.game.player.y - 20)
    for i in range(30):
        app.tick(i)
    app._check("session end")
    app.trace.close()
    out = replay_human(rec)
    assert out["mismatches"] == 0 and out["unverified_level_changes"] == 0 and out["checks"] == 2
    assert [(g["level"], g["reached_exit"]) for g in out["games"]] == [("level00", True), (route["goal"], False)]


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


def test_the_level_2_route_picks_up_its_three_placed_power_ups():
    from abuse_remake.engine.game import Game
    from abuse_remake.engine.view import Inputs

    route = json.loads((Path(repo_root()) / "evidence" / "routes" / "level02.json").read_text())
    g = Game(seed=route["seed"], difficulty=route["difficulty"], level="level02", remastered=True)
    items = []
    steps = [r[1:] for r in route["inputs"] for _ in range(r[0])]
    for x, y, special, fire, dx, dy in steps:
        p = g.player
        g.step(Inputs(x=x, y=y, b1=special, b2=fire, pointer_x=p.x + dx, pointer_y=p.y - 20 + dy))
        items += [e.data["item"] for e in g.world.events if e.kind == "pickup"]
        if g.world.globals.get("level_complete"):
            break
    powers = ["ultra health", "sneaky", "fly"]
    assert [i for i in items if i in powers] == powers


@pytest.mark.parametrize("path", SOLVER, ids=[p.stem for p in SOLVER])
def test_a_solver_route_wins_its_scenario_under_classic_rules(path):
    """The privileged solver's result for a reported situation (EVALUATION.md): a route that
    starts where the agents' scenario starts and reaches the exit, under Classic rules, within
    the scenario's tick limit."""
    from abuse_remake.agent.interface import SCENARIOS

    route = json.loads(path.read_text())
    scenario = SCENARIOS[_situation(path)]
    if path.parent.name == "solver":
        assert path.stem.endswith(f"-s{route['seed']}")
    assert route["mode"] == "classic" and route["level"] == "level01" and route["difficulty"] == "hard"
    if scenario.start is None:
        assert "start" not in route
    else:
        assert tuple(route["start"]) == scenario.start
    mod = _module()
    g = mod.replay_route(route)
    assert g.remastered is None  # the replay really ran Classic (Remastered Level 1 would also finish)
    assert mod.finished(g, route["goal"], "classic") and not g.player_dead
    assert g.frames == route["ticks"] <= scenario.max_ticks


def test_every_reported_situation_has_a_solver_route_and_none_is_lost():
    """Seed 0 for every situation; on the other reported seeds the solver crossed the turret room
    only for cp2 (seed 1) and cp3 (seeds 1, 2): EVALUATION.md reports exactly this set, and a
    deleted route fails here."""
    import tomllib

    from abuse_remake.agent.interface import SCENARIOS

    suite = tomllib.loads((Path(repo_root()) / "eval" / "configs" / "midterm.toml").read_text())
    have = {(_situation(p), json.loads(p.read_text())["seed"]) for p in SOLVER}
    assert {s for s, _ in have} == set(SCENARIOS) == set(suite["scenarios"])
    assert have == {("level01", 0), ("level01-cp1", 0), ("level01-cp2", 0), ("level01-cp2", 1),
                    ("level01-cp3", 0), ("level01-cp3", 1), ("level01-cp3", 2)}


def test_the_solver_starts_a_checkpoint_exactly_as_the_agents_scenario_does():
    """route_search.place copies AbuseEpisode.reset; if reset changes, the solver's routes would
    stop saying anything about the agents' scenarios."""
    from abuse_remake.agent.interface import SCENARIOS, AbuseEpisode
    from abuse_remake.engine.game import Game

    mod = _module()
    for name, sc in SCENARIOS.items():
        ep = AbuseEpisode(name, seed=1)
        g = Game(seed=1, difficulty="hard", level="level01", remastered=False)
        if sc.start is not None:
            mod.place(g, sc.start)
        a, b = ep._game, g
        assert a.state_hash() == b.state_hash()
        assert (a.player.x, a.player.y, a.player.last_x, a.player.last_y) == \
               (b.player.x, b.player.y, b.player.last_x, b.player.last_y)
        assert (a.view.last_x, a.view.last_y, a.view.last_last_x, a.view.last_last_y) == \
               (b.view.last_x, b.view.last_y, b.view.last_last_x, b.view.last_last_y)
