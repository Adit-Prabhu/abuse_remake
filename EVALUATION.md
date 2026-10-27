# Evaluation

**Status on 2026-10-26:**
- The suite is declared (`SUITE.md`) and the offline baselines are run.
- The solver has proved one situation winnable so far.
- **The live model comparison has not been run yet.** Its table and traces will be added here
  from the reported run, with the commit and `src` tree they ran on.

## 1. The declared suite

[`SUITE.md`](SUITE.md) was declared on 2026-10-26, before any live model call and before any
prompt or baseline tuning. Its configs are `eval/configs/midterm.toml` (reported) and
`eval/configs/midterm-tuning.toml` (tuning only).

| Situation | Start | Ticks | Decisions | Seeds | Role |
|---|---|---|---|---|---|
| `level01-cp1` | console 1 | 2700 | 200 | 0, 1, 2 | held out |
| `level01-cp2` | console 2 | 2700 | 200 | 0, 1, 2 | tuned on seeds 90–91 only |
| `level01-cp3` | console 3 | 2700 | 200 | 0, 1, 2 | held out |
| `level01` | START | 9000 | 600 | 0, 1, 2 | held out |

The players are `random`, `scripted` (rules + A* over the automap), `model-M1` (Gemini
flash-lite on Vertex AI, with the last 8 turns of history) and `model-M0` (the same model, with
the current screen only). All of them get the same observation, actions and budgets, each in
its own process. The privileged solver is reported separately, as an upper reference.

## 2. Comparison table

*Pending the reported live run.* The report `abuse-eval` writes for it will include, per
situation and pooled:
- wins/n with Wilson intervals;
- progress;
- deaths;
- invalid actions, with failed requests counted separately;
- decisions and ticks;
- each episode's ending;
- model calls, tokens, latency p50/p95, and cost from dated prices;
- paired differences against `scripted`, and M1 against M0.

### Baselines before the declaration (offline, 2026-10-26)

`evidence/reports/offline-baselines.md` uses the older offline config: 600 decisions for every
scenario, seeds 0–4, with the interface as it now stands (after PRs #21 and #25). Pooled over the
four scenarios, scripted's progress is 0.348 and random's is 0.090 (a paired difference of
−0.258, with a cluster-bootstrap 95% interval of [−0.558, −0.015]). Neither wins any of 20
episodes. Per scenario:

| Scenario | random progress | scripted progress | scripted ending |
|---|---|---|---|
| `level01` | 0.163 (dies 5/5) | 0.163 on every seed | decision budget: it stalls in the first section |
| `level01-cp1` | 0.117 (dies 3/5) | 0.155 | tick limit |
| `level01-cp2` | 0.043 (dies 5/5) | 0.307 | dies 3/5 |
| `level01-cp3` | 0.038 | 0.767 | dies 5/5, close to the exit |

## 3. The solver: is each situation winnable?

`scripts/route_search.py --mode classic` is a best-first search over the engine's own state. It
is privileged, because it reads the World object, and it is never a competitor. A route it
finds is saved, and CI replays it under Classic rules.

| Situation | Result |
|---|---|
| `level01-cp3` | **winnable**: a 337-tick route from the console to the exit |
| `level01-cp2`, `level01-cp1`, `level01` | in progress. Segment START → console 2 found (293 ticks) |

## 4. CI evidence

**In the course repository:** `.github/workflows/midterm-adit-prabhu.yml` runs on pull requests
touching `midterms/adit-prabhu/`. It runs Ruff, the original-data checksums, the full pytest
suite (Python 3.11 and 3.12; the differential tests against compiled original C are required),
and an offline evaluation smoke run. It needs no network model calls and no secrets.

**In the project repository:** `.github/workflows/ci.yml` runs the same checks on every push. The
link to the green run for the submitted commit will be added here.

The five kinds of check the course asks for:

| Kind | Tests (in `tests/`) |
|---|---|
| Rule invariants | `test_engine_core.py`: C arithmetic, trig tables, the original random table, collision against the compiled original C (20,000 cases). `test_c_reference.py`: boundary flags against the original C. `test_classic_golden.py`: Classic state hashes pinned per seed and difficulty. `test_level01_objects.py`: every Level 1 object's rules. `abuse-data verify`: the original files' checksums |
| Legal and illegal actions | `test_player_interface.py`: `test_invalid_actions_are_refused_counted_and_change_nothing` (7 kinds of bad action, state hash unchanged), `test_legal_actions_only_name_visible_objects`, `test_a_player_that_answers_garbage_is_refused_not_crashed`, `test_a_bare_legal_word_that_is_not_json_is_still_refused`, the refused `fire`, `fire north` and `fire W1`. On what an action may name: `test_each_hidden_wall_shows_only_as_it_looks` (all eight hidden-wall types), `test_no_wall_is_named_before_it_looks_breakable_at_the_start`, `test_fire_shoots_the_current_weapon_that_way`. `test_model_player.py`: `test_non_json_answers_are_refused_with_the_raw_text_kept`, `test_failed_requests_are_refused_decisions_with_no_retry` |
| A terminal outcome | `test_level01_objects.py`: `test_exit_needs_touch_and_action_key`. `test_campaign_routes.py`: every saved route replays to its level's exit. `test_player_interface.py`: `test_tick_limit_ends_the_episode`, `test_decision_budget_ends_the_episode` |
| A genuine observed regression | `test_the_last_decision_under_the_cap_still_runs`: the committed evidence trace showed decision 600 accepted with 0 ticks (PR #21). `test_evidence.py` replays every committed trace, and fails on the old trace under the fix. `test_a_late_reply_is_never_used_for_the_next_decision_but_its_tokens_count`: found in review of PR #6 |
| Episode limits | `test_decision_budget_ends_the_episode`, `test_tick_limit_ends_the_episode`, `test_every_action_is_capped_at_max_action_ticks`, `test_every_accepted_action_takes_at_least_one_tick`, `test_token_budget_ends_the_episode_as_its_own_outcome`, `test_wall_clock_budget_ends_a_real_episode`, `test_live_episodes_respect_the_episode_and_run_token_caps` |

## 5. Traces

- Offline: `evidence/traces/offline-v5/`, three traces, each replayed exactly in CI.
- Every run writes all of its traces to `runs/<run>/traces/`. Selected live traces will be
  committed under `evidence/traces/`.
- `uv run abuse-replay --trace <file>` replays one with its decision panel and checks every
  observation.

## 6. Limitations

*Written by the student after the reported run, using the peer playtest notes.*
