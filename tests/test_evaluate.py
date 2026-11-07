"""The repeated-comparison harness: every planned episode is reported, live players are gated,
run-level token caps hold, and the statistics are right."""

import json
import sys
import textwrap
from pathlib import Path

import pytest

from abuse_remake.agent import evaluate
from abuse_remake.agent.evaluate import cost, estimate, load_config, plan, run, write_report
from abuse_remake.agent.stats import cluster_paired_diff, mean_ci, paired_diff, wilson

ROOT = Path(__file__).resolve().parents[1]


def test_ci_smoke_eval_reports_every_planned_episode(tmp_path):
    cfg = load_config(ROOT / "eval/configs/ci-smoke.toml")
    rows = run(cfg, tmp_path / "a", live=False, log=None)
    assert len(rows) == len(plan(cfg)) == 6
    live = [r for r in rows if r["label"] == "model-M1"]
    assert all(not r["ran"] and r["reason"] == "not run: live player and --live not given" for r in live)
    ran = [r for r in rows if r["ran"]]
    assert len(ran) == 4  # random and scripted, two seeds each: an empty run must not pass
    assert all(r["decisions"] == 12 and 0.0 <= r["progress"] <= 1.0 and r["invalid_actions"] == 0 for r in ran)
    assert all((tmp_path / "a" / r["trace"]).exists() for r in ran)
    report = write_report(tmp_path / "a")
    assert "not run: live player and --live not given: 2" in report
    assert "| model-M1 | 2 | 0 |" in report  # planned 2, ran 0: listed, not dropped
    record = json.loads((tmp_path / "a" / "config.json").read_text())
    assert len(record["prompt_sha"]) == 12 and "src_tree" in record and "src_dirty" in record
    assert f"prompt `{record['prompt_sha']}`" in report
    rows2 = run(cfg, tmp_path / "b", live=False, log=None)  # same seeds: the same results
    key = ("label", "scenario", "seed", "progress", "ticks", "x", "y", "hp")
    assert [{k: r.get(k) for k in key} for r in rows] == [{k: r.get(k) for k in key} for r in rows2]


def test_live_episodes_respect_the_episode_and_run_token_caps(tmp_path):
    player = tmp_path / "token_player.py"
    player.write_text(textwrap.dedent("""
        import json, sys
        for line in sys.stdin:
            msg = json.loads(line)
            if msg["type"] == "decide":
                print(json.dumps({"action": "wait", "meta": {"calls": 1, "input_tokens": 100, "output_tokens": 5,
                                                           "model": "stub", "latency_s": 0.01}}), flush=True)
            elif msg["type"] == "end":
                break
    """))
    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text(textwrap.dedent(f"""
        name = "caps"
        scenarios = ["level01-cp1"]
        seeds = [0, 1, 2]
        [budgets]
        max_decisions = 50
        max_input_tokens = 450
        [run]
        max_input_tokens = 800
        [[players]]
        label = "stub"
        player = "cmd:{sys.executable} {player}"
        live = true
    """))
    cfg = load_config(cfg_path)
    rows = run(cfg, tmp_path / "out", live=True, log=None)
    assert [r["ran"] for r in rows] == [True, True, False]
    assert rows[0]["reason"] == "token budget exhausted" and rows[0]["input_tokens"] == 500
    assert rows[2]["reason"] == "not run: run token budget exhausted"
    assert rows[0]["model"] == "stub" and rows[0]["model_calls"] == 5


