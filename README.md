# abuse_remake

A reconstruction of **Level 1 of Abuse** (Crack dot Com, 1996) in Python, with a model-driven
player, a scripted search baseline and a fair, repeated evaluation. This is a COMS E6998 midterm
project ("AI in Practice: Game Design and Development").

- **Classic mode** is the faithful port. It is a deterministic 15 Hz port of the original C
  engine and Lisp rules, played on the original Level 1 file. Every rule is cited in
  `docs/rule-source-map.md` with an evidence label.
- **Remastered mode** adds a wider view, lighting and particles, a dash, quick restart, a ghost
  race, an AI spectator and a Horde arena (`docs/remastered.md`). Evaluations always run Classic
  rules.
- The scope record is `SCOPE.md`. Data provenance and licences are in
  `data/original/PROVENANCE.md`, and `docs/data-lineage.md` shows the data matches the 1995 and
  1996 releases.

## Quick start

```sh
uv sync --all-extras
uv run abuse-remake                         # play (Remastered); --mode classic for the faithful port
uv run abuse-remake --horde                 # the Horde arena
uv run pytest                               # deterministic tests: no network, no model calls
uv run abuse-data verify                    # check the original data files
```

Controls:
- move: A/D or the arrow keys;
- jump: W, Up or Space;
- action (switches, doors, consoles, exit): S or Down;
- aim: the mouse; fire: the left button; special: the right button or Shift;
- weapons: 1–4, the original Ctrl/Home (previous) and Insert/PageUp (next), Q/E, the mouse wheel,
  or the middle button;
- pause: Esc; after a death, Space restarts from the last console;
- Remastered: dash F, quick restart R, ghost G.

Gamepads work too.

## Players and evaluation

```sh
uv run abuse-agent --player scripted --scenario level01-cp3 --seed 0 --trace runs/demo.jsonl
uv run abuse-replay --trace runs/demo.jsonl                  # watch it, checking every observation
uv run abuse-replay --player scripted --scenario level01     # spectate live
uv run abuse-eval run --config eval/configs/offline.toml --jobs 6
COURSE_MODEL=<model id> uv run abuse-agent --player model -- --provider vertex --memory M1
```

`docs/evaluation.md` has the full instructions, including the Vertex AI setup and the live
comparison. The model ID is never in the code: it comes from `COURSE_MODEL`.

## Submission checklist

| Assignment item | Where |
|---|---|
| Tagged playable build | Tag `v1.0.0`, which the student pushes. `.github/workflows/release.yml` then builds Linux, macOS and Windows bundles into a GitHub Release. Locally, `uv run abuse-remake` |
| Executable player | `abuse-agent` (`src/abuse_remake/agent/runner.py`). Players are separate programs speaking `src/abuse_remake/agent/protocol.py`: `random`, `scripted`, `model`, or any `cmd:<program>` |
| Explicit observation/action interface | `src/abuse_remake/agent/interface.py` (five operations), `docs/action-interface.md` |
| Scripted or search baseline | `src/abuse_remake/agent/players/baselines.py`: priority rules plus A* over the automap (`agent/nav.py`) |
| Model-driven player | `src/abuse_remake/agent/players/model_player.py`, with adapters for Vertex (default), Anthropic and OpenAI in `agent/providers/` |
| Run and evaluation instructions | This README and `docs/evaluation.md` |
| Rule and source map | `docs/rule-source-map.md` |
| Configuration record | `agent-config.json` (course-1, checked by `tests/test_agent_config.py`), `eval/configs/*.toml`, and each run's `config.json` |
| Reusable skill | `.claude/skills/port-classic-rule/SKILL.md`, `.claude/skills/agent-eval/SKILL.md` |
| Implementation and review evidence | One stacked PR per milestone (#1–#8). Independent review records for #1–#7 are in `docs/reviews/PR-<n>.md`, with the reviewer brief in `.claude/agents/rules-reviewer.md` |
| Meaningful CI tests | `.github/workflows/ci.yml` (Python 3.11 and 3.12). It covers: format readers, differential tests against compiled original C, engine and object rules, the player boundary, invalid actions, budgets, determinism, mocked providers using the real SDK error types, the eval harness, Remastered isolation, replay |
| Repeated live comparison | `eval/configs/live.toml` through `abuse-eval --live` (or `.github/workflows/live-eval.yml`), reported to `docs/evaluation-report.md`. **Not run yet:** it needs the student's Vertex setup and approval of the estimate. The offline comparison is in `evidence/reports/offline-baselines.md` |
| Episode traces | `evidence/traces/`. Every run writes `runs/<run>/traces/` |
| Information boundaries | `docs/information-boundary.md` |
| Memory and history comparison | M0, M1 and M2 in `src/abuse_remake/agent/memory.py`. The memory table in the live report compares them |
| Invalid-action handling | `docs/action-interface.md` |
| Budgets | `docs/budgets.md` |
| One-page agent-team log | `docs/agent-team-log.md` (for the student to check) |
| Peer playtest notes | `docs/playtests/protocol.md` and `template.md`. `--playtest` records a replayable trace, and `abuse-replay --human-trace` scores it with the agents' progress measure. **TODO (student):** run the sessions; agents do not write the notes |
| Recorded demonstration | Generated: `evidence/video/scripted-level01-cp3-s0.mp4`. Narrated: `docs/demo.md` scripts it. **TODO (student):** record it |
| Human responsibility | `docs/human-responsibility.md` |

## Repository map

- `src/abuse_remake/formats/`: readers for the original SPEC files, tiles, sprites and levels.
- `src/abuse_remake/engine/`: the deterministic simulation. Pure Python, with no pygame.
  - `behaviors/` holds the hand-ported Lisp and C rules.
  - `remastered.py` and `horde.py` hold the rules for Remastered only.
- `src/abuse_remake/game/`: the pygame front end (rendering, input, audio, HUD, the Remastered
  features, `abuse-replay`).
- `src/abuse_remake/agent/`: the playing-agent interface, the players and providers, the runner,
  and `abuse-eval`.
- `data/original/`: the vendored public-domain data, with checksums and provenance.
- `docs/`, `evidence/`, `eval/configs/`, `tests/`, `.github/workflows/`, `.claude/`.

`docs/PROGRESS.md` has the handoff notes for picking the work up.
