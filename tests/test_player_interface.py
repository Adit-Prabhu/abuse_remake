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


def test_the_last_decision_under_the_cap_still_runs():
    """Regression: the decision that reached the cap was counted before it ran, so the controller
    saw the budget as spent and the action was accepted with 0 ticks. The offline evidence trace
    scripted-level01-s0 (offline-v3, git 88670c4^) shows it: decision 600, `explore left`,
    accepted with 0 ticks."""
    ep = AbuseEpisode("level01", seed=0, budgets=Budgets(max_ticks=9000, max_decisions=2))
    first = ep.step(PLAYER_ID, "wait")
    last = ep.step(PLAYER_ID, "wait")
    assert first["ticks"] == 8 and last["accepted"] and last["ticks"] == 8
    assert ep.ticks == 16 and ep.outcome()["reason"] == "decision budget exhausted"


def test_switching_to_the_laser_at_the_cap_reaches_the_laser():
    """Ctrl steps back one weapon per tick. At the cap the old counting stopped after one press,
    on the grenade, and still reported the switch to the laser as accepted."""
    ep = AbuseEpisode("level01", seed=0, budgets=Budgets(max_ticks=9000, max_decisions=1))
    v = ep._game.view
    v.weapons[1], v.weapons[2], v.current_weapon = 5, 5, 2  # grenades and rockets, rockets held
    r = ep.step(PLAYER_ID, "weapon laser")
    assert r["accepted"] and r["ticks"] == 2 and v.current_weapon == 0


def test_a_refused_decision_at_the_cap_ends_the_episode_without_ticks():
    ep = AbuseEpisode("level01", seed=0, budgets=Budgets(max_ticks=9000, max_decisions=1))
    r = ep.step(PLAYER_ID, "fly away")
    assert not r["accepted"] and r["ticks"] == 0 and ep.ticks == 0
    assert ep.decisions == 1 and ep.invalid_actions == 1
    assert ep.outcome()["reason"] == "decision budget exhausted"


def test_the_decision_in_progress_is_numbered_while_it_runs():
    """The spectator's panel numbers the decision being played on every tick of it."""
    ep = AbuseEpisode("level01", seed=0, budgets=Budgets(max_ticks=9000, max_decisions=5))
    seen = []
    ep.on_tick = lambda: seen.append(ep.decision_number)
    ep.step(PLAYER_ID, "wait")
    ep.step(PLAYER_ID, "wait")
    assert seen == [1] * 8 + [2] * 8 and ep.decision_number == 2


def test_a_decision_is_counted_even_if_its_action_raises(monkeypatch):
    ep = AbuseEpisode("level01", seed=0)

    def boom(_):
        raise RuntimeError("controller bug")

    monkeypatch.setattr(ep, "_c_wait", boom)
    with pytest.raises(RuntimeError):
        ep.step(PLAYER_ID, "wait")
    assert ep.decisions == 1 and ep.decision_number == 1


def test_tick_limit_ends_the_episode():
    ep = AbuseEpisode("level01", seed=0, budgets=Budgets(max_ticks=20, max_decisions=100))
    while ep.outcome()["status"] == "ongoing":
        ep.step(PLAYER_ID, "wait")
    assert ep.outcome()["reason"] == "tick limit" and ep.ticks == 20  # an action never runs past the limit


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
    ep._note_events([Event("enemy_alert", {"uid": 999, "x": v["x"] + 2000, "y": v["y"] + 900}),
                     Event("enemy_alert", {"uid": 998, "x": v["x"] + 50, "y": v["y"] + 50})])
    events = ep.observe(PLAYER_ID)["events"]
    assert len(events) == 1 and events[0]["type"] == "enemy_alert"



# --- controllers, navigation, progress and scenarios (PR #5 review) -----------------------------
def test_every_action_is_capped_at_max_action_ticks():
    ep = AbuseEpisode("level01-cp2", seed=1)
    pl = ScriptedPlayer()
    longest = 0
    for _ in range(60):
        if ep.outcome()["status"] != "ongoing":
            break
        r = ep.step(PLAYER_ID, pl.decide(ep.observe(PLAYER_ID), ep.legal_actions(PLAYER_ID))["action"])
        longest = max(longest, r["ticks"])
        assert 1 <= r["ticks"] <= ep.budgets.max_action_ticks
    assert longest > 8  # long actions do happen, and still stop at the cap


def test_an_action_stops_when_the_player_is_hurt():
    ep = AbuseEpisode("level01", seed=0)
    ep.step(PLAYER_ID, "wait")
    seen = []

    def hurt_on_second_tick():
        seen.append(ep.ticks)
        if len(seen) == 2:
            p = ep._game.player
            p.do_damage(5, None, p.x, p.y, 0, 0)

    ep.on_tick = hurt_on_second_tick
    r = ep.step(PLAYER_ID, "wait")  # 8 ticks unless interrupted
    assert r["ticks"] == 2 and any(e["type"] == "player_hurt" for e in r["observation"]["events"])


