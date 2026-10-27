# Progress and handoff notes

This page lets a fresh session (human or agent) pick up the build. Update it with every push.
The approved plan is summarised in the "Branches and PRs" table below; `SCOPE.md` is the scope
record.

## Remastered polish (2026-10-15)

The student played the stack and reported:
- Horde on Level 2 felt poorly made: you could fall into holes and never get back up;
- the upgrade cards (blue boxes) did not match the game's look;
- nobody said how to use a power-up;
- unexplained white bars on screen;
- the window could not be resized or put into full screen;
- training seemed to be gone;
- the ghost had a black background again.

Causes and fixes (R6, #20, `feat/rm-polish` on R5):
- **The white bars and the ghost's box were one macOS-only bug.** The macOS window surface has an
  alpha channel; drawing straight onto it made pygame-ce fill every text box and the ghost's
  rectangle. The dummy driver used by tests and screenshots has no alpha, so it never showed.
  Frames are now drawn on opaque surfaces (`game/display.py`, `tests/test_display.py`), checked
  on the real Cocoa driver too.
- **Holes.** Horde removes every object, including the ladders and lifts out of each room. The
  arenas are now sealed with the level's own tiles (`horde.SEALS`); Horde traces are version 3.
- **Look and teaching.** The cards, the HUD and every Remastered screen are drawn from the
  original's interface art (`game/ui.py`, `modern_hud.py`, `screens.py`). Every HUD element is
  labelled, powers show how to use them, Horde has a briefing, and F1 explains the controls and
  the screen.
- **Full screen.** A resizable, scaled window; F11, Alt+Enter or Cmd+F.
- **Training.** It was there, but the title started at Level 1 and only the L key reached it.
  The title is now a menu whose campaign starts with Training.

Still the student's: play it on their Mac and accept or reject the feel.

## Midterm fixes (from 2026-10-26)

`docs/reviews/midterm-audit-2026-10-26.md` is the audit against the course rubric, with the
student's decisions. The fixes are stacked on #20, one PR each, and the student merges them in
order.

| PR | Branch | Contents | Review |
|---|---|---|---|
| #21 | `fix/episode-limits` | The decision that reaches the cap runs its ticks. Offline evidence regenerated as `offline-v4`, and every committed trace replays in CI (`tests/test_evidence.py`) | `docs/reviews/PR-21.md` (with a follow-up) |
| #22 | `eval/midterm-suite` | `SUITE.md`, `eval/configs/midterm.toml` and `midterm-tuning.toml`, declared before any live call; per-scenario budgets; runs record `src_tree` and `prompt_sha` | harness only, no rule change |
| #23 | `docs/midterm-rubric` | `SCOPE.md` rewritten; rule map relabelled to `code/manual/observed/assumed/design`; provenance and publication terms; the boundary's two judgement calls (hidden walls, HUD strip); a README for the course folder with the design-choices table; a 15-minute playtest protocol; a 4:30 recording script | docs, plus the boundary screenshots and their script |
| #24 | `chore/course-package` | The course workflow, the export script, `EVALUATION.md`, and the config record on the declared suite | packaging |
| #25 | `fix/hidden-walls` | A hidden wall is shown only as it looks (cracked: a `wall_block`; drawn as scenery: remembered solid cells; background: nothing), from per-frame renders; `fire left/right/up/down`; `attack` and `fire` hold fire only while the gun turns and return fire when hurt; the baseline adapted on the tuning set (with a recorded deviation); evidence regenerated from a clean commit | `docs/reviews/PR-25.md` (two follow-ups) |
| #26 | `eval/live-run` | Dated Vertex prices; run caps that keep smoke, tuning and the reported run under USD 9.66 | config only |
| #27 | `feat/level01-route` | The solver's Classic mode, scenario starts, `--press` and `--min-hp`; Level 1 finished from START (1,414 ticks) and from every checkpoint scenario, replayed in CI; `docs/level01-route.md` | `docs/reviews/PR-27.md` |

Still to come:
- the live smoke run, tuning (`docs/prompt-log.md`), the freeze and the reported run;
- the course submission, which the student makes: `scripts/export_submission.py` builds the
  `midterms/adit-prabhu/` folder in a clone of the course repository.

The student owns:
- `AGENT-TEAM.md` in their own voice, and the limitations paragraph;
- the peer playtest (notes due 2026-11-06) and the recording;
- making the repository public;
- the merges, and submitting on CourseWorks by 2026-11-07.

## Remastered expansion (2026-10-14)

The student chose to grow Remastered mode, and approved the plan:
- the shareware training level and Level 2, joined to Level 1 as a campaign;
- the four original power-ups;
- Horde 2: new enemies, upgrade cards, a boss every fifth wave, more arenas, score and high
  scores.

Classic mode and the agent evaluations are unchanged. `tests/test_classic_golden.py` pins Classic
state hashes computed on `main` before the work.

| Stage | Branch | Parent | Contents |
|---|---|---|---|
| R1 (#15) | `feat/rm-levels` | `main` | Shareware `level00`/`level02` vendored with provenance; strict loading per level; `engine/campaign.py` (exits, playability, the exit rule); `Game(carry=)` level changes; `--level`, L picker, carry-on, per-level records; traces follow level changes |
| R2 (#16) | `feat/rm-training` | R1 | Training level objects (ladders, lava, springs, switch ball, training messages, flyers, straight rockets), the four power-ups, power drawing and HUD, extra power-ups placed in the training level, `scripts/route_search.py`, `evidence/routes/level00.json` |
| R3 (#17) | `feat/rm-level02` | R2 | Level 2 objects (blocks, steps, pushers, tracking gun, cleaner robot, Juggernaut, thrown grenades), Level 2 route |
| R4 (#18) | `feat/rm-horde2` | R3 | Horde 2: arenas (prison, rooftop, Juggernaut floor), roster, boss, cards, score and combos, top-10 tables |
| R5 (#19) | `docs/rm-evidence` | R4 | Screenshots (`scripts/remastered_evidence.py`, `evidence/remastered/`), review records, these notes |
| R6 (#20) | `feat/rm-polish` | R5 | The macOS display fix, a resizable window and full screen, sealed Horde arenas, the interface in the original's art (title menu, HUD, cards, briefing, controls screen), power prompts |

How to pick it up:
- `uv run abuse-remake` opens the title menu: PLAY CAMPAIGN (left and right choose the start
  level) or HORDE (left and right choose the arena). `--level level00` and `--horde --arena
  rooftop` do the same from the command line.
- `uv run python scripts/route_search.py --level level02 --goal level03 --via "x,y;..." --out F`
  finds a route; `tests/test_campaign_routes.py` replays every saved route.
- A new campaign level needs:
  - its file in `data/original/levels` with provenance;
  - its types in `scope.LEVEL_TYPES`;
  - every behaviour ported (`campaign.unported` lists what is missing);
  - a route in `evidence/routes`.

What the student still has to do:
- play each level and Horde, and judge the feel;
- confirm the dated SCOPE.md draft;
- merge the stack in order.
Nothing here is a human playtest.

Merge order is #15 to #19. The stack is based on `main`, not on the Neon PRs (#9-#14); whichever
merges second needs a small rebase in `app.py` and `controls.py`. Review records are in
`docs/reviews/PR-15.md` to `PR-18.md`.

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

Milestones 1-9 are done and reviewed. The open work is listed under "Midterm fixes" at the top
of this page:
1. **The live comparison**, which waits on the student's Vertex credentials
   (`gcloud auth application-default login` and a project ID). Then, in order, as `SUITE.md`
   says: `abuse-eval estimate` on `eval/configs/midterm.toml`, the 20-request `live-smoke`, at
   most two tuning rounds on `midterm-tuning.toml` (logged in `docs/prompt-log.md`), the freeze,
   the reported run, and the results in `EVALUATION.md`. Commands are in `docs/evaluation.md`.
   Prices and run caps are already filled in.
2. The student-owned items listed there: the merges, `AGENT-TEAM.md`, the peer playtest, the
   recording, making the repository public, and the course submission.

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

See "The student owns" under "Midterm fixes" at the top of this page. The midterm needs no
release tag and no Asana links.
