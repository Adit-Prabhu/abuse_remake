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

Before an episode starts, `abuse-agent` and `abuse-eval --live` check the model player's
setup: the model ID, the SDK, the Vertex project, and that the client can be built (this reads
the SDK's credentials but sends no request). Credentials that are present but rejected show up
on the first request; that error is fatal, and the runner ends the episode as `player failed`
after one refused decision, so a misconfigured run cannot spend its budget on refusals.

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
- Every planned episode is reported, including deaths, budget stops, player failures, crashes
  (their own section, with their partial traces) and episodes not run. Live players run only
  with `--live`, and no fixture ever stands in for them.

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

The report gives:
- success as wins / n with a Wilson 95% interval;
- other figures as means with percentile-bootstrap 95% intervals (10,000 resamples, fixed seed),
  and no interval for a single episode. A player that does the same on every seed gets a
  zero-width interval: the interval covers seeds, not other ways the player could have played;
- paired differences against the scripted baseline per scenario (seeds resampled), and pooled
  with a cluster bootstrap (scenarios resampled, then seeds within them), because seeds of one
  scenario are not independent;
- failed model requests apart from illegal choices, with their categories;
- a table for the memory/history comparison.

### Splitting a long live run

One model player over 4 scenarios × 5 seeds × 200 decisions makes up to 4,000 requests, about two
hours at 2 s each. Results are appended to `results.partial.jsonl` as episodes finish, so a
stopped run keeps what it finished. To split a run:

```sh
abuse-eval run --config eval/configs/live.toml --live --out runs/live-1 --only scripted,random,model-M0
abuse-eval run --config eval/configs/live.toml --live --out runs/live-1 --only model-M1 --resume
abuse-eval run --config eval/configs/live.toml --live --out runs/live-1 --resume   # the rest; then one report
```

## Evidence so far

- The offline baseline run: `evidence/reports/offline-baselines.md`, with its results, config and
  three traces in `evidence/traces/offline-v2/`.
- The scripted baseline beats random in every scenario. Random's progress minus scripted's is
  −0.218 pooled, with a cluster-bootstrap 95% interval of [−0.439, −0.029]. The interval is wide
  because the gap differs a lot between scenarios: −0.025 on `level01-cp1` against −0.531 on
  `level01-cp3`.
- The scripted baseline is deterministic in practice: on `level01` it reaches 0.163 on every
  seed, so its interval there has zero width.
- The live comparison has not been run yet. It needs the owner's Vertex setup and approval of
  the estimated cost.

Self-play alone does not establish learning or strong play. These are fixed players compared
under equal budgets. Human playtests give the human reference; their protocol and notes go in
`docs/playtests/`, and none have been run yet.
