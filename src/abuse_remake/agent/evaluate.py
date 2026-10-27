"""``abuse-eval``: the repeated comparison of players over the same scenarios and seeds.

    uv run abuse-eval run --config eval/configs/offline.toml            # baselines, no network
    uv run abuse-eval estimate --config eval/configs/live.toml          # tokens and cost, no calls
    COURSE_MODEL=<id> uv run abuse-eval run --config eval/configs/live.toml --live
    uv run abuse-eval report runs/<dir> --report-to docs/evaluation-report.md

Fairness rules (docs/evaluation.md):
- every player gets the same scenarios, seeds, difficulty, budgets and motor skills;
- players run in separate processes and see only observations and legal actions;
- the progress metric is computed on the runner side and never shown to players;
- every planned episode appears in the results: failures, budget stops and episodes that were
  not run are reported, never dropped;
- players marked ``live`` run only with ``--live``. Without it they are reported as not run;
  nothing is substituted for them;
- the run-level token caps stop further live episodes once reached, and those are reported as
  not run.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import platform
import sys
import tomllib
from dataclasses import asdict
from importlib import metadata
from pathlib import Path

from .. import __version__
from .interface import SCENARIOS, Budgets
from .runner import code_identity, git_sha, make_player, run_episode
from .stats import cluster_paired_diff, mean_ci, paired_diff, percentile, wilson

EST_INPUT_TOKENS_PER_DECISION = 1800  # measured prompt sizes: ~700 system + ~700-1100 per turn (M2 most)


# --- configuration ---------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    cfg = tomllib.loads(Path(path).read_text())
    cfg.setdefault("name", Path(path).stem)
    cfg.setdefault("difficulty", "hard")
    cfg.setdefault("isolation", "process")
    cfg.setdefault("decision_timeout", 90.0)
    cfg.setdefault("budgets", {})
    cfg.setdefault("run", {})
    cfg.setdefault("prices", {})
    for s in cfg["scenarios"]:
        if s not in SCENARIOS:
            raise SystemExit(f"unknown scenario {s!r}")
    for s in cfg["budgets"].get("scenarios", {}):
        if s not in cfg["scenarios"]:
            raise SystemExit(f"budgets for {s!r}, which is not one of this config's scenarios")
    labels = [p["label"] for p in cfg["players"]]
    if len(set(labels)) != len(labels):
        raise SystemExit("player labels must be unique")
    return cfg


def budgets_for(cfg: dict, scenario: str) -> Budgets:
    """The scenario's budgets: the config's defaults, then any ``[budgets.scenarios.<name>]``
    overrides. They depend only on the scenario, so every player gets the same."""
    b = {k: v for k, v in cfg["budgets"].items() if k != "scenarios"}
    b.update(cfg["budgets"].get("scenarios", {}).get(scenario, {}))
    return Budgets(max_ticks=int(b.get("max_ticks") or SCENARIOS[scenario].max_ticks),
                   max_decisions=int(b.get("max_decisions", 600)),
                   max_input_tokens=int(b.get("max_input_tokens", 0)),
                   max_output_tokens=int(b.get("max_output_tokens", 0)),
                   max_wall_s=float(b.get("max_wall_s", 0.0)))


def plan(cfg: dict) -> list[dict]:
    return [{"label": p["label"], "player": p["player"], "args": list(p.get("args", [])),
             "live": bool(p.get("live", False)), "scenario": s, "seed": int(seed)}
            for p in cfg["players"] for s in cfg["scenarios"] for seed in cfg["seeds"]]


def versions() -> dict:
    out = {}
    for pkg in ("pygame-ce", "numpy", "google-genai", "anthropic", "openai"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = None
    return out


# --- running ---------------------------------------------------------------------------------
def _trace_usage(trace: Path) -> tuple[int, int]:
    """Tokens recorded in a trace, for an episode that crashed before reporting its own totals."""
    inp = out = 0
    try:
        for line in trace.read_text().splitlines():
            row = json.loads(line)
            if row.get("kind") == "step":
                inp += int((row.get("meta") or {}).get("input_tokens") or 0)
                out += int((row.get("meta") or {}).get("output_tokens") or 0)
    except (OSError, ValueError):
        pass
    return inp, out


def _run_one(cfg: dict, job: dict, out_dir: str) -> dict:
    trace = Path(out_dir) / "traces" / job["label"] / f"{job['scenario']}-s{job['seed']}.jsonl"
    budgets = budgets_for(cfg, job["scenario"])
    try:
        player = make_player(job["player"], cfg["isolation"], job["args"], float(cfg["decision_timeout"]))
        out = run_episode(player, job["scenario"], job["seed"], cfg["difficulty"], budgets, trace,
                          label=job["label"], config={"eval": cfg["name"], "player": job})
        out["ran"] = True
    except Exception as exc:  # noqa: BLE001 - a crashed episode is reported as crashed, not dropped
        inp, outp = _trace_usage(trace)
        out = {"ran": False, "crashed": True, "reason": f"crashed: {type(exc).__name__}: {exc}"[:300],
               "input_tokens": inp, "output_tokens": outp}
    out.update({"label": job["label"], "scenario": job["scenario"], "seed": job["seed"], "live": job["live"],
                "trace": str(trace.relative_to(out_dir)) if trace.exists() else None})
    return out


def _key(r: dict) -> tuple:
    return r["label"], r["scenario"], r["seed"]


def run(cfg: dict, out_dir: Path, live: bool, jobs: int = 1, log=sys.stderr, only: set[str] | None = None,
        resume: bool = False) -> list[dict]:
    """Run the plan, appending each result to ``results.partial.jsonl`` as soon as it is known, so a
    run that is stopped part-way loses no finished episode. ``only`` limits the run to some player
    labels (to split a long live comparison); ``resume`` skips episodes that already ran."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs_list = [j for j in plan(cfg) if only is None or j["label"] in only]
    partial = out_dir / "results.partial.jsonl"
    done: dict[tuple, dict] = {}
    if resume and partial.exists():
        for line in partial.read_text().splitlines():
            r = json.loads(line)
            if r.get("ran"):
                done[_key(r)] = r
    resolved_model = os.environ.get("COURSE_MODEL", "").strip() or None
    record = {"config": cfg, "git": git_sha(), "version": __version__, "python": platform.python_version(),
              "packages": versions(), "live": live, "only": sorted(only) if only else None,
              "started": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
              "course_model": resolved_model if live else None,
              "budgets": {s: asdict(budgets_for(cfg, s)) for s in cfg["scenarios"]},
              **code_identity()}
    (out_dir / "config.json").write_text(json.dumps(record, indent=2))
    results: list[dict] = list(done.values())
    sink = partial.open("a" if resume else "w")

    def keep(r: dict) -> None:
        results.append(r)
        sink.write(json.dumps(r) + "\n")
        sink.flush()
        _log(log, r, len(results), len(jobs_list))

    todo = [j for j in jobs_list if _key(j) not in done]
    offline = [j for j in todo if not j["live"]]
    online = [j for j in todo if j["live"]]
    if jobs > 1 and len(offline) > 1:
        with cf.ProcessPoolExecutor(max_workers=jobs) as pool:
            for f in cf.as_completed([pool.submit(_run_one, cfg, j, str(out_dir)) for j in offline]):
                keep(f.result())
    else:
        for j in offline:
            keep(_run_one(cfg, j, str(out_dir)))
    cap_in = int(cfg["run"].get("max_input_tokens", 0))
    cap_out = int(cfg["run"].get("max_output_tokens", 0))
    used_in = sum(int(r.get("input_tokens") or 0) for r in results if r.get("live"))
    used_out = sum(int(r.get("output_tokens") or 0) for r in results if r.get("live"))
    # Live episodes run one at a time. The run-level caps are checked before each one starts, so a
    # run can pass a cap by at most one episode's own token budget.
    for j in online:
        if not live:
            keep({**j, "ran": False, "reason": "not run: live player and --live not given"})
        elif (cap_in and used_in >= cap_in) or (cap_out and used_out >= cap_out):
            keep({**j, "ran": False, "reason": "not run: run token budget exhausted"})
        else:
            r = _run_one(cfg, j, str(out_dir))
            used_in += int(r.get("input_tokens") or 0)
            used_out += int(r.get("output_tokens") or 0)
            keep(r)
    sink.close()
    order = {_key(j): i for i, j in enumerate(jobs_list)}
    results.sort(key=lambda r: order[_key(r)])
    with (out_dir / "results.jsonl").open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    return results


