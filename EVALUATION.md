# Evaluation

**Status on 2026-10-26:**
- The suite is declared (`SUITE.md`) and the offline baselines are run.
- The solver's results arrive with its Classic mode (PR #27).
- **The live model comparison has not been run yet.** Its table and traces will be added here
  from the reported run, with the commit and `src` tree they ran on.

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

### Offline baselines (no model calls)

`evidence/reports/offline-baselines.md` uses the offline config: 600 decisions for every
scenario, seeds 0–4. It was generated on 2026-10-27 from the clean commit `5aef372`, with the
interface as it now stands (after PRs #21 and #25). Pooled over the four scenarios, scripted's
progress is 0.322 and random's is 0.088 (a paired difference of −0.234, with a cluster-bootstrap
95% interval of [−0.543, −0.008]). Neither wins any of 20 episodes. Per scenario:

| Scenario | random progress | scripted progress | scripted ending | random minus scripted |
|---|---|---|---|---|
| `level01` | 0.125 (dies 3/5) | 0.163 | decision budget: it stalls in the first section | −0.038 [−0.053, −0.022] |
| `level01-cp1` | 0.170 (dies 1/5) | 0.155 | tick limit | +0.015 [−0.013, 0.029] |
| `level01-cp2` | 0.019 (dies 5/5) | 0.224 | dies 5/5 | −0.205 [−0.252, −0.122] |
| `level01-cp3` | 0.038 | 0.747 | dies 5/5, close to the exit | −0.709 [−0.726, −0.686] |

On `level01-cp1` the two are level (the interval covers 0). Random breaks no walls there, and
scripted breaks 14 on every seed, so the gap is not about walls. The baseline is strongest from
console 2 on.

## 3. The solver: is each situation winnable?

`scripts/route_search.py` is a best-first search over the engine's own state. It is
privileged, because it reads the World object, and it is never a competitor. Its Classic mode,
its starts at the restart consoles, and the routes it finds for each situation (replayed in CI)
arrive in PR #27, which fills in this section.

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

- Offline: `evidence/traces/offline-v7/`, three traces, each replayed exactly in CI.
- Every run writes all of its traces to `runs/<run>/traces/`. Selected live traces will be
  committed under `evidence/traces/`.
- `uv run abuse-replay --trace <file>` replays one with its decision panel and checks every
  observation.

## 6. Limitations

*Written by the student after the reported run, using the peer playtest notes.*
