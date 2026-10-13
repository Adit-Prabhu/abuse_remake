"""The playing agent's interface: operations, information boundary, invalid actions, budgets."""

import json
import sys

import pytest

from abuse_remake.agent.interface import PLAYER_ID, AbuseEpisode, Budgets
from abuse_remake.agent.observation import KINDS
from abuse_remake.agent.players.baselines import RandomPlayer, ScriptedPlayer
from abuse_remake.agent.protocol import InProcessPlayer, ProcessPlayer
from abuse_remake.agent.runner import run_episode

FORBIDDEN_KEYS = {"aistate", "aistate_time", "lvars", "uid", "rand_on", "links", "objs", "hp_enemy",
                  "xacel", "yacel", "fxvel", "fyvel", "type_name", "ctype", "level_index"}


def walk(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + (k,), k, v
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (i,))


def test_five_operations_and_observation_shape():
    ep = AbuseEpisode("level01", seed=0)
    obs = ep.reset(0)
    assert obs["schema"] == "abuse-obs-1" and obs["status"] == "playing"
    assert set(obs) >= {"player", "view", "tiles", "objects", "events", "last_result", "tick", "ticks_left"}
    assert obs["view"]["w"] == 316 and obs["view"]["h"] == 162  # the original play view
    assert isinstance(ep.legal_actions(PLAYER_ID), list)
    assert ep.outcome()["status"] == "ongoing"
    json.dumps(obs)  # plain JSON only
    with pytest.raises(ValueError):
        ep.observe("someone_else")


def test_observation_exposes_nothing_internal():
    ep = AbuseEpisode("level01", seed=1)
    for action in ["attack W10", "explore right", "explore right", "explore right"]:
        if action in ep.legal_actions(PLAYER_ID):
            ep.step(PLAYER_ID, action)
        else:
            ep.step(PLAYER_ID, "explore right")
    obs = ep.observe(PLAYER_ID)
    for path, key, _ in walk(obs):
        assert key not in FORBIDDEN_KEYS, path
    for o in obs["objects"]:
        assert "hp" not in o and o["kind"] in set(KINDS.values())


def test_only_on_screen_and_drawn_objects_are_visible():
    ep = AbuseEpisode("level01", seed=2)
    for _ in range(6):
        ep.step(PLAYER_ID, "explore right")
    obs = ep.observe(PLAYER_ID)
    v = obs["view"]
    game = ep._game  # the runner side may look; the test checks what the player gets
    shown = {(o["x"], o["y"]) for o in obs["objects"]}
    for o in game.world.objects:
        x1, y1, x2, y2 = o.picture_space()
        on_screen = not (x2 < v["x"] or x1 > v["x"] + v["w"] - 1 or y2 < v["y"] or y1 > v["y"] + v["h"] - 1)
        if not on_screen:
            assert (o.x, o.y) not in shown or any(
                p.x == o.x and p.y == o.y for p in game.world.objects if p is not o)
        if o.ctype.name in ("SENSOR", "GATE_AND", "GATE_DELAY", "HIDDEN_ANT", "DEATH_SENSOR", "AMBIENT_SOUND"):
            assert o.ctype.name not in KINDS  # invisible in play: never reported


def test_legal_actions_only_name_visible_objects():
    ep = AbuseEpisode("level01", seed=0)
    for _ in range(4):
        ep.step(PLAYER_ID, "explore right")
    obs = ep.observe(PLAYER_ID)
    ids = {o["id"] for o in obs["objects"]}
    for a in ep.legal_actions(PLAYER_ID):
        parts = a.split()
        if parts[0] in ("attack", "goto", "use"):
            assert parts[1] in ids


@pytest.mark.parametrize("bad", ["fly away", "", "attack Z99", None, 42, {"action": "wait"}, "weapon rocket"])
def test_invalid_actions_are_refused_counted_and_change_nothing(bad):
    ep = AbuseEpisode("level01", seed=0)
    before = ep._game.state_hash()
    r = ep.step(PLAYER_ID, bad)
    assert r["accepted"] is False and r["ticks"] == 0 and r["error"]
    assert ep._game.state_hash() == before
    assert ep.invalid_actions == 1 and ep.decisions == 1
    assert r["observation"]["last_result"]["accepted"] is False
    assert r["observation"]["last_result"]["error"] == r["error"]


def test_accepted_actions_advance_the_game():
    ep = AbuseEpisode("level01", seed=0)
    r = ep.step(PLAYER_ID, "wait")
    assert r["accepted"] and r["ticks"] >= 1 and ep.ticks == r["ticks"]
    assert ep.invalid_actions == 0


