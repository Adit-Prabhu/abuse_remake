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
(`SUITE.md`).

| Round | Date | Change and why | Tuning result (`level01-cp2`, seeds 90 and 91) |
|---|---|---|---|
| B1 | 2026-10-26 | With hidden walls no longer named (PR #25), "break through" also fires at the scenery ahead when stuck (twice per spot), then at the floor (once per spot). **Deviation:** first motivated by offline `cp2` runs that include reported seeds 0-2 (stalled at (1168, 841) on 4 of 5) and by the evaluator's A* route, against the tuning rule (`SUITE.md`). Re-checked on 2026-10-27 on the tuning set alone: without the floor shot seed 90 dies at 0.060 progress, with it 0.254 | both seeds reach the bottom floor (y 1456), breaking 17 and 18 walls; progress 0.260 on each; both die there |
| B2 | 2026-10-27 | The give-up rule (3 attacks that change nothing) compares a wall's `cracks`, since every shown wall now looks cracked and the old `damaged` flag no longer changes | 0.254 and 0.260, unchanged |
