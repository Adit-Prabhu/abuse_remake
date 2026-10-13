# Review record: PR #5 (player interface, baselines, runner)

- **Reviewer:** an independent read-only agent (Claude, `Explore` type, fresh context, no edit
  tools), briefed with `.claude/agents/rules-reviewer.md`. It read the code through git objects
  and ran it in memory to check behaviour.
- **Input:** the diff `feat/game-app..feat/player-interface`. Later PRs (#6, #7) had already
  changed this code, so the reviewer reported only what still applied on `feat/remastered`.
- **Date:** 2026-10-13.
- **Fixes:** on `feat/remastered`, the top of the code stack, because #6 and #7 had changed the
  same files.

**Result:** no blocking findings. The reviewer checked, and did not report:
- `attack` reads the target only while it is on screen;
- tiles never change at runtime, so the automap cannot see off-screen changes;
- no hidden ant is on screen in any scenario's start view;
- refusals leave the state hash unchanged;
- a switch `use` matches the edge-triggered `switcher_ai`;
- the baselines import no engine code;
- the end message carries no progress.

| # | Severity | Finding (summarised) | Resolution |
|---|---|---|---|
| 1 | should fix | Events from the last accepted action were sent again after every refused action, so M1/M2 history repeated kills and pickups | Events are cleared at every decision. Test: `test_refused_actions_report_no_events_of_their_own` |
| 2 | should fix | `weapon laser` sent no key: it wrote `pending_weapon` into the engine, and only took effect on the next action | Number keys for weapons with ammo; Ctrl, one press per tick, until the laser is selected, as the original allows. Test: `test_switching_to_the_laser_uses_the_original_keys_and_takes_effect_at_once` |
| 3 | should fix | The start message carried the episode seed, which is exactly the random table's start position | The seed is no longer sent. The random player seeds itself from its first observation. The docstrings no longer overclaim isolation |
| 4 | should fix | The controllers had almost no tests: the cap, early stops, the one-tick fallback, seen-tiles-only planning, `blocked_cells`, progress, an accepted `weapon` action, the segment scenarios | Tests added for each. `test_tick_limit_ends_the_episode` now checks the exact tick count |
| 5 | note | Labels were given on intermediate ticks, so gaps in the numbering revealed objects never shown, and objects first seen together were numbered in level-file order | Labels are given only by observations, nearest first. Test: `test_labels_are_given_only_at_decision_time_nearest_first` |
| 6 | note | Events were checked against the view at observation time, not at the tick they happened | Each event is checked when it happens (`_note_events`) |
| 7 | note | The progress doc mentioned only doors. Hidden walls, force fields, always-on teleporters and lifts were not mentioned, and progress was sampled only between decisions | Docs list all of these. Progress is now sampled every tick |
| 8 | note | `shots_fired` counted enemy shots, and `kills` counted every enemy death | `shots_fired` counts the player's own `shot` events (fixed with PR #7). The docs say what `kills` counts |
| 9 | note | The docstring did not mention `attack`'s exception or that matching normalises case | Docstring corrected |
| 10 | note | Segment scenarios start in a fresh level; the docs did not say so | Stated in `docs/evaluation.md` |
| 11 | note | The `dev_draw` check was static. The activation filters and cross-process determinism were untested | Behavioural tests: a hidden ant, and an ammo icon linked to a switch, are hidden until activated. A determinism test runs in two processes with different `PYTHONHASHSEED` |
| 12 | note | `copy` was imported only to export it | Now used, and no longer exported |

## Effect on the evidence

Three changes alter the observations and results, so the offline run was redone
(`evidence/traces/offline-v3`): label order, per-tick progress, and the random player's seeding.
On the full level, random and scripted are now level (−0.002 [−0.044, 0.039]). Scripted still
wins all three segments. `docs/evaluation.md` reports this as found.
