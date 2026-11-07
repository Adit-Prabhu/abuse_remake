# Tuning log (prompt and baseline)

Every prompt tuning round for the midterm suite (`SUITE.md`), in order. A round runs
`eval/configs/midterm-tuning.toml` only (`level01-cp2`, seeds 90 and 91); the reported suite is
never used for tuning. `prompt_sha` is the hash of `src/abuse_remake/agent/prompts.py` that
`abuse-eval` records in each run's `config.json`.

| Round | Date | `prompt_sha` | What changed and why | Tuning result (scripted vs model-M1) | Run |
|---|---|---|---|---|---|
| 0 | 2026-10-26 | declared `053f8d59b6c6`; now `4b949a8cede1` | The prompt as declared, before any live call. Changed before any tuning round by the interface fix (PR #25): it now describes `fire`, cracked walls, which actions ignore new threats, and the tip that shooting a wall or floor that stops you may show that it breaks. The tip shares the deviation recorded in `SUITE.md` | not yet run | |

## Baseline rounds

The scripted baseline may be changed only on the same tuning set, before the freeze
(`SUITE.md`). Each result below comes from `eval/configs/midterm-tuning-offline.toml` (scripted
only, `level01-cp2`, seeds 90 and 91, no model calls) at the commit named, so it can be re-run.

| Round | Date | Change and why | Result (seed 90, seed 91) | At |
|---|---|---|---|---|
| B1 | 2026-10-26 | With hidden walls no longer named (PR #25), "break through" also fires at the scenery ahead when stuck (twice per spot), then at the floor (once per spot). **Deviation:** first motivated by offline `cp2` runs that include reported seeds 0-2 (stalled at (1168, 841) on 4 of 5) and by the evaluator's A* route, against the tuning rule (`SUITE.md`) | 0.260, 0.260 (17 and 18 walls broken) | `f611a7b` (PR #25 as first opened) |
| B1 re-check | 2026-10-27 | The same rule judged on the tuning set alone, with and without the floor shot | without: 0.060, 0.260; with: 0.254, 0.260 | `5d26519` |
| B2 | 2026-10-27 | The give-up rule (3 attacks that change nothing) compares a wall's `cracks`, since the old `damaged` flag no longer changes | 0.254, 0.260 | `5d26519` |
| check | 2026-10-27 | No baseline change. The interface's second review fixes (the look table, aiming, returning fire) apply to every player | 0.260, 0.254 | `5aef372` (the row was added in that commit; its `src` is the code that ran) |
| check | 2026-10-27 | No baseline change. The interface's last review fixes (10-degree aim, return fire capped at 6 ticks) apply to every player | 0.254, 0.254 | `72733d7` |
