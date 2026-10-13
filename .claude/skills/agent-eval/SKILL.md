---
name: agent-eval
description: "Use when running, extending or reporting the repeated comparison of Abuse players (random, scripted, the model player under M0/M1/M2, or any cmd: player). Keeps the comparison fair, the spending approved, every episode reported, and the evidence reproducible."
---

# Run a fair repeated comparison

`abuse-eval` (`src/abuse_remake/agent/evaluate.py`) runs every player on every scenario and seed
in a config, under the same budgets. This skill is the procedure around it.

## Steps

1. **Write the config before running.** Put it in `eval/configs/<name>.toml` and commit it.
   - Every player gets the same `scenarios`, `seeds`, `difficulty` and `[budgets]`.
   - Model players are marked `live = true` and differ only in what is being compared, for
     example `--memory M0|M1|M2`.
   - Never put a model ID in the config: it comes from `COURSE_MODEL` at run time.
   - Fill `[prices]` from the provider's price page, with its `date` and `source`, or leave
     it empty. Never guess a price.
2. **Run the offline part first.** Run `uv run abuse-eval run --config <cfg> --jobs 6` without
   `--live`. It checks the baselines and the report. The live players are listed as not run.
3. **Estimate and ask.** Run `uv run abuse-eval estimate --config <cfg>`. It makes no calls. Show
   the student the episodes, the requests, the tokens and the cost, and wait for approval.
   Never spend credits without it. Do not touch credentials yourself; the student sets them up.
4. **Smoke-test the live path.** With approval, run
   `abuse-eval run --config eval/configs/live-smoke.toml --live`. Check the trace for real
   answers, the model that answered, the token counts and the failed-request categories.
   Stop if every request fails.
5. **Run the comparison.** Use `abuse-eval run --config <cfg> --live --out runs/<name>`. Split
   long runs with `--only <labels>` and `--resume` into the same `--out`. Results are written
   as episodes finish. Never re-run an episode because it went badly: every planned episode
   is reported.
6. **Report.** Run `abuse-eval report runs/<name> --report-to docs/evaluation-report.md`. Read
   it before quoting it:
   - the success intervals are Wilson intervals;
   - intervals over seeds can have zero width for a deterministic player;
   - the pooled paired comparison uses the cluster bootstrap over scenarios;
   - failed requests (provider problems) are not the same as illegal choices.
7. **Keep the evidence.** Copy the report, `results.jsonl` and `config.json` to
   `evidence/reports/`, and a few traces (a win or the best run, a typical run and a failure)
   to `evidence/traces/<run>/`. Check that `abuse-replay --trace <file> --headless` reproduces
   them (no mismatches).
8. **Write the conclusion honestly.** Compare under equal budgets and give the intervals. Say
   what the numbers do not show. Self-play alone does not establish learning or strong play;
   the human playtests are the human reference.

## Do not

- substitute a fixture, a cached answer or another model for a live player;
- retry failed requests or drop episodes that failed;
- give one player more decisions, ticks, skills or observation than another;
- show any player the evaluator's progress measure;
- put credentials, prompts with secrets or personal playtester data in traces or reports.