def test_estimate_and_cost_make_no_calls(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("estimate must not start a player")

    monkeypatch.setattr(evaluate, "make_player", boom)
    monkeypatch.setattr(evaluate, "run_episode", boom)
    cfg = load_config(ROOT / "eval/configs/live.toml")
    est = estimate(cfg)
    assert est["live_episodes"] == 60 and est["requests_max"] == 60 * 200
    assert est["input_tokens"] <= cfg["run"]["max_input_tokens"]
    assert est["cost_usd_worst_case"] is None  # no prices are invented
    cfg["prices"] = {"input_per_mtok": 2.0, "output_per_mtok": 10.0}
    assert cost(cfg, 1_000_000, 100_000) == 3.0


def test_a_scenario_can_have_its_own_budgets_the_same_for_every_player(tmp_path):
    cfg = load_config(ROOT / "eval/configs/midterm.toml")
    assert evaluate.budgets_for(cfg, "level01-cp1").max_decisions == 200
    full = evaluate.budgets_for(cfg, "level01")
    assert full.max_decisions == 600 and full.max_input_tokens == 1_800_000 and full.max_ticks == 9000
    est = estimate(cfg)  # 2 live players x (3 segments x 3 seeds x 200 + 3 seeds x 600)
    assert est["live_episodes"] == 24 and est["requests_max"] == 2 * (9 * 200 + 3 * 600)
    assert est["max_decisions"] == {"level01-cp1": 200, "level01-cp2": 200, "level01-cp3": 200, "level01": 600}
    bad = tmp_path / "bad.toml"
    bad.write_text((ROOT / "eval/configs/midterm.toml").read_text().replace(
        "[budgets.scenarios.level01]", "[budgets.scenarios.level99]"))
    with pytest.raises(SystemExit, match="level99"):
        load_config(bad)


def test_the_tuning_set_never_shares_an_episode_with_the_reported_suite():
    suite = load_config(ROOT / "eval/configs/midterm.toml")
    tuning = load_config(ROOT / "eval/configs/midterm-tuning.toml")
    reported = {(s, seed) for s in suite["scenarios"] for seed in suite["seeds"]}
    tuned = {(s, seed) for s in tuning["scenarios"] for seed in tuning["seeds"]}
    assert not reported & tuned
    held_out = set(suite["scenarios"]) - set(tuning["scenarios"])
    assert held_out == {"level01-cp1", "level01-cp3", "level01"}


def test_declared_pairs_are_compared_on_the_same_cases(tmp_path):
    cfg = load_config(ROOT / "eval/configs/ci-smoke.toml")
    cfg["compare"] = [["random", "scripted"]]
    run(cfg, tmp_path / "p", live=False, log=None)
    report = write_report(tmp_path / "p")
    assert "## Other paired comparisons (declared in the config)" in report
    assert "| random | scripted | level01-cp1 | 2 |" in report
    assert "latency p50 / p95 s" in report
    bad = tmp_path / "bad.toml"
    bad.write_text((ROOT / "eval/configs/ci-smoke.toml").read_text().replace(
        'reference = "scripted"', 'reference = "scripted"\ncompare = [["random", "nobody"]]'))
    with pytest.raises(SystemExit, match="compare"):
        load_config(bad)


def test_a_crashed_episode_makes_the_run_exit_non_zero(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("engine bug")

    monkeypatch.setattr(evaluate, "run_episode", boom)
    config = str(ROOT / "eval/configs/ci-smoke.toml")
    assert evaluate.main(["run", "--config", config, "--out", str(tmp_path / "c")]) == 1
    assert "crashed: RuntimeError" in (tmp_path / "c" / "report.md").read_text()


def test_bootstrap_statistics():
    assert mean_ci([0.5, 0.5, 0.5]) == (0.5, 0.5, 0.5)  # a deterministic player: zero width, and said so
    m, lo, hi = mean_ci([0.7])
    assert m == 0.7 and lo != lo and hi != hi  # one episode: no interval
    rate, lo, hi = wilson(0, 5)
    assert rate == 0.0 and lo == 0.0 and 0.4 < hi < 0.45  # 0/5 is not "0 [0, 0]"
    assert wilson(5, 5)[1] < 0.6 and wilson(0, 0)[0] != wilson(0, 0)[0]
    a = {("s1", i): 1.0 for i in range(5)} | {("s2", i): 0.0 for i in range(5)}
    b = {k: 0.5 for k in a}
    n, k, d, lo, hi = cluster_paired_diff(a, b)
    assert (n, k, d) == (10, 2, 0.0) and lo <= -0.4 and hi >= 0.4  # two scenarios disagree: a wide interval
    assert paired_diff(a, b)[2] > -0.4  # the naive per-pair interval is far narrower
    m, lo, hi = mean_ci([0.0, 1.0] * 20)
    assert m == 0.5 and 0.3 < lo < 0.5 < hi < 0.7
    assert mean_ci([1.0, 2.0, 3.0]) == mean_ci([1.0, 2.0, 3.0])  # fixed resampling seed
    n, d, lo, hi = paired_diff({"a": 1.0, "b": 0.5, "c": 0.2}, {"a": 0.5, "b": 0.5})
    assert n == 2 and d == pytest.approx(0.25)


def test_configs_load_and_live_players_are_marked():
    for name in ("offline", "live", "live-smoke", "ci-smoke", "midterm", "midterm-tuning"):
        cfg = load_config(ROOT / f"eval/configs/{name}.toml")
        for p in cfg["players"]:
            assert p.get("live", False) == (p["player"] == "model")
            assert "--model" not in p.get("args", [])  # the model comes from COURSE_MODEL at run time
    json.dumps(load_config(ROOT / "eval/configs/live.toml"))


def test_crashed_episodes_are_their_own_category_and_runs_can_be_split_and_resumed(tmp_path):
    cfg_path = tmp_path / "cfg.toml"
    cfg_path.write_text(textwrap.dedent("""
        name = "split"
        scenarios = ["level01-cp1"]
        seeds = [0, 1]
        [budgets]
        max_decisions = 4
        [[players]]
        label = "scripted"
        player = "scripted"
        [[players]]
        label = "broken"
        player = "no-such-player"
    """))
    cfg = load_config(cfg_path)
    out = tmp_path / "out"
    rows = run(cfg, out, live=False, log=None, only={"broken"})
    assert [r["label"] for r in rows] == ["broken", "broken"]
    assert all(r["crashed"] and not r["ran"] and r["reason"].startswith("crashed:") for r in rows)
    report = write_report(out)
    assert "## Episodes that crashed" in report and "not in this run" in report
    assert "crashed" in report.split("### Per-seed progress")[1]
    rows = run(cfg, out, live=False, log=None, resume=True)  # finishes the plan; crashed ones are retried
    assert sorted((r["label"], r["ran"]) for r in rows) == [("broken", False), ("broken", False),
                                                            ("scripted", True), ("scripted", True)]
    assert len((out / "results.partial.jsonl").read_text().splitlines()) == 6  # every result appended as it came