def test_a_new_threat_stops_an_action_except_attack():
    def run(action):
        ep = AbuseEpisode("level01", seed=0)
        ep.step(PLAYER_ID, "wait")
        n = []

        def spawn_on_second_tick():
            n.append(1)
            if len(n) == 2:
                p = ep._game.player
                ep._game.world.spawn("ANT_ROOF", p.x + 120, p.y).set_state("stopped")

        ep.on_tick = spawn_on_second_tick
        return ep, ep.step(PLAYER_ID, action)

    _, r = run("wait")
    assert r["ticks"] == 2
    ep, _ = run("wait")
    alien = next(o["id"] for o in ep.observe(PLAYER_ID)["objects"] if o["kind"] == "alien")
    n = []

    def another_threat():
        n.append(1)
        if len(n) == 2:
            p = ep._game.player
            ep._game.world.spawn("ANT_ROOF", p.x - 120, p.y).set_state("stopped")

    ep.on_tick = another_threat
    r2 = ep.step(PLAYER_ID, f"attack {alien}")
    assert r2["accepted"] and r2["ticks"] > 2  # attack keeps firing when a second threat appears


def test_every_accepted_action_takes_at_least_one_tick(monkeypatch):
    ep = AbuseEpisode("level01", seed=0)
    monkeypatch.setattr(ep, "_c_wait", lambda _arg: iter(()))  # a controller with nothing to do
    r = ep.step(PLAYER_ID, "wait")
    assert r["accepted"] and r["ticks"] == 1 and ep.ticks == 1


def test_switching_to_the_laser_uses_the_original_keys_and_takes_effect_at_once():
    ep = AbuseEpisode("level01", seed=0)
    v = ep._game.view
    v.give_weapon(1)
    v.add_ammo(1, 5)
    assert "weapon grenade" in ep.legal_actions(PLAYER_ID)
    r = ep.step(PLAYER_ID, "weapon grenade")
    assert r["observation"]["player"]["weapon"] == "grenade" and r["ticks"] == 1
    assert "weapon laser" in ep.legal_actions(PLAYER_ID) and v.weapons[0] == 0  # no laser ammo
    r = ep.step(PLAYER_ID, "weapon laser")
    assert r["observation"]["player"]["weapon"] == "laser" and r["ticks"] == 1  # one Ctrl press
    assert "weapon laser" not in ep.legal_actions(PLAYER_ID)


def test_refused_actions_report_no_events_of_their_own():
    ep = AbuseEpisode("level01", seed=1)
    for _ in range(3):
        ep.step(PLAYER_ID, "attack W10" if "attack W10" in ep.legal_actions(PLAYER_ID) else "explore right")
    from abuse_remake.engine.world import Event

    ep._note_events([Event("pickup", {"item": "ammo_laser"})])
    assert ep.observe(PLAYER_ID)["events"]  # what the last action did is reported once...
    r = ep.step(PLAYER_ID, "fly away")
    assert r["accepted"] is False and r["observation"]["events"] == []  # ...and not again after a refusal


def test_labels_are_given_only_at_decision_time_nearest_first():
    ep = AbuseEpisode("level01", seed=0)
    for _ in range(6):
        ep.step(PLAYER_ID, "explore right")
        obs = ep.observe(PLAYER_ID)
        given = set(ep._ids.labels.values())
        shown_so_far = {o["id"] for o in obs["objects"]}
        assert shown_so_far <= given
    # every label ever given was shown in some observation: numbers have no gaps per prefix
    for prefix, n in ep._ids.counters.items():
        assert sorted(int(lab[1:]) for lab in ep._ids.labels.values() if lab[0] == prefix) == list(range(1, n + 1))
    first = AbuseEpisode("level01", seed=0).observe(PLAYER_ID)["objects"]
    walls = [o for o in first if o["kind"] == "wall_block"]
    assert [int(o["id"][1:]) for o in walls] == sorted(int(o["id"][1:]) for o in walls)  # nearer, lower number


def test_navigation_plans_only_over_seen_tiles_and_respects_blocked_cells():
    from abuse_remake.agent.nav import KnownMap, Navigator, blocked_cells, cell_of
    from abuse_remake.engine.game import Game

    tm = Game(seed=0).world.tiles
    full = KnownMap({(c, r) for c in range(tm.width) for r in range(tm.height)})
    start = Navigator(tm, full).nearest_standable(*cell_of(209, 76))
    goal = (start[0] - 4, start[1])
    goal = Navigator(tm, full).nearest_standable(*goal)
    h = lambda n: 0 if n == goal else abs(n[0] - goal[0]) + abs(n[1] - goal[1])  # noqa: E731
    assert Navigator(tm, full).plan(start, h) is not None
    unseen = KnownMap({start})
    assert Navigator(tm, unseen).plan(start, h) is None  # nothing is known beyond where we stand
    wall = {"kind": "wall_block", "x": 30 * goal[0] + 15, "y": 15 * (goal[1] + 1)}
    cells = blocked_cells([wall, {"kind": "door", "state": "open", "x": 0, "y": 0}])
    assert cell_of(wall["x"], wall["y"]) in cells and (0, -1) not in cells  # open doors do not block
    assert Navigator(tm, full, cells).cls(*cell_of(wall["x"], wall["y"])) == "#"