def _log(log, r: dict, i: int, n: int) -> None:
    if log is not None:
        prog = f"progress {r['progress']:.3f}" if r.get("ran") else ""
        print(f"[{i}/{n}] {r['label']} {r['scenario']} seed {r['seed']}: {r.get('reason')} {prog}",
              file=log, flush=True)


# --- estimating ------------------------------------------------------------------------------
def _arg(args: list[str], flag: str, default: int) -> int:
    try:
        return int(args[args.index(flag) + 1])
    except (ValueError, IndexError):
        return default


def estimate(cfg: dict, max_output_tokens_per_request: int | None = None) -> dict:
    live_jobs = [j for j in plan(cfg) if j["live"]]
    if max_output_tokens_per_request is None:  # what the live players will actually ask for
        max_output_tokens_per_request = max([_arg(j["args"], "--max-output-tokens", 1024) for j in live_jobs] or [1024])
    total_in = total_out = requests = 0
    for j in live_jobs:
        b = budgets_for(cfg, j["scenario"])
        ep_in = b.max_decisions * EST_INPUT_TOKENS_PER_DECISION
        ep_out_worst = b.max_decisions * max_output_tokens_per_request
        total_in += min(ep_in, b.max_input_tokens) if b.max_input_tokens else ep_in
        total_out += min(ep_out_worst, b.max_output_tokens) if b.max_output_tokens else ep_out_worst
        requests += b.max_decisions
    if cfg["run"].get("max_input_tokens"):
        total_in = min(total_in, int(cfg["run"]["max_input_tokens"]))
    if cfg["run"].get("max_output_tokens"):
        total_out = min(total_out, int(cfg["run"]["max_output_tokens"]))
    decisions = {s: budgets_for(cfg, s).max_decisions for s in cfg["scenarios"]}
    est = {"live_episodes": len(live_jobs),
           "max_decisions": decisions if len(set(decisions.values())) > 1 else next(iter(decisions.values())),
           "input_tokens": total_in, "output_tokens_worst_case": total_out, "requests_max": requests}
    est["cost_usd_worst_case"] = cost(cfg, total_in, total_out)
    return est


