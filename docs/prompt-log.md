# Tuning log (prompt and baseline)

Every prompt tuning round for the midterm suite (`SUITE.md`), in order. A round runs
`eval/configs/midterm-tuning.toml` only (`level01-cp2`, seeds 90 and 91); the reported suite is
never used for tuning. `prompt_sha` is the hash of `src/abuse_remake/agent/prompts.py` that
`abuse-eval` records in each run's `config.json`.

| Round | Date | `prompt_sha` | What changed and why | Tuning result (scripted vs model-M1) | Run |
|---|---|---|---|---|---|
| 0 | | | The prompt as declared, unchanged | | |

## Baseline rounds

The scripted baseline may be changed only on the same tuning set, before the freeze
(`SUITE.md`).

| Round | Date | Change and why | Tuning result (`level01-cp2`, seeds 90 and 91) |
|---|---|---|---|
| B1 | 2026-10-26 | With uncracked hidden walls no longer named (PR #25), "break through" also fires at the scenery ahead when stuck (twice per spot), then at the floor (once per spot). Without the floor shot, the offline `cp2` runs stalled at (1168, 841) on 4 of 5 seeds; the evaluator's A* route goes down from there | both seeds reach the bottom floor (y 1456), breaking 17 and 18 walls; progress 0.260 on each; both die there |
