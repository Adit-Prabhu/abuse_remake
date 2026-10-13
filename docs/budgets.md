# Budgets

Every limit, who enforces it, and what happens when it runs out. Exhaustion is recorded as its
own episode ending, so it is never confused with a death or a timeout.

| Budget | Default | Enforced by | When it runs out |
|---|---|---|---|
| Ticks per episode | 9000 for the full level, 2700 for a checkpoint segment (`scope.py`) | the episode | ends as `tick limit` |
| Decisions per episode | 600 (`Budgets.max_decisions`); the live comparison uses 200 for every player | the episode | ends as `decision budget exhausted`. Refused actions count too |
| Ticks per action | 15 (`Budgets.max_action_ticks`) | the episode's controllers | the action ends and the next decision starts |
| Input / output tokens per episode | none offline; 600k / 150k in `eval/configs/live.toml` | the runner, from the usage the player reports | ends as `token budget exhausted`. The model player also stops calling once its share is used up |
| Wall-clock time per episode | none offline; 3600 s in the live config | the runner | ends as `wall-clock budget exhausted` |
| Time per decision | 90 s (`--decision-timeout`); 60 s in the live configs | the runner's protocol client | the decision is refused (`no reply within ... s`) |
| Time per model request | 20 s (`--timeout`), one attempt | the provider adapter (SDK timeout; SDK retries off) | the decision is refused with category `timeout` |
| Output tokens per model request | 1024 (`--max-output-tokens`) | the provider | the decision is refused with category `truncated`; its tokens still count |
| Tokens per run | 30M input / 4M output in the live config | `abuse-eval` | later live episodes are listed as `not run: run token budget exhausted` |

## Notes

- **Equal budgets.** In a comparison every player gets the same tick, decision and per-action
  limits. Only model players use tokens. The game is paused while any player decides, so slow
  players gain or lose no game time.
- **No automatic paid retries.** A failed request is a refused decision. It spends a decision
  and is counted, and the model sees the refusal in its next observation.
- **Token counts.** They come from the provider's usage fields: for Gemini, prompt tokens and
  candidate plus thinking tokens; for Claude, input (including cache reads and writes) and output
  tokens; for OpenAI, prompt and completion tokens. The model player reports them per decision
  and the runner sums them. Budgets are checked after each decision, so the last request of an
  episode can go past a cap by at most one request.
- **Estimate first.** `uv run abuse-eval estimate --config eval/configs/live.toml` prints the
  number of live episodes and requests, the estimated input tokens (about 1,800 per decision,
  from measured prompt sizes), the worst-case output tokens, and the cost once `[prices]` in the
  config is filled in from the provider's price page with its date. It makes no calls.

## Tests

`tests/test_player_interface.py`:
- `test_decision_budget_ends_the_episode`
- `test_tick_limit_ends_the_episode`

`tests/test_model_player.py`:
- `test_token_budget_ends_the_episode_as_its_own_outcome`
- `test_player_stops_calling_when_its_budget_is_spent`
- `test_wall_clock_budget`

`tests/test_evaluate.py`:
- `test_live_episodes_respect_the_episode_and_run_token_caps`
- `test_estimate_and_cost_make_no_calls`