def test_decision_budget_ends_the_episode():
    ep = AbuseEpisode("level01", seed=0, budgets=Budgets(max_ticks=9000, max_decisions=3))
    for _ in range(3):
        ep.step(PLAYER_ID, "wait")
    out = ep.outcome()
    assert out["status"] == "terminal" and out["reason"] == "decision budget exhausted"
    assert ep.legal_actions(PLAYER_ID) == []
    r = ep.step(PLAYER_ID, "wait")
    assert r["accepted"] is False and ep.decisions == 3  # after the end nothing is counted


def test_tick_limit_ends_the_episode():
    ep = AbuseEpisode("level01", seed=0, budgets=Budgets(max_ticks=20, max_decisions=100))
    while ep.outcome()["status"] == "ongoing":
        ep.step(PLAYER_ID, "wait")
    assert ep.outcome()["reason"] == "tick limit" and ep.ticks >= 20


def test_same_seed_and_actions_reproduce_the_same_observations():
    def run():
        ep = AbuseEpisode("level01", seed=7)
        out = []
        for a in ["attack W10", "explore right", "jump right", "explore right", "wait"]:
            r = ep.step(PLAYER_ID, a)
            out.append(json.dumps(r["observation"], sort_keys=True))
        return out
    assert run() == run()


def test_in_process_player_gets_copies():
    class Mutator:
        def start(self, info):
            pass

        def decide(self, obs, legal):
            obs["player"]["hp"] = -1
            legal.clear()
            return {"action": "wait"}

        def end(self, outcome):
            pass

    ep = AbuseEpisode("level01", seed=0)
    obs = ep.observe(PLAYER_ID)
    InProcessPlayer(Mutator()).decide(obs, ep.legal_actions(PLAYER_ID))
    assert ep.observe(PLAYER_ID)["player"]["hp"] == 100


def test_process_player_runs_an_episode_over_the_protocol(tmp_path):
    player = ProcessPlayer([sys.executable, "-m", "abuse_remake.agent.players.baselines", "scripted"])
    trace = tmp_path / "t.jsonl"
    out = run_episode(player, "level01", 0, budgets=Budgets(max_ticks=9000, max_decisions=8), trace_path=trace)
    assert out["decisions"] == 8 and out["invalid_actions"] == 0 and 0.0 <= out["progress"] <= 1.0
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    assert rows[0]["kind"] == "header" and rows[-1]["kind"] == "outcome"
    assert sum(1 for r in rows if r["kind"] == "step") == 8


def test_a_player_that_answers_garbage_is_refused_not_crashed(tmp_path):
    script = tmp_path / "bad_player.py"
    script.write_text("import sys\nfor line in sys.stdin:\n    print('not json', flush=True)\n")
    player = ProcessPlayer([sys.executable, str(script)], decision_timeout=10)
    out = run_episode(player, "level01", 0, budgets=Budgets(max_ticks=9000, max_decisions=3))
    assert out["invalid_actions"] == 3 and out["ticks"] == 0


def test_a_bare_legal_word_that_is_not_json_is_still_refused(tmp_path):
    script = tmp_path / "bare_player.py"
    script.write_text("import sys\nfor line in sys.stdin:\n    print('wait', flush=True)\n")
    player = ProcessPlayer([sys.executable, str(script)], decision_timeout=10)
    trace = tmp_path / "t.jsonl"
    out = run_episode(player, "level01", 0, budgets=Budgets(max_ticks=9000, max_decisions=2), trace_path=trace)
    assert out["invalid_actions"] == 2 and out["ticks"] == 0
    step = [json.loads(x) for x in trace.read_text().splitlines()][1]
    assert step["raw"] == "wait" and step["player_error"] == "reply is not a JSON object"


def test_baselines_are_deterministic_and_scripted_beats_random():
    def run(policy, seed):
        budgets = Budgets(max_ticks=9000, max_decisions=120)
        return run_episode(InProcessPlayer(policy), "level01", seed, budgets=budgets)
    a = run(ScriptedPlayer(), 3)
    b = run(ScriptedPlayer(), 3)
    keys = ("ticks", "x", "y", "hp", "progress")
    assert {k: a[k] for k in keys} == {k: b[k] for k in keys}
    r = run(RandomPlayer(), 3)
    assert a["progress"] >= r["progress"] or r["reason"] == "player died"
    assert a["invalid_actions"] == 0


def test_off_screen_events_are_not_reported():
    from abuse_remake.engine.world import Event
    ep = AbuseEpisode("level01", seed=0)
    v = ep.observe(PLAYER_ID)["view"]
    ep._pending_events = [Event("enemy_alert", {"uid": 999, "x": v["x"] + 2000, "y": v["y"] + 900}),
                          Event("enemy_alert", {"uid": 998, "x": v["x"] + 50, "y": v["y"] + 50})]
    events = ep.observe(PLAYER_ID)["events"]
    assert len(events) == 1 and events[0]["type"] == "enemy_alert"
