"""The repeated-comparison harness: every planned episode is reported, live players are gated,
run-level token caps hold, and the statistics are right."""

import json
import sys
import textwrap
from pathlib import Path

import pytest

from abuse_remake.agent.evaluate import cost, estimate, load_config, plan, run, write_report
from abuse_remake.agent.stats import mean_ci, paired_diff

ROOT = Path(__file__).resolve().parents[1]


def test_ci_smoke_eval_reports_every_planned_episode(tmp_path):
    cfg = load_config(ROOT / "eval/configs/ci-smoke.toml")
    rows = run(cfg, tmp_path / "a", live=False, log=None)
    assert len(rows) == len(plan(cfg)) == 6
    live = [r for r in rows if r["label"] == "model-M1"]
    assert all(not r["ran"] and r["reason"] == "not run: live player and --live not given" for r in live)
    ran = [r for r in rows if r["ran"]]
    assert all(r["decisions"] == 12 and 0.0 <= r["progress"] <= 1.0 and r["invalid_actions"] == 0 for r in ran)
    assert all((tmp_path / "a" / r["trace"]).exists() for r in ran)
    report = write_report(tmp_path / "a")
    assert "not run: live player and --live not given: 2" in report
    assert "| model-M1 | 2 | 0 |" in report  # planned 2, ran 0: listed, not dropped
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


def test_estimate_and_cost_make_no_calls():
    cfg = load_config(ROOT / "eval/configs/live.toml")
    est = estimate(cfg)
    assert est["live_episodes"] == 60 and est["requests_max"] == 60 * 200
    assert est["input_tokens"] <= cfg["run"]["max_input_tokens"]
    assert est["cost_usd_worst_case"] is None  # no prices are invented
    cfg["prices"] = {"input_per_mtok": 2.0, "output_per_mtok": 10.0}
    assert cost(cfg, 1_000_000, 100_000) == 3.0


def test_bootstrap_statistics():
    assert mean_ci([0.5, 0.5, 0.5]) == (0.5, 0.5, 0.5)
    m, lo, hi = mean_ci([0.0, 1.0] * 20)
    assert m == 0.5 and 0.3 < lo < 0.5 < hi < 0.7
    assert mean_ci([1.0, 2.0, 3.0]) == mean_ci([1.0, 2.0, 3.0])  # fixed resampling seed
    n, d, lo, hi = paired_diff({"a": 1.0, "b": 0.5, "c": 0.2}, {"a": 0.5, "b": 0.5})
    assert n == 2 and d == pytest.approx(0.25)


def test_configs_load_and_live_players_are_marked():
    for name in ("offline", "live", "live-smoke", "ci-smoke"):
        cfg = load_config(ROOT / f"eval/configs/{name}.toml")
        for p in cfg["players"]:
            assert p.get("live", False) == (p["player"] == "model")
            assert "--model" not in p.get("args", [])  # the model comes from COURSE_MODEL at run time
    json.dumps(load_config(ROOT / "eval/configs/live.toml"))
