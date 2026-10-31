# Evaluation

**Status on 2026-10-30:**
- The declared suite (`SUITE.md`) has been run once, live, from the frozen commit. All 48
  planned episodes ran and are reported in §2.
- The solver shows that all four situations can be won under Classic rules (seed 0; §3).
- The limitations (§6) are the student's to write.

**2026-10-30: the live path works.** The 20-request smoke run (`eval/configs/live-smoke.toml`,
`level01-cp1` seed 0, model-M1) made 20 calls with 0 failures and 0 refused actions. Every
answer came from `gemini-3.5-flash-lite`, as Vertex reported it. It used 26,264 input and 513
output tokens (USD 0.009 at the dated prices), with latency 0.86 s p50 and 1.69 s p95
(`evidence/reports/live-smoke.md`). It is a check of the path, not a result: 20 decisions,
one episode, and not part of the suite.

**2026-10-30: tuning is done and the prompt is frozen.** Two rounds on the tuning set
(`level01-cp2`, seeds 90 and 91) brought model-M1's mean progress there from 0.0055 to 0.057;
scripted's is 0.254. The rule that picked the frozen prompt was committed before the second
round ran (`docs/prompt-log.md`). The frozen commit, `src` tree, prompt hash and model ID are in
`SUITE.md`.

## 1. The declared suite

[`SUITE.md`](SUITE.md) was declared on 2026-10-26, before any live model call and before any
prompt or baseline tuning. Its configs are `eval/configs/midterm.toml` (reported) and
`eval/configs/midterm-tuning.toml` (tuning only).

| Situation | Start | Ticks | Decisions | Seeds | Role |
|---|---|---|---|---|---|
| `level01-cp1` | console 1 | 2700 | 200 | 0, 1, 2 | held out |
| `level01-cp2` | console 2 | 2700 | 200 | 0, 1, 2 | tuned on seeds 90–91; the baseline's floor shot was first prompted by its seeds 0–2 (a recorded deviation, `SUITE.md`), so the cleanest held-out cases are the other three |
| `level01-cp3` | console 3 | 2700 | 200 | 0, 1, 2 | held out |
| `level01` | START | 9000 | 600 | 0, 1, 2 | held out |

The players are `random`, `scripted` (rules + A* over the automap), `model-M1` (Gemini
flash-lite on Vertex AI, with the last 8 turns of history) and `model-M0` (the same model, with
the current screen only). All of them get the same observation, actions and budgets, each in
its own process. The privileged solver is reported separately, as an upper reference.

## 2. Comparison table

The reported run: `eval/configs/midterm.toml` with `--live`, on 2026-10-30. It ran from the
frozen commit `c05542c` (`src` tree `298297660541`, clean; prompt `52e0fd185e2d`), with
`gemini-3.5-flash-lite` on Vertex AI, the ID Vertex reported for every call. **All 48 planned
episodes ran, and none was re-run.** The full report, with every metric and each episode's
ending, is `evidence/reports/midterm.md`; its data is in `midterm.results.jsonl` and
`midterm.config.json` beside it.

**Wins: 0/12 for every player** (Wilson 95% interval [0.00, 0.24]). No player finished any
episode, though the solver finishes every situation (§3). So the comparison rests on
progress, the evaluator's distance measure (1 = reached the exit).

Progress, the mean over seeds 0–2, with a bootstrap 95% interval over seeds:

| Situation | random | scripted | model-M0 | model-M1 |
|---|---|---|---|---|
| `level01-cp1` (held out) | 0.140 [0.110, 0.184] | 0.155 [0.155, 0.155] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| `level01-cp2` | 0.000 [0.000, 0.000] | 0.173 [0.000, 0.260], died 3/3 | 0.018 [0.000, 0.054], died 2/3 | 0.032 [0.000, 0.085], died 2/3 |
| `level01-cp3` (held out) | 0.038 [0.038, 0.038] | 0.633 [0.573, 0.753], died 1/3 | 0.038 [0.038, 0.038] | 0.176 [0.038, 0.431] |
| `level01` (held out) | 0.123 [0.098, 0.135], died 1/3 | 0.163 [0.163, 0.163] | 0.009 [0.009, 0.009] | 0.009 [0.009, 0.009] |
| **Pooled** (12 episodes) | 0.075 [0.041, 0.110] | **0.281 [0.169, 0.413]** | 0.016 [0.006, 0.027] | 0.054 [0.009, 0.128] |