def cost(cfg: dict, inp: int, out: int) -> float | None:
    p = cfg.get("prices") or {}
    if not p.get("input_per_mtok") and not p.get("output_per_mtok"):
        return None
    return round(inp / 1e6 * float(p.get("input_per_mtok", 0)) + out / 1e6 * float(p.get("output_per_mtok", 0)), 4)


# --- reporting -------------------------------------------------------------------------------
def _fmt_ci(m: float, lo: float, hi: float, digits: int = 3) -> str:
    if m != m:  # NaN: nothing ran
        return "n/a"
    if lo != lo:  # one episode: no interval
        return f"{m:.{digits}f} [n/a]"
    return f"{m:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"


def _num(x: float) -> str:
    return "-" if x != x else f"{x:.0f}"


def _rate(num: int, den: int) -> str:
    return "n/a" if not den else f"{num / den:.3f}"


def summarize(rows: list[dict], cfg: dict) -> dict:
    ran = [r for r in rows if r.get("ran")]
    out = {}
    for label in [p["label"] for p in cfg["players"]]:
        for scen in cfg["scenarios"] + ["all"]:
            rs = [r for r in ran if r["label"] == label and (scen == "all" or r["scenario"] == scen)]
            planned = [r for r in rows if r["label"] == label and (scen == "all" or r["scenario"] == scen)]
            lat = [r["latency_p50_s"] for r in rs if r.get("latency_p50_s") is not None]
            cats: dict = {}
            for r in rs:
                for k, n in (r.get("error_categories") or {}).items():
                    cats[k] = cats.get(k, 0) + n
            out[(label, scen)] = {
                "planned": len(planned), "n": len(rs),
                "success": wilson(sum(int(r["score"]) for r in rs), len(rs)),
                "wins": sum(int(r["score"]) for r in rs),
                "progress": mean_ci([r["progress"] for r in rs]),
                "deaths": sum(r["reason"] == "player died" for r in rs),
                "kills": mean_ci([r["kills"] for r in rs]),
                "damage": mean_ci([r["damage_taken"] for r in rs]),
                "decisions_total": sum(r["decisions"] for r in rs),
                "invalid": sum(r["invalid_actions"] for r in rs),
                "decisions": mean_ci([r["decisions"] for r in rs]),
                "ticks": mean_ci([r["ticks"] for r in rs]),
                "calls": sum(int(r.get("model_calls") or 0) for r in rs),
                "errors": sum(int(r.get("model_errors") or 0) for r in rs),
                "error_categories": cats,
                "input_tokens": sum(int(r.get("input_tokens") or 0) for r in planned),
                "output_tokens": sum(int(r.get("output_tokens") or 0) for r in planned),
                "latency_p50": percentile(lat, 50),
                "reasons": _count(r["reason"] for r in planned),
            }
    return out


