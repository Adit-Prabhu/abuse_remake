# Running players and the evaluation

## Setup

```sh
uv sync --all-extras          # the game, the baselines and the model SDKs
uv run pytest                 # deterministic tests: no network, no model calls
```

## One episode

```sh
uv run abuse-agent --player scripted --scenario level01-cp1 --seed 0 --trace runs/demo.jsonl
uv run abuse-agent --player random --scenario level01 --seed 3
uv run abuse-agent --player "cmd:python my_player.py" --scenario level01 --seed 0
```

The scenarios are:
- `level01`: the full level from START, 9000 ticks;
- `level01-cp1`, `level01-cp2`, `level01-cp3`: segments starting at each restart console, 2700
  ticks each.

Any program that speaks the JSON-lines protocol in `agent/protocol.py` is a valid player.

## The model player

The model ID is never in the code. It comes from `COURSE_MODEL` (or `--model`), and it is
recorded in every trace and report.

**Vertex AI (Gemini), the default.** Owner setup:

```sh
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<your project> GOOGLE_CLOUD_LOCATION=global
export COURSE_MODEL=<a Gemini model ID available on Vertex>
uv run abuse-agent --player model --scenario level01-cp1 --seed 0 --max-decisions 20 --trace runs/m.jsonl \
    -- --provider vertex --memory M1
```

**Anthropic** (`ANTHROPIC_API_KEY` or `ant auth login`), with
`-- --provider anthropic --memory M1`.

**OpenAI** (`OPENAI_API_KEY`), with `-- --provider openai --memory M1`.

The model player's options (after `--`):

| Option | Meaning |
|---|---|
| `--memory M0\|M1\|M2` | the memory condition |
| `--timeout 20` | seconds per request; one attempt |
| `--max-output-tokens 1024` | output cap per request |
| `--effort low` | optional: Anthropic `output_config.effort`, OpenAI `reasoning_effort` |
| `--thinking-budget N` | optional: the Gemini thinking budget |

`abuse-agent` refuses to start a model player when the model, the SDK or the Vertex project is
missing, so a misconfigured run cannot turn into a run of refused decisions.

## The repeated comparison

```sh
uv run abuse-eval run --config eval/configs/offline.toml --jobs 6        # baselines, no network
uv run abuse-eval estimate --config eval/configs/live.toml               # tokens and cost, no calls
COURSE_MODEL=<id> uv run abuse-eval run --config eval/configs/live-smoke.toml --live   # about 20 requests
COURSE_MODEL=<id> uv run abuse-eval run --config eval/configs/live.toml --live --jobs 6 \
    --report-to docs/evaluation-report.md
```

A run directory (`runs/<name>-<UTC time>/`) holds:
- `config.json`: the config, git SHA, package versions, the resolved model and the budgets;
- `results.jsonl`: one row per planned episode, including ones that did not run;
- `traces/<player>/<scenario>-s<seed>.jsonl`: a header, one row per decision and the outcome;
- `report.md`.

`uv run abuse-eval report <run dir>` rebuilds the report from the results.

The live comparison can also run in GitHub Actions (`.github/workflows/live-eval.yml`). It is a
manual dispatch on the default branch, uses Workload Identity Federation, and needs the owner to
set the repository variables listed at the top of the workflow.

## Fairness

- Every player gets the same scenarios, seeds (0 to 4), difficulty (`hard`), budgets and motor
  skills, and runs in its own process.
- The game is paused while a player decides.
- The progress measure is computed on the runner side and never shown to players.
- The config is committed before a run, and the run records it.
- Every planned episode is reported, including deaths, budget stops, crashes and episodes not
  run. Live players run only with `--live`, and no fixture ever stands in for them.

## Metrics

| Metric | Meaning |
|---|---|
| success | reached the exit and pressed down (score 1) |
| progress | `1 - d_best / d_start`, where `d` is the A* distance to the exit over the full map with teleporters; 1 for a win. Evaluator only |
| deaths, kills, damage taken | from game events |
| invalid rate | refused actions / decisions |
| decisions, ticks | used per episode |
| model calls, errors, tokens, latency p50 | from the model player's per-decision reports |
| cost | tokens times the dated prices in the config, when they are filled in |

The report gives means with percentile-bootstrap 95% CIs (10,000 resamples, fixed seed). It
also gives paired per-seed differences against the scripted baseline, and a table for the
memory/history comparison.

## Evidence so far

- The offline baseline run: `evidence/reports/offline-baselines.md`, with its results, config and three
  traces in `evidence/traces/offline-v1/`.
- Over 20 paired episodes, the scripted baseline beats random: random's progress minus
  scripted's is −0.219 [−0.329, −0.124].
- The live comparison has not been run yet. It needs the owner's Vertex setup and approval of
  the estimated cost.

Self-play alone does not establish learning or strong play. These are fixed players compared
under equal budgets. Human playtests give the human reference; their protocol and notes go in
`docs/playtests/`, and none have been run yet.