Every other episode ended at its decision budget. A zero-width interval means a player did the
same on all three seeds; it covers seeds, not other ways the player could have played.

Paired differences in progress (same scenario and seed; pooled with a cluster bootstrap over
scenarios, then seeds):

| | `level01-cp1` | `level01-cp2` | `level01-cp3` | `level01` | Pooled |
|---|---|---|---|---|---|
| random − scripted | −0.015 [−0.045, 0.029] | −0.173 [−0.260, 0.000] | −0.595 [−0.716, −0.535] | −0.041 [−0.065, −0.028] | −0.206 [−0.471, −0.025] |
| model-M0 − scripted | −0.155 [−0.155, −0.155] | −0.156 [−0.260, 0.000] | −0.595 [−0.716, −0.535] | −0.154 [−0.154, −0.154] | −0.265 [−0.485, −0.133] |
| model-M1 − scripted | −0.155 [−0.155, −0.155] | −0.142 [−0.260, 0.011] | −0.457 [−0.694, −0.142] | −0.154 [−0.154, −0.154] | −0.227 [−0.401, −0.123] |
| model-M1 − model-M0 | 0.000 [0.000, 0.000] | +0.014 [−0.054, 0.085] | +0.138 [0.000, 0.393] | 0.000 [0.000, 0.000] | +0.038 [−0.008, 0.133] |

The model players' requests, failures and cost:

| | model-M0 | model-M1 |
|---|---|---|
| Requests | 3,337 | 3,309 |
| Failed requests (refused decisions, never retried) | 6 (timeout ×6) | 5 (timeout ×4, API error ×1) |
| Illegal choices | 0 | 2 (`use D1`, not in the legal actions) |
| Tokens in / out | 3,787,457 / 88,291 | 4,749,297 / 86,097 |
| Input tokens per decision | 1,135 | 1,435 |
| Latency p50 / p95 | 0.86 s / 1.73 s | 0.85 s / 1.43 s |
| Cost at the dated prices | USD 1.36 | USD 1.64 |

Live spending for the whole midterm: smoke USD 0.01, tuning USD 0.26, the reported run
USD 3.00. In all, USD 3.27 of the USD 10 cap.

### What the numbers say

- **The scripted baseline is ahead of both model players** in every situation. Pooled, it
  leads M1 by 0.227 and M0 by 0.265, with intervals that exclude 0. The cleanest held-out
  situations (`level01-cp1`, `level01-cp3`, `level01`) point the same way.
- **Neither model player beats random** on pooled progress: 0.054 (M1) and 0.016 (M0),
  against random's 0.075. Random gets further from the start on `level01-cp1` and the full
  level, where both model players stay near it.
- **History (M1 against M0) cannot be told apart in progress** with 3 seeds: +0.038 pooled,
  with an interval [−0.008, 0.133] that includes 0. The one visible gain, on `level01-cp3`, is
  one seed (seed 2: 0.431 against 0.038). One behaviour does separate them. M0 cannot see that
  it already saved, and used a console in 197 of its 3,337 decisions (5.9%); M1 in 32 of 3,309
  (1.0%); scripted in 12 of 3,284 (0.4%).

### What the traces show

- **The model fixes on targets it never kills.** 73% of M0's decisions (2,442) and 63% of
  M1's (2,096) were in runs of 20 or more identical `attack` actions; scripted's were 1%. Every
  one of M0's, and 2,068 of M1's, were aimed at an alien hanging from the ceiling. The longest
  run is `attack E1` 589 times in a row (M0, full level, seed 1); M1's is 228 (full level, seed
  2). `E1` hangs up and to the right of the first console (dx +156, dy −25) and was never
  killed. `level01-cp1` and `level01` both start near it, which is why both model players stay
  at 0.000 and 0.009 there.
- **The stuck rule added in tuning did not fire there.** It reacts to moves that do not move
  the player; while attacking, the model was not trying to move.