def _count(items) -> dict:
    c: dict = {}
    for i in items:
        c[i] = c.get(i, 0) + 1
    return c


def _status_cell(r: dict | None) -> str:
    if r is None:
        return "not in this run"
    if r.get("crashed"):
        return "crashed"
    if not r.get("ran"):
        return "not run"
    tag = " (won)" if r["score"] else " (died)" if r["reason"] == "player died" else ""
    return f"{r['progress']:.3f}{tag}"


def render_report(rows: list[dict], record: dict) -> str:
    cfg = record["config"]
    s = summarize(rows, cfg)
    labels = [p["label"] for p in cfg["players"]]
    ref = cfg.get("reference", "scripted" if "scripted" in labels else labels[0])
    budgets = budgets_for(cfg, cfg["scenarios"][0])
    own = {s: budgets_for(cfg, s) for s in cfg["scenarios"] if budgets_for(cfg, s) != budgets}
    dirty = " with uncommitted changes" if record.get("src_dirty") else ""
    identity = (f"; src tree `{record['src_tree'][:12]}`{dirty}, prompt `{record['prompt_sha']}`"
                if record.get("prompt_sha") else "")
    lines = [
        f"# Evaluation report: {cfg['name']}",
        "",
        f"Generated by `abuse-eval` from `results.jsonl`. Git `{record['git'][:12]}`{identity}, "
        f"version {record['version']}, Python {record['python']}, started {record['started']} (UTC).",
        f"Live model calls: {'yes' if record['live'] else 'no'}"
        + (f"; requested model `{record['course_model']}`" if record.get("course_model") else "") + "."
        + (f" Players in this run: {', '.join(record['only'])}." if record.get("only") else ""),
        "",
        f"Scenarios: {', '.join(cfg['scenarios'])}. Seeds: {', '.join(str(x) for x in cfg['seeds'])}. "
        f"Difficulty: {cfg['difficulty']}. Players run in {cfg['isolation']} isolation.",
        f"Budgets per episode, the same for every player: {budgets.max_decisions} decisions, the scenario's tick "
        f"limit, at most {budgets.max_action_ticks} ticks per action"
        + (f", {budgets.max_input_tokens} input tokens" if budgets.max_input_tokens else "")
        + (f", {budgets.max_output_tokens} output tokens" if budgets.max_output_tokens else "")
        + (f", {budgets.max_wall_s:.0f} s" if budgets.max_wall_s else "") + "."
        + "".join(f" `{s}` has its own: {b.max_decisions} decisions"
                  + (f", {b.max_input_tokens} input tokens" if b.max_input_tokens else "")
                  + (f", {b.max_output_tokens} output tokens" if b.max_output_tokens else "")
                  + (f", {b.max_wall_s:.0f} s" if b.max_wall_s else "") + "." for s, b in own.items()),
        "",
        "How to read the tables:",
        "- *planned* counts every episode in the plan; *n* is the number that ran.",
        "- *success* is wins / n with a Wilson 95% interval.",
        "- Other figures are means over episodes with a percentile-bootstrap 95% interval (`[n/a]` with one "
        "episode). A player that does the same thing on every seed gets a zero-width interval: the "
        "interval covers seeds, not other ways the player could have played.",
        "- *progress* is the evaluator-only distance measure (1 = reached the exit).",
        "- *invalid* is refused actions per decision. *failed requests* is the part of that which came from "
        "model requests that failed (timeouts, rate limits, truncation, refusals), not from illegal choices.",
        "",
        "## Players",
        "",
        "| label | player | args | live | models that answered |",
        "|---|---|---|---|---|",
    ]
    for p in cfg["players"]:
        models = sorted({r.get("model") for r in rows if r["label"] == p["label"] and r.get("model")})
        lines.append(f"| {p['label']} | {p['player']} | `{' '.join(p.get('args', [])) or '-'}` | "
                     f"{'yes' if p.get('live') else 'no'} | {', '.join(f'`{m}`' for m in models) or '-'} |")
    for scen in cfg["scenarios"] + ["all"]:
        title = "All scenarios pooled" if scen == "all" else f"Scenario `{scen}`"
        lines += ["", f"## {title}", "",
                  "| player | planned | n | success | progress | deaths | kills | damage taken | invalid "
                  "| failed requests | decisions | ticks | model calls | tokens in / out | latency p50 s | cost USD |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for label in labels:
            v = s[(label, scen)]
            c = cost(cfg, v["input_tokens"], v["output_tokens"]) if v["input_tokens"] or v["output_tokens"] else None
            lat = "-" if v["latency_p50"] is None else f"{v['latency_p50']:.2f}"
            _, slo, shi = v["success"]
            succ = "n/a" if not v["n"] else f"{v['wins']}/{v['n']} [{slo:.2f}, {shi:.2f}]"
            lines.append(
                f"| {label} | {v['planned']} | {v['n']} | {succ} | {_fmt_ci(*v['progress'])} "
                f"| {v['deaths']} | {_fmt_ci(*v['kills'], 1)} | {_fmt_ci(*v['damage'], 0)} "
                f"| {_rate(v['invalid'], v['decisions_total'])} | {_rate(v['errors'], v['decisions_total'])} "
                f"| {_num(v['decisions'][0])} | {_num(v['ticks'][0])} | {v['calls']} "
                f"| {v['input_tokens']} / {v['output_tokens']} | {lat} | {'-' if c is None else c} |")
        lines += ["", "Episode endings: " + "; ".join(
            f"{label}: " + ", ".join(f"{k} x{n}" for k, n in s[(label, scen)]["reasons"].items())
            for label in labels)]
        cats = [f"{label}: " + ", ".join(f"{k} x{n}" for k, n in sorted(s[(label, scen)]["error_categories"].items()))
                for label in labels if s[(label, scen)]["error_categories"]]
        if cats:
            lines.append("Failed requests by category: " + "; ".join(cats))
    ran = [r for r in rows if r.get("ran")]
    by = {label: {(r["scenario"], r["seed"]): r["progress"] for r in ran if r["label"] == label} for label in labels}
    lines += ["", "## Paired comparison (same scenario and seed)", "",
              f"Mean difference in progress against `{ref}`. Per scenario, the interval resamples seeds. Pooled, it "
              "resamples scenarios and then seeds within them, because seeds of one scenario are not independent.",
              "", "| player | scenario | pairs | progress minus reference |", "|---|---|---|---|"]
    for label in labels:
        if label == ref:
            continue
        for scen in cfg["scenarios"]:
            a = {k: v for k, v in by[label].items() if k[0] == scen}
            n, m, lo, hi = paired_diff(a, by.get(ref, {}))
            lines.append(f"| {label} | {scen} | {n} | {_fmt_ci(m, lo, hi)} |")
        n, k, m, lo, hi = cluster_paired_diff(by[label], by.get(ref, {}))
        lines.append(f"| {label} | **pooled** ({k} scenarios) | {n} | {_fmt_ci(m, lo, hi)} |")
    lines += ["", "### Per-seed progress", "", "| scenario | seed | " + " | ".join(labels) + " |",
              "|---|---|" + "---|" * len(labels)]
    index = {(r["label"], r["scenario"], r["seed"]): r for r in rows}
    for scen in cfg["scenarios"]:
        for seed in cfg["seeds"]:
            cells = [_status_cell(index.get((label, scen, seed))) for label in labels]
            lines.append(f"| {scen} | {seed} | " + " | ".join(cells) + " |")
    mem = sorted({r.get("memory") for r in ran if r.get("memory")})
    if mem:
        lines += ["", "## Memory and history comparison", "",
                  "M0: current observation only. M1: plus the last 8 turns. M2: plus the model's notes and an "
                  "automap summary built from past observations.", "",
                  "| memory | episodes | progress | invalid | failed requests | input tokens per decision |",
                  "|---|---|---|---|---|---|"]
        for m_ in mem:
            rs = [r for r in ran if r.get("memory") == m_]
            dec = sum(r["decisions"] for r in rs)
            tpd = sum(int(r.get("input_tokens") or 0) for r in rs) / dec if dec else float("nan")
            lines.append(f"| {m_} | {len(rs)} | {_fmt_ci(*mean_ci([r['progress'] for r in rs]))} "
                         f"| {_rate(sum(r['invalid_actions'] for r in rs), dec)} "
                         f"| {_rate(sum(int(r.get('model_errors') or 0) for r in rs), dec)} | {_num(tpd)} |")
    crashed = [r for r in rows if r.get("crashed")]
    if crashed:
        lines += ["", "## Episodes that crashed", "",
                  "These started and have a partial trace, but did not finish. Tokens they used still count above.", ""]
        for r in crashed:
            lines.append(f"- {r['label']} {r['scenario']} seed {r['seed']}: {r['reason']}")
    not_run = [r for r in rows if not r.get("ran") and not r.get("crashed")]
    if not_run:
        lines += ["", "## Episodes not run", ""]
        for reason, n in _count(r["reason"] for r in not_run).items():
            lines.append(f"- {reason}: {n}")
    p = cfg.get("prices") or {}
    lines += ["", "## Prices", "",
              (f"Cost uses {p.get('input_per_mtok')} / {p.get('output_per_mtok')} USD per million input / output "
               f"tokens, from {p.get('source') or 'an unrecorded source'} on {p.get('date') or 'an unrecorded date'}."
               if cost(cfg, 1, 1) is not None else "No prices in the config, so no cost is estimated."),
              "", "Self-play alone does not establish learning or strong play: these numbers compare fixed players "
              "under equal budgets; see the human playtest notes for a human reference.", ""]
    return "\n".join(lines)


def write_report(out_dir: Path, report_to: Path | None = None) -> str:
    src = out_dir / "results.jsonl"
    if not src.exists():  # a run that was stopped part-way
        src = out_dir / "results.partial.jsonl"
    rows = [json.loads(line) for line in src.read_text().splitlines() if line.strip()]
    record = json.loads((out_dir / "config.json").read_text())
    text = render_report(rows, record)
    (out_dir / "report.md").write_text(text)
    if report_to is not None:
        report_to.parent.mkdir(parents=True, exist_ok=True)
        report_to.write_text(text)
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="abuse-eval", description="Repeated comparison of Abuse players")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run every player on every scenario and seed")
    r.add_argument("--config", type=Path, required=True)
    r.add_argument("--out", type=Path, default=None, help="default: runs/<name>-<UTC time>")
    r.add_argument("--live", action="store_true", help="also run players marked live (model calls cost money)")
    r.add_argument("--jobs", type=int, default=1, help="parallel offline episodes")
    r.add_argument("--report-to", type=Path, default=None)
    r.add_argument("--only", default=None, help="comma-separated player labels to run (splits a long live run)")
    r.add_argument("--resume", action="store_true", help="with --out: skip episodes that already ran there")
    e = sub.add_parser("estimate", help="token and cost estimate for the live players; makes no calls")
    e.add_argument("--config", type=Path, required=True)
    e.add_argument("--max-output-tokens", type=int, default=None,
                   help="per request (default: what the live players' args say)")
    rep = sub.add_parser("report", help="rebuild report.md from a run directory")
    rep.add_argument("run_dir", type=Path)
    rep.add_argument("--report-to", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.cmd == "estimate":
        print(json.dumps(estimate(load_config(a.config), a.max_output_tokens), indent=2))
        return 0
    if a.cmd == "report":
        write_report(a.run_dir, a.report_to)
        print(a.run_dir / "report.md")
        return 0
    cfg = load_config(a.config)
    if a.live:
        from .players.model_player import check_config

        for p in cfg["players"]:
            problem = check_config(p.get("args", [])) if p.get("live") and p["player"] == "model" else None
            if problem:
                print(f"abuse-eval: player {p['label']}: {problem}", file=sys.stderr)
                return 2
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = a.out or Path("runs") / f"{cfg['name']}-{stamp}"
    only = {x.strip() for x in a.only.split(",")} if a.only else None
    if only and not only <= {p["label"] for p in cfg["players"]}:
        print(f"abuse-eval: unknown labels in --only: {sorted(only - {p['label'] for p in cfg['players']})}",
              file=sys.stderr)
        return 2
    run(cfg, out_dir, a.live, a.jobs, only=only, resume=a.resume)
    write_report(out_dir, a.report_to)
    print(out_dir / "report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
