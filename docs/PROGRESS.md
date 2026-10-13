# Progress and handoff notes

This page lets a fresh session (human or agent) pick up the build. Update it with every push.
The approved plan is summarised in the "Branches and PRs" table below; `SCOPE.md` is the scope
record.

## Neon Protocol v2 (2026-10-13, replaces v1)

The student played v1 and rejected it:
- a one-floor map;
- NPC-like enemies;
- drawn-line weapons;
- synthesised beeps.

They approved the v2 plan: the Warped City runner as the hero, three sectors and a boss,
Horde kept and upgraded. They asked that Remastered and Classic stay exactly as they are.

| Stage | Branch | Parent | Contents |
|---|---|---|---|
| Engine | `feat/neon2-engine` | `feat/neon-validation` (#11) | `engine/neon/` package: maps, physics, AI, weapons, boss, Horde v2, training, nav model, development autopilot, `neon-trace-2` replay. Removes all of v1 |
| Presentation | `feat/neon2-presentation` | `feat/neon2-engine` | `game/neon/`: renderer, HUD, menus, manual, sound and music; vendored assets with manifest; release bundling |
| Validation | `feat/neon2-validation` | `feat/neon2-presentation` | Evidence screenshots, replay-checked trace, docs, review records |

Merge order is #9, #10, #11, then the three v2 stages. v2 replaces everything v1 added, so the
student may prefer to close #9–#11 and rebase the v2 stack onto `main`. That is the student's
call; agents never merge.

How to pick it up:
- `uv run abuse-remake --mode neon` plays.
- `uv run python scripts/neon_evidence.py` regenerates `evidence/neon/`.
- Maps are ASCII files in `src/abuse_remake/engine/neon/maps/`. Edit them directly; the
  tile-graph check in `tests/test_neon_engine.py` reports anything unreachable.
- `uv run python scripts/vendor_neon_assets.py` re-vendors the assets (needs network and ffmpeg).

Validation at the end of the session:
- The full suite passes and Ruff is clean.
- The autopilot wins the campaign:
  - hard: seeds 1–3 with 0 deaths;
  - extreme: seeds 1–3 with 0–6 deaths.
- The evidence run (hard, seed 7) wins in 268 game-seconds; its trace replays 4 checks with
  0 mismatches.
- The student still needs to play it and judge the feel; nothing here is a human playtest.

## Neon Protocol expansion (2026-10-13)

The student approved the plan in `docs/neon-protocol.md`: separate futuristic campaign AND
Horde, new combat/art, visible controls, tutorial, and transparency fixes. Earlier PRs #1–#8
are now merged (confirmed against GitHub); the historical table below records their old handoff.

| Stage | Branch | Branch parent | State |
|---|---|---|---|
| Simulation | `feat/neon-engine` (#9) | `main` | Pushed; independent review found five issues, all fixed with failing regression tests |
| Playable presentation/tutorial | `feat/neon-playable` (#10) | `feat/neon-engine` | Pushed; independent review found two trace lifecycle issues, fixed with failed-before-fix regressions |
| Art revision/validation/release | `feat/neon-validation` (#11) | `feat/neon-playable` | Pushed; both final reviews resolved; 244 local tests pass; standalone Classic/Neon campaign/Horde/training smoke checks pass |

Merge ownership remains with the student. These branches will be pushed as milestones finish;
no live model calls are needed. Development uses `.claude/skills/port-classic-rule/SKILL.md`,
with honest `neon design` evidence labels for new optional rules.

All three PRs target `main`, matching #1–#8's workflow. Merge #9, then #10, then #11; the
later PR diffs shrink as earlier milestones merge. Branches themselves are stacked so the
latest checkout is the complete playable game. No agent merges or tags.

Neon's final art is vendored under `assets/neon/` with licence text and SHA-256 manifest.
The new renderer reads assets through `paths.assets_root`; release bundles must include
`assets/neon` as well as original data. World view is 640×360 with a 960×540 HUD; mouse
mapping uses world size. The first two PRs describe the earlier milestone snapshots; the
third PR replaces prototype wireframes with artist sprites and textured industrial scenery.

Final validation: required-C suite 244 passed; Ruff src/tests/scripts passes; original-data
checksums and all 101 artist-asset hashes match. `scripts/neon_evidence.py` generates actual
screenshots and a developer-controller trace: Hard campaign seed 7 wins at 533 ticks, all
three relays/11 enemies, four replay hash checks with zero mismatches. Five Hard seeds
complete using normal controls in the tests. These are development checks, not human results.

A macOS PyInstaller standalone executable was built under `/private/tmp/neon-bundle/dist/`
with original data and Neon assets included. It was run from `/private/tmp` in Classic and
all three Neon variants, writing screenshots successfully. Executable tests needed sandbox
escalation because PyInstaller's process semaphore is denied inside the sandbox. No tag or
release was pushed; the release workflow will exercise these modes on each supported OS.

Independent reviews: `docs/reviews/PR-9.md`, `PR-10.md`, `PR-11.md`. Final review follow-ups
report no unresolved findings. CI originally caught licence CRLF normalization against the
manifest; `.gitattributes` now preserves those upstream bytes. GitHub push and PR CI both
pass on Python 3.11 and 3.12 for gameplay/art commit `0ec79cd`; security checks also pass.

## Branches and PRs (stacked; the student merges in order, agents never merge)

| Milestone | Branch | PR | State |
|---|---|---|---|
| 1. Scaffold, data, format readers | `feat/scaffold-data` | #1 | reviewed (`docs/reviews/PR-1.md`), awaiting merge |
| 2. Engine core | `feat/engine-core` | #2 | reviewed (`docs/reviews/PR-2.md`), fixes in, awaiting merge |
| 3. Every Level 1 object | `feat/level01-objects` | #3 | reviewed (`docs/reviews/PR-3.md`), fixes in, awaiting merge |
| 4. Playable game (pygame, modern rendering) | `feat/game-app` | #4 | reviewed (`docs/reviews/PR-4.md`); fixes landed on `feat/remastered` |
| 5. Player interface, baselines, runner, traces | `feat/player-interface` | #5 | reviewed (`docs/reviews/PR-5.md`); fixes landed on `feat/remastered` |
| 6+7. Model player, providers, memory conditions, `abuse-eval`, live-eval workflow | `feat/model-player` | #6 | reviewed (`docs/reviews/PR-6.md`), all fixes in |
| 8. Remastered mode | `feat/remastered` (on top of #6) | #7 | reviewed (`docs/reviews/PR-7.md`), all fixes in; also carries PR #5's fixes |
| 9. Evidence, docs, release | `docs/evidence` (on top of #7) | #8 | done except the human-owned items below |

Milestones 6 and 7 share one branch: the live comparison needs both the model player and the
evaluation harness.

## Current state (milestones 6 and 7, `feat/model-player`)

- `agent/providers/`: one adapter per SDK.
  - `vertex.py` (google-genai, the default), `anthropic_provider.py`, `openai_provider.py`.
  - Each makes one request per decision with structured JSON output, a 20 s timeout, an output
    cap and no retries.
  - The model comes from `--model` or `COURSE_MODEL`.
  - Failures raise `ProviderError` with a category.
- `agent/prompts.py`: the system prompt (manual-level knowledge plus the baseline's priors, no map
  knowledge) and the turn renderer (status, screen map with `@` and object letters, objects,
  events, memory, legal actions).
- `agent/memory.py`: M0, M1 (last 8 turns), M2 (plus notes up to 600 characters and an automap
  summary).
- `agent/players/model_player.py`: `ModelPlayer` and `check_config`. It passes the model's
  action through unchanged, and failures become refused decisions.
- `agent/runner.py`:
  - token and wall-clock budgets, ended through `AbuseEpisode.stop`;
  - the provider, model and memory recorded in the outcome;
  - `error` and `player_error` kept apart in traces.
- `agent/evaluate.py` and `agent/stats.py`: `abuse-eval run/estimate/report`, with bootstrap CIs,
  paired tables and run-level token caps.
- Configs: `eval/configs/offline.toml`, `live.toml` (Vertex, M0/M1/M2, 200 decisions),
  `live-smoke.toml`, `ci-smoke.toml`.
- `.github/workflows/live-eval.yml`: manual, default branch only, Workload Identity Federation.
- The protocol now refuses any reply that is not a JSON object (a bare `wait` used to be
  accepted).
- Docs: `information-boundary.md`, `action-interface.md`, `budgets.md`, `evaluation.md`, and a
  new map section for the agent-interface course choices.
- Evidence: `evidence/reports/offline-baselines.md` (scripted beats random: paired difference
  −0.219 [−0.329, −0.124]), plus three traces.
- Measured: a turn prompt is about 2.8k characters plus a 2.8k-character system prompt, about
  1,800 tokens per decision with M2.
- After the PR #6 review:
  - one decision is one request (Vertex continuation is off);
  - players get a minimal environment and never the evaluator's progress;
  - late replies are dropped by request id;
  - fatal credential errors end an episode as `player failed`;
  - results are written as they finish, and `--only`/`--resume` split long live runs;
  - success uses Wilson intervals and pooled pairs a cluster bootstrap;
  - failed requests are reported apart from illegal choices.
  See `docs/reviews/PR-6.md`.

## Milestone 9 (`docs/evidence`)

- `agent-config.json` (course-1), checked against the code by `tests/test_agent_config.py`.
- Skills: `.claude/skills/port-classic-rule/` and `.claude/skills/agent-eval/`.
- Docs: `agent-team-log.md`, `human-responsibility.md`, `playtests/protocol.md` and
  `playtests/template.md`, `demo.md`, and the README's submission checklist.
- `.github/workflows/release.yml`: PyInstaller builds on a version tag. The one-file build was
  tested locally on macOS: 21 MB, and it runs headless from another directory.
- `evidence/video/scripted-level01-cp3-s0.mp4`, generated by `abuse-replay` from the evidence
  trace.

## Next steps

1. Every milestone PR (#1–#7) now has an independent review record with all findings resolved.
   The remaining work is the human-owned items below.
2. **Live comparison (human-gated).**
   - The owner sets up Vertex: `gcloud auth application-default login`, `GOOGLE_CLOUD_PROJECT`,
     `GOOGLE_CLOUD_LOCATION`, and `COURSE_MODEL` (a Gemini ID).
   - The owner fills in `[prices]` in `eval/configs/live.toml`.
   - Show `abuse-eval estimate`, get approval, run `live-smoke`, then `live`, with
     `--report-to docs/evaluation-report.md`.
   - Commit a few traces under `evidence/traces/`.
3. Milestone 8, Remastered mode: dash, stats screen, quick restart, ghost race, AI spectator,
   Horde.
4. Milestone 9:
   - `agent-config.json` (course-1);
   - skills `.claude/skills/port-classic-rule/` and `.claude/skills/agent-eval/`;
   - docs: `agent-team-log.md`, `human-responsibility.md`, `playtests/protocol.md` and
     `playtests/template.md`, `demo.md`;
   - `release.yml` (PyInstaller on tag);
   - the README submission checklist;
   - `abuse-replay` to MP4, and the demo video.

## Facts established from the source (cite these in the map)

- **Timing:** logic is capped at 15 fps (`game.c:1630-1633`). Each loop iteration reads input,
  then steps (active area, then `level::tick`), then draws (`game.c:2650-2670`).
- **Active area:** the view rectangle plus a quarter of its size on each side, with each
  object's `range` (`game.c:1983-1998`). Objects outside it do not tick.
- **Camera:** with no scroll ranges, `last_x` follows the player exactly.
  `xoff = last_x - w/2 + shift_right + pan_x`; `yoff = last_y - h/2 - shift_down + pan_y`;
  both are clamped at 0 or more (`view.c:98-140`).
- **Controls** (`input.lsp`): arrows move; up jumps or climbs; down is the action key
  (`pressing_action_key`). Mouse aim; the left button is fire (b2), the right button special
  (b1). Weapon keys 1-7; Ctrl for the previous weapon, Insert/PageUp for the next
  (`view.c:586-617`).
- **Laser:** with ammo it fires every 3 ticks and uses 1 ammo. With no ammo it still fires
  every 5 ticks and uses none (`cop.c:238-265`).
- **Weapon order** (the order of `is_weapon` flags): MGUN 0, GRENADE 1, ROCKET 2, FIREBOMB 3.
- **Difficulty:** the default is `hard` (`abuse/hardness.lsp`). `max_hp` is 200
  (`clisp.c:137`).
- **Level 1:** `tick_counter` starts at 80002 from the file. START is at (167, 43); the exit
  is at (2715, 306).
- **Data lineage:** see `docs/data-lineage.md`.

## Reference sources (not committed; re-fetch into a scratch folder)

- C engine: `git clone https://github.com/historicalsource/abuse` and check out `01cce80`.
- Original releases for comparison: `uv run python scripts/compare_original_data.py`
  downloads and checks them into `cache/`.
- C reference harnesses for differential tests are in `tests/c_reference/`. They are built
  from verbatim original code.

## Human-owned items still open

- Confirm `SCOPE.md` against the Session 2 agreement.
- Merge the PRs in order, and push tag `v1.0.0` at the end.
- Set up Vertex credentials before the live evaluation.
- Peer playtests, the narrated demo, and Asana links.