- **A difference in priors, found after the run.** The scripted baseline's fight rule leaves
  hanging aliens alone (`agent/players/baselines.py`, rule 1). The prompt says aliens may hang,
  but not that they can be left. `docs/information-boundary.md` said the prompt held the same
  priors as the baseline; for this rule it did not, and that page now says so. Nothing was
  changed: the suite and prompt are frozen, so a fix could only be a separate, labelled study.
- The smoke run, on held-out `level01-cp1`, already showed 11 attacks in a row on the hanging
  `E1`. The tuning rule kept that from being used to tune the prompt (`docs/prompt-log.md`).
- Representative traces are in `evidence/traces/midterm/` (§5).

### Offline baselines (no model calls)

This earlier offline run is kept for the record. For the comparison, the random and scripted
rows of the reported run above replace it: they use the declared budgets (200 decisions, 600 for
the full level) and seeds 0–2.

`evidence/reports/offline-baselines.md` uses the offline config: 600 decisions for every
scenario, seeds 0–4. It was generated on 2026-10-27 from the clean commit `72733d7`, with the
interface as it now stands (after PRs #21 and #25). Pooled over the four scenarios, scripted's
progress is 0.302 and random's is 0.088 (a paired difference of −0.213, with a cluster-bootstrap
95% interval of [−0.560, −0.007]). Neither wins any of 20 episodes. Per scenario:

| Scenario | random progress | scripted progress | scripted ending | random minus scripted |
|---|---|---|---|---|
| `level01` | 0.128 (dies 2/5) | 0.163 | decision budget: it stalls in the first section | −0.035 [−0.053, −0.020] |
| `level01-cp1` | 0.161 | 0.155 | tick limit | +0.006 [−0.017, 0.029] |
| `level01-cp2` | 0.027 (dies 5/5) | 0.115 | dies 5/5 | −0.088 [−0.196, 0.019] |
| `level01-cp3` | 0.038 | 0.773 | dies 5/5, close to the exit | −0.735 [−0.762, −0.716] |

The baseline separates clearly from random on `level01` and `level01-cp3`. It is level with
random on `level01-cp1`, and on `level01-cp2` the interval covers 0. On the tuning seeds of
`cp2` (90 and 91) it reaches 0.254 on both, so `cp2`'s reported seeds are harder for it. No
baseline change is made from that: the reported seeds are not for tuning.

## 3. The solver: is each situation winnable?

`scripts/route_search.py --mode classic` is a best-first search over the engine's own state. It
is privileged, because it reads the World object, and it is never a competitor. Each route it
found starts where the scenario starts, and CI replays it under Classic rules (difficulty hard)
to the exit (`tests/test_campaign_routes.py`). Route lengths in ticks:

| Situation | Seed 0 | Seed 1 | Seed 2 | Tick limit |
|---|---|---|---|---|
| `level01` (from START) | **1,414** | not found | not found | 9,000 |
| `level01-cp1` | **1,440** | not found | not found | 2,700 |
| `level01-cp2` | **1,156** | **1,156** | not found | 2,700 |
| `level01-cp3` | **337** | **341** | **349** | 2,700 |

**Every situation can be won under the rules** (seed 0). The seed moves the enemies' random
choices, and every "not found" fails at the same place: the trap room, where nine spray-gun
turrets wake while the player waits on a teleporter. There the search ran out of branches, even
at a finer setting (about 9,000-10,800 nodes). That says the solver's coarse moves die there on
those seeds. It does not say the room cannot be crossed: for example, it never stops to shoot
the turrets first.

These are routes of per-tick inputs, which fire while running at targets read from the engine.
So they show that the **rules** allow a win, not that the action interface does
(`docs/level01-route.md`). Level 1 is a puzzle: a lift, a switch that opens a trap door far
below, teleporters, and the turret trap. Unguided searches found no route, and the solver needed
waypoints read from the level's objects. That gap, between heading right and finishing the
level, is where every player in the comparison is measured.

## Known limitations of the shared motor skills

`goto`, `use` and `explore` plan over the automap and walk the plan. They are the same for every
player, and they are imperfect. For example, `use` on the exit wins from the floor just before
the exit's slope, but from about 60 px further back it jumps about and had not arrived after six
uses (found while writing `test_using_the_exit_wins_the_episode_through_the_interface`). A player
that sees this can walk closer with `move` or `goto` first.

