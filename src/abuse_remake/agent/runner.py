"""``abuse-agent``: run one episode with a player, writing a trace.

    uv run abuse-agent --player scripted --scenario level01-cp1 --seed 0 --trace runs/demo.jsonl
    uv run abuse-agent --player cmd:"python my_player.py" ...

Players run in a child process by default (``--isolation process``). A player is a name
(``random``, ``scripted``, ``model``) or ``cmd:<command>`` for any program that speaks
``agent/protocol.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shlex
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .. import __version__
from .interface import PLAYER_ID, SCENARIOS, AbuseEpisode, Budgets
from .progress import ProgressTracker
from .protocol import InProcessPlayer, ProcessPlayer, player_env

BUILTIN = {
    "random": [sys.executable, "-m", "abuse_remake.agent.players.baselines", "random"],
    "scripted": [sys.executable, "-m", "abuse_remake.agent.players.baselines", "scripted"],
    "model": [sys.executable, "-m", "abuse_remake.agent.players.model_player"],
}


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def make_player(spec: str, isolation: str = "process", player_args: list[str] | None = None,
                decision_timeout: float = 90.0):
    if isolation == "inprocess":
        from .players.baselines import RandomPlayer, ScriptedPlayer

        if spec == "random":
            return InProcessPlayer(RandomPlayer())
        if spec == "scripted":
            return InProcessPlayer(ScriptedPlayer())
        if spec == "model":
            from .players.model_player import ModelPlayer

            return InProcessPlayer(ModelPlayer.from_args(player_args or []))
        raise ValueError("in-process mode supports random, scripted and model")
    if spec.startswith("cmd:"):
        command = shlex.split(spec[4:])
    else:
        command = BUILTIN[spec] + (player_args or [])
    # only the model player gets its provider's credential variables; every other player gets a
    # minimal environment (agent/protocol.py)
    return ProcessPlayer(command, decision_timeout=decision_timeout, env=player_env(spec == "model"))


def budget_stop(budgets: Budgets, usage: dict, wall_s: float) -> str | None:
    """The runner's budgets: tokens as reported by the player, and wall-clock time."""
    if budgets.max_input_tokens and usage["input_tokens"] >= budgets.max_input_tokens:
        return "token budget exhausted"
    if budgets.max_output_tokens and usage["output_tokens"] >= budgets.max_output_tokens:
        return "token budget exhausted"
    if budgets.max_wall_s and wall_s >= budgets.max_wall_s:
        return "wall-clock budget exhausted"
    return None


def add_usage(usage: dict, meta: dict) -> None:
    usage["input_tokens"] += int(meta.get("input_tokens") or 0)
    usage["output_tokens"] += int(meta.get("output_tokens") or 0)
    usage["model_calls"] += int(meta.get("calls") or 0)
    usage["model_errors"] += int(meta.get("errors") or 0)
    if meta.get("latency_s") is not None:
        usage["latency_s"].append(float(meta["latency_s"]))
    cat = meta.get("error_category")
    if cat:
        usage["error_categories"][cat] = usage["error_categories"].get(cat, 0) + 1


