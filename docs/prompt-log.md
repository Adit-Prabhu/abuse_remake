# Prompt log

Every prompt tuning round for the midterm suite (`SUITE.md`), in order. A round runs
`eval/configs/midterm-tuning.toml` only (`level01-cp2`, seeds 90 and 91); the reported suite is
never used for tuning. `prompt_sha` is the hash of `src/abuse_remake/agent/prompts.py` that
`abuse-eval` records in each run's `config.json`.

| Round | Date | `prompt_sha` | What changed and why | Tuning result (scripted vs model-M1) | Run |
|---|---|---|---|---|---|
| 0 | | | The prompt as declared, unchanged | | |