## 4. CI evidence

**In the course repository:** `.github/workflows/midterm-adit-prabhu.yml` runs on pull requests
touching `midterms/adit-prabhu/`. It runs Ruff, the original-data checksums, the full pytest
suite (Python 3.11 and 3.12; the differential tests against compiled original C are required),
and an offline evaluation smoke run. It needs no network model calls and no secrets.

**In the project repository:** `.github/workflows/ci.yml` runs the same checks on every push.
`EXPORTED_FROM.json` in the course folder names the project commit the folder was exported from.

The five kinds of check the course asks for:

| Kind | Tests (in `tests/`) |
|---|---|
| Rule invariants | `test_engine_core.py`: C arithmetic, trig tables, the original random table, collision against the compiled original C (20,000 cases). `test_c_reference.py`: boundary flags against the original C. `test_classic_golden.py`: Classic state hashes pinned per seed and difficulty. `test_level01_objects.py`: every Level 1 object's rules. `abuse-data verify`: the original files' checksums |
| Legal and illegal actions | `test_player_interface.py`: `test_invalid_actions_are_refused_counted_and_change_nothing` (7 kinds of bad action, state hash unchanged), `test_legal_actions_only_name_visible_objects`, `test_a_player_that_answers_garbage_is_refused_not_crashed`, `test_a_bare_legal_word_that_is_not_json_is_still_refused`, the refused `fire`, `fire north` and `fire W1`. On what an action may name: `test_each_hidden_wall_shows_only_as_it_looks` (all eight hidden-wall types), `test_at_the_start_only_the_walls_the_level_placed_cracked_are_named`, `test_fire_shoots_the_current_weapon_that_way`. `test_model_player.py`: `test_non_json_answers_are_refused_with_the_raw_text_kept`, `test_failed_requests_are_refused_decisions_with_no_retry` |
| A terminal outcome | `test_player_interface.py`: `test_using_the_exit_wins_the_episode_through_the_interface` (won, score 1, through `step`), `test_tick_limit_ends_the_episode`, `test_decision_budget_ends_the_episode`. `test_level01_objects.py`: `test_exit_needs_touch_and_action_key` (the exit rule in the engine) |
| A genuine observed regression | `test_the_last_decision_under_the_cap_still_runs`: the committed evidence trace showed decision 600 accepted with 0 ticks (PR #21). `test_evidence.py` replays every committed trace, and fails on the old trace under the fix. `test_a_late_reply_is_never_used_for_the_next_decision_but_its_tokens_count`: found in review of PR #6 |
| Episode limits | `test_decision_budget_ends_the_episode`, `test_tick_limit_ends_the_episode`, `test_every_action_is_capped_at_max_action_ticks`, `test_every_accepted_action_takes_at_least_one_tick`, `test_token_budget_ends_the_episode_as_its_own_outcome`, `test_wall_clock_budget_ends_a_real_episode`, `test_live_episodes_respect_the_episode_and_run_token_caps` |

## 5. Traces

- Offline: `evidence/traces/offline-v8/`, three traces, each replayed exactly in CI.
- Live smoke: `evidence/traces/live-smoke/model-M1-level01-cp1-s0.jsonl`, the first live
  episode (20 decisions, each with the model's raw answer), replayed exactly in CI.
- The reported run: `evidence/traces/midterm/`, five of its 48 traces, each replayed exactly
  in CI:
  - `model-M1-level01-cp3-s2`: the model's best episode (0.431);
  - `model-M1-level01-cp1-s0`: a typical one, with 161 `attack E1` in a row at a hanging alien;
  - `model-M0-level01-s0`: the full level, with 548 `attack E1` in a row;
  - `model-M1-level01-cp2-s1`: a death;
  - `scripted-level01-cp3-s1`: the baseline's best episode (0.753, then died).

  All 48 are in the run folder, `runs/midterm/traces/`, which is not committed.
- Every run writes all of its traces to `runs/<run>/traces/`. Selected live traces will be
  committed under `evidence/traces/`.
- `uv run abuse-replay --trace <file>` replays one with its decision panel and checks every
  observation.

## 6. Limitations

*Written by the student after the reported run, using the peer playtest notes.*