def run_episode(player, scenario: str, seed: int, difficulty: str = "hard", budgets: Budgets | None = None,
                trace_path: Path | None = None, full_obs: bool = False, label: str = "",
                config: dict | None = None) -> dict:
    ep = AbuseEpisode(scenario, seed, difficulty, budgets)
    budgets = ep.budgets
    started = time.time()
    trace = None
    if trace_path is not None:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace = trace_path.open("w")
        trace.write(json.dumps({"kind": "header", "label": label, "scenario": scenario, "seed": seed,
                                "difficulty": difficulty, "budgets": asdict(budgets), "version": __version__,
                                "git": git_sha(), "python": platform.python_version(),
                                "config": config or {}}) + "\n")
    player.start({"player_id": PLAYER_ID, "scenario": scenario, "seed": seed, "difficulty": difficulty,
                  "budgets": asdict(budgets)})
    obs = ep.observe(PLAYER_ID)
    tracker = ProgressTracker(obs["player"]["x"], obs["player"]["y"])
    usage = {"input_tokens": 0, "output_tokens": 0, "model_calls": 0, "model_errors": 0, "latency_s": [],
             "error_categories": {}}
    model_id = provider = memory = fatal_error = None
    while ep.outcome()["status"] == "ongoing":
        legal = ep.legal_actions(PLAYER_ID)
        reply = player.decide(obs, legal)
        action = reply.get("action")
        meta = reply.get("meta") or {}
        for late in reply.get("late_meta") or []:  # answers that missed their deadline still cost tokens
            add_usage(usage, late)
        if meta:
            add_usage(usage, meta)
            model_id = meta.get("model") or model_id
            provider = meta.get("provider") or provider
            memory = meta.get("memory") or memory
        res = ep.step(PLAYER_ID, action)
        obs = res["observation"]
        tracker.update(obs["player"]["x"], obs["player"]["y"])
        if trace is not None:
            row = {"kind": "step", "decision": ep.decisions, "tick": ep.ticks, "action": action,
                   "accepted": res["accepted"], "error": res["error"], "player_error": reply.get("error"),
                   "ticks": res["ticks"], "legal_count": len(legal), "note": str(reply.get("note") or "")[:300],
                   "raw": (reply.get("raw") or "")[:600], "wall_s": round(reply.get("wall_s", 0.0), 4),
                   "meta": meta, "player": obs["player"], "events": obs["events"],
                   "obs_sha": hashlib.sha256(json.dumps(obs, sort_keys=True).encode()).hexdigest()[:16]}
            if "notes" in reply:
                row["notes"] = str(reply["notes"])[:700]
            if full_obs:
                row["observation"] = obs
            trace.write(json.dumps(row) + "\n")
        stop = budget_stop(budgets, usage, time.time() - started)
        if meta.get("budget_exhausted"):
            stop = stop or "token budget exhausted"
        if reply.get("fatal") or meta.get("fatal"):  # e.g. rejected credentials: every later request would fail
            fatal_error = str(reply.get("error") or "")[:200]
            stop = stop or "player failed"
        if stop:
            ep.stop(stop)
    episode_outcome = ep.outcome()
    out = dict(episode_outcome)
    out["progress"] = round(tracker.value(out["reason"] == "reached the exit"), 4)
    lat = sorted(usage.pop("latency_s"))
    usage["latency_p50_s"] = round(lat[len(lat) // 2], 3) if lat else None
    usage["latency_p95_s"] = round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 3) if lat else None
    out.update(usage)
    out.update({"scenario": scenario, "seed": seed, "difficulty": difficulty, "label": label,
                "model": model_id, "provider": provider, "memory": memory, "wall_s": round(time.time() - started, 2),
                "fatal_error": fatal_error})
    player.end(episode_outcome)  # the episode's own outcome only: progress is evaluator-only
    if trace is not None:
        trace.write(json.dumps({"kind": "outcome", **out}) + "\n")
        trace.close()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="abuse-agent", description="Run one Level 1 episode with a player")
    ap.add_argument("--player", default="scripted", help="random | scripted | model | cmd:<command>")
    ap.add_argument("--scenario", default="level01", choices=sorted(SCENARIOS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", default="hard")
    ap.add_argument("--max-decisions", type=int, default=None)
    ap.add_argument("--max-ticks", type=int, default=None)
    ap.add_argument("--max-input-tokens", type=int, default=0, help="per episode, 0 = no cap")
    ap.add_argument("--max-output-tokens", type=int, default=0, help="per episode, 0 = no cap")
    ap.add_argument("--max-wall-s", type=float, default=0.0, help="per episode, 0 = no cap")
    ap.add_argument("--isolation", choices=("process", "inprocess"), default="process")
    ap.add_argument("--decision-timeout", type=float, default=90.0)
    ap.add_argument("--trace", type=Path)
    ap.add_argument("--full-obs", action="store_true", help="store every observation in the trace")
    ap.add_argument("player_args", nargs="*", help="extra arguments for the player program (after --)")
    args = ap.parse_args(argv)
    sc = SCENARIOS[args.scenario]
    budgets = Budgets(max_ticks=args.max_ticks or sc.max_ticks, max_input_tokens=args.max_input_tokens,
                      max_output_tokens=args.max_output_tokens, max_wall_s=args.max_wall_s)
    if args.max_decisions:
        budgets.max_decisions = args.max_decisions
    if args.player == "model":
        from .players.model_player import check_config

        problem = check_config(args.player_args)
        if problem:
            print(f"abuse-agent: {problem}", file=sys.stderr)
            return 2
    player = make_player(args.player, args.isolation, args.player_args, args.decision_timeout)
    out = run_episode(player, args.scenario, args.seed, args.difficulty, budgets, args.trace, args.full_obs,
                      label=args.player)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