def test_progress_is_zero_at_the_start_one_at_the_exit_and_uses_teleporters():
    from abuse_remake.agent.progress import ProgressTracker, distance_to_exit
    from abuse_remake.engine.game import Game

    t = ProgressTracker(167, 43)
    assert t.value(False) == 0.0 and t.value(True) == 1.0
    t.update(2715, 306)
    assert t.value(False) > 0.95
    g = Game(seed=0)
    pads = [o for o in g.world.objects if o.ctype.name in ("TELE2", "TP_DOOR") and o.objs]
    assert pads
    d_pad = [(distance_to_exit(o.x, o.y), distance_to_exit(o.objs[0].x, o.objs[0].y)) for o in pads]
    assert any(a is not None and b is not None and a <= b + 3.5 for a, b in d_pad)  # a pad is as close as its far end


@pytest.mark.parametrize("name,start", [("level01-cp1", (81, 111)), ("level01-cp2", (841, 828)),
                                        ("level01-cp3", (1413, 639))])
def test_segment_scenarios_start_at_their_console(name, start):
    ep = AbuseEpisode(name, seed=0)
    p = ep.observe(PLAYER_ID)["player"]
    assert (p["x"], p["y"]) == start and ep.budgets.max_ticks == 2700
    assert ep.step(PLAYER_ID, "wait")["accepted"]


def test_hidden_ants_and_inactive_pickups_are_not_reported():
    ep = AbuseEpisode("level01", seed=0)
    w = ep._game.world
    p = ep._game.player
    hidden = w.spawn("HIDDEN_ANT", p.x + 60, p.y)
    switch = w.spawn("SWITCH", p.x - 60, p.y)
    ammo = w.spawn("MBULLET_ICON5", p.x + 40, p.y)
    ammo.add_object(switch)  # linked: shown only while the switch is on (on_draw)
    switch.aistate = 0
    shown = {(o["x"], o["y"]) for o in ep.observe(PLAYER_ID)["objects"]}
    assert (hidden.x, hidden.y) not in shown and (ammo.x, ammo.y) not in shown
    switch.aistate = 1
    shown = {(o["x"], o["y"]) for o in ep.observe(PLAYER_ID)["objects"]}
    assert (ammo.x, ammo.y) in shown


def test_episodes_are_identical_across_processes_and_hash_seeds():
    import subprocess

    code = ("from abuse_remake.agent.interface import PLAYER_ID, AbuseEpisode;"
            "from abuse_remake.agent.players.baselines import ScriptedPlayer;"
            "ep = AbuseEpisode('level01-cp1', seed=3); pl = ScriptedPlayer()\n"
            "for _ in range(40):\n"
            "    ep.step(PLAYER_ID, pl.decide(ep.observe(PLAYER_ID), ep.legal_actions(PLAYER_ID))['action'])\n"
            "print(ep._game.state_hash())")
    out = set()
    for hs in ("0", "12345"):
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={**__import__("os").environ, "PYTHONHASHSEED": hs})
        assert r.returncode == 0, r.stderr
        out.add(r.stdout.strip())
    assert len(out) == 1


def test_using_the_exit_wins_the_episode_through_the_interface():
    """The terminal win, through the five operations: on screen, `use X1` walks up the slope to
    the exit and presses the action key, and the outcome is won, score 1."""
    ep = AbuseEpisode("level01-cp3", seed=0)
    p, v = ep._game.player, ep._game.view
    p.x, p.y = 2620, 316  # test set-up: on the floor before the exit's slope, as the solver's route passes
    p.last_x, p.last_y = p.x, p.y
    v.last_x, v.last_y, v.last_last_x, v.last_last_y = p.x, p.y, p.x, p.y
    ep.step(PLAYER_ID, "wait")
    use = [a for a in ep.legal_actions(PLAYER_ID) if a.startswith("use X")]
    assert use
    for _ in range(4):
        if ep.outcome()["status"] != "ongoing":
            break
        ep.step(PLAYER_ID, use[0])
    out = ep.outcome()
    assert out["status"] == "terminal" and out["reason"] == "reached the exit" and out["score"] == 1
    assert ep.legal_actions(PLAYER_ID) == [] and not ep.step(PLAYER_ID, "wait")["accepted"]
