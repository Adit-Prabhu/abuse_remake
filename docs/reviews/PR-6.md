# Review record: PR #6 (model player, providers, memory conditions, abuse-eval, live-eval)

- **Reviewer:** an independent read-only agent (Claude, `Explore` type, fresh context, no edit
  tools), briefed with `.claude/agents/rules-reviewer.md` plus the course rules for this change.
  It read the branch only through git objects, and inspected the installed SDKs read-only. It
  made no network or model calls.
- **Input:** the diff `feat/player-interface..feat/model-player` at `0751bd2`, the docs and
  configs, and the installed `google-genai` 2.30.0, `anthropic` 0.125.0 and `openai` 2.54.0.
- **Date:** 2026-10-13.
- **Fixes:** commit `b0a58f8` and the docs commit after it, on `feat/model-player`.

**Result:** one blocking finding and twelve that should be fixed. All were fixed; the notes were fixed or are recorded below.

| # | Severity | Finding (summarised) | Resolution |
|---|---|---|---|
| 1 | blocking | google-genai follows `CONTINUATION` tokens automatically, so one decision could send several billed requests | `automatic_continuation: False` in the Vertex config. `CONTINUATION` now counts as `truncated`. Both are tested |
| 2 | should fix | Evaluator-only `progress` reached players through the protocol's `end` message | The player gets only the episode's own outcome. Test: `test_players_get_the_episode_outcome_without_evaluator_data` |
| 3 | should fix | Player processes inherited the runner's whole environment, credentials included | Players get a minimal environment (`protocol.BASE_ENV`). Only the model player gets its provider's variables. Tested with placeholder values |
| 4 | should fix | `live-eval.yml` put a free-form `jobs` input straight into a shell script | Inputs are choices, passed through `env` and validated in the script |
| 5 | should fix | The default-branch gate was only an `if:` in the workflow file | Now documented as needing a protected `live-eval` environment and a WIF attribute condition, which the owner sets up. Tests run in a job without `id-token` |
| 6 | should fix | 60 sequential live episodes exceed the 6-hour job limit, and results were written only at the end | Results are appended as each episode finishes. `--only` and `--resume` split the run, and the workflow takes `only` |
| 7 | should fix | Some Anthropic and OpenAI SDK errors escaped uncategorised and were counted as player bugs with zero tokens | Every SDK error is caught. 401/403/404 and missing credentials are `auth` and fatal. Each case is tested |
| 8 | should fix | The docs claimed a misconfigured run could not become a run of refusals; three credential failures still could | `check_config` builds the client. Fatal errors and a dead player process end the episode as `player failed`. The docs were reworded to match |
| 9 | should fix | A reply after `decision_timeout` was read as the reply to the next decision | Requests carry ids. Late replies are dropped and their tokens still counted. Test: `test_a_late_reply_is_never_used_for_the_next_decision_but_its_tokens_count` |
| 10 | should fix | Player-side token caps below the runner's caps turned the rest of the episode into refusals | The CLI caps were removed. The player uses the runner's caps and reports `budget_exhausted`, and the runner stops the episode |
| 11 | should fix | One-episode and constant samples were printed as 95% CIs, e.g. "0.00 [0.00, 0.00]" for 0/5 | Success uses a Wilson interval, and a single episode shows `[n/a]`. The report explains zero-width intervals |
| 12 | should fix | The "SDK retries off" tests built their own clients and could not fail. The Vertex client settings were untested | Tests now check each adapter's own client: `max_retries`, `timeout`, and the Vertex `HttpOptions` (20,000 ms, 1 attempt) through a stand-in `genai.Client` |
| 13 | should fix | The automap test could not fail | Replaced with synthetic observations: an off-screen object is remembered; a vanished one is forgotten; projectiles are not kept |
| 14 | note | The run-level cap can be passed by one episode, and crashed episodes' tokens counted as 0 | Documented in `budgets.md`. A crashed episode's tokens are now read from its trace |
| 15 | note | Crashed episodes were listed as "not run" | They have their own category and report section |
| 16 | note | Vertex recorded the requested model ID, not the one that answered | Now records `model_version`. The report lists the models that answered |
| 17 | note | `httpx.ConnectError` was classified as `api_error`, and `requests.Timeout` as `connection` | Fixed: timeouts are checked first, then transport errors. Tested with the real classes |
| 18 | note | `live.toml` had no thinking cap with a 1024-token output limit | The output cap is now 2048, and a comment explains `--thinking-budget`. Truncations are reported as failed requests by category |
| 19 | note | `id-token: write` covered the whole job | Tests moved to a job without it. The live job still runs `uv sync` while holding it; that is recorded here as a residual risk |
| 20 | note | The system prompt held rule knowledge the baseline lacks (the hanging-ant drop distance, switches turning off force fields) | Removed. The prompt now states only what the screen shows and the baseline's priors |
| 21 | note | The paired bootstrap treated the 20 pairs as independent | Per-scenario intervals plus a cluster bootstrap over scenarios. The pooled interval widened from [−0.329, −0.124] to [−0.439, −0.029] |
| 22 | note | `invalid_rate` mixed illegal choices with failed requests | A separate "failed requests" column and per-category counts |
| 23 | note | Three tests were weak (wall clock, prompt purity, estimate) | A wall-clock test through `run_episode`, a prompt test on a hand-made observation, and an estimate test that fails if a player is started |
| 24 | note | The labels "course choice" and "course rule" were not in the map legend | Added to the legend |
| 25 | note | The `cop.c:668-674` citation could not be checked, because the C source is not vendored | Checked by the implementer against `historicalsource/abuse@01cce80`: lines 668-674 of `abuse/src/cop.c` are the dead player's `restart_player` call in `cop_mover` |

## Found by the implementer during the review

- The scripted baseline's give-up rule counted attacks on a target that "did not change". Aliens
  show no damage, so it stopped shooting each alien after 6 attacks. This weakened the
  baseline, which would have flattered the model. Now it gives up on walls after 3 unchanged
  attacks and on enemies after 20. In the offline run, kills rose from 6.2 to 7.0 per episode
  and deaths fell from 10 to 8.
- The offline evidence was regenerated with the fixed baseline and the new report:
  `evidence/reports/offline-baselines.md`, `evidence/traces/offline-v2/`.
