# Review record: PR #4 (the playable game)

- **Reviewer:** an independent read-only agent (Claude, `Explore` type, fresh context, no edit
  tools), briefed with `.claude/agents/rules-reviewer.md`. It read the code through git objects,
  read the original C at `01cce80`, and ran the game headless in memory to reproduce behaviour.
- **Input:** the diff `feat/level01-objects..feat/game-app`. Later PRs had already changed the app,
  so the reviewer reported only what still applied on the top branch.
- **Date:** 2026-10-13.
- **Fixes:** on `feat/remastered`, the top of the code stack.

**Result:** one blocking finding and seven should-fix findings, all fixed. The reviewer checked,
and did not report:
- the front end never uses or advances the engine's random table;
- the engine imports no pygame;
- the save is taken when and how `people.lsp:885-901` takes it;
- fire and special are on the original buttons.

| # | Severity | Finding (summarised) | Resolution |
|---|---|---|---|
| 1 | blocking | The second restore of any snapshot crashed the game, because an old bound `save_hook` inside the snapshot dragged the whole App (and pygame) into the copy | Snapshots no longer contain front-end hooks; `restore` keeps the live ones. Test: `test_restores_can_be_repeated_any_number_of_times` (three rounds of every restart kind) |
| 2 | should fix | Camera interpolation never happened: the view's `last_last` position is overwritten by the second scroll update each tick | The renderer keeps its own camera per tick (`note_tick`) and cuts on big jumps. Aiming uses the drawn camera. Test: `test_the_camera_is_interpolated_between_ticks` |
| 3 | should fix | Classic lighting did not follow `light.c`: it multiplied instead of subtracting, took the maximum of lights instead of adding them, used Euclidean distance, and lit type-9 lights fully | `light_levels` ports `calc_light_value` (integer levels, additive with `mul_div`, octagonal distance, type-9 sets the level), and Classic subtracts `63 - level` per channel as `white_light` does. Tests pin the formula and a pixel value |
| 4 | should fix | Pause→R left the old run's console save as the checkpoint | Restarting the level resets the checkpoint. Test: `test_restarting_the_level_forgets_the_old_runs_console` |
| 5 | should fix | `--record` traces could not be replayed: no restores were recorded, the trace was truncated on title toggles, and nothing read the traces | Format `human-trace-1`: `new_game`, `input`, `restore` and `check` rows (state hashes); one file per session. `abuse-replay --human-trace` replays a session, checks every hash, and scores it with the evaluator's progress. Tests: a full round trip including a real console save and both restart kinds, a tamper test, a toggle test |
| 6 | should fix | Nothing bounded the tick accumulator after a stall | At most 4 owed ticks (`MAX_CATCHUP`). Test: `test_a_long_stall_runs_only_a_few_ticks` |
| 7 | should fix | Some original controls were missing (Ctrl/Home, Insert/PageUp, the middle button), left did not win when both directions were held, and the README left out the special button | All mapped as in `input.lsp` and `view.c`. Tests: `test_input_mapping_left_wins_and_the_aim_follows_the_drawn_camera`, `test_original_weapon_keys` |
| 8 | should fix | Only two App tests existed; restarts, `restart_ai`, input, timing, the camera and lighting were untested | `tests/test_game_app.py` (14 tests), including a console save reached by real inputs |
| 9 | note | The world stops while the player is dead, and Return also restarted | Only space restarts now. The pause while dead remains, and is recorded in the map as the one difference |
| 10 | note | `screen_to_game` assumed the requested scale | It uses the real window size |
| 11 | note | Gamepad axes assumed rest at 0, and unplugging was not handled | Axes are measured against their resting value at connection; unplugging is handled |
| 12 | note | Every object was drawn, but the original draws only active ones | Classic draws only active objects. Remastered draws the inactive ones near its wider edges, standing still. Test: `test_classic_draws_only_active_objects` |
| 13 | note | The sound falloff did not follow `game::play_sound` | Ported (`original_volume`). Classic has no pan and plays every sound; Remastered adds pan. Test: `test_sound_volume_follows_game_play_sound` |
| 14 | note | The renderer docstring overclaimed: it left out the second foreground pass and the original's `interpolate_draw` switch | Docstring corrected. Level 1 has no "above" tiles |
| 15 | note | `SCOPE.md` listed interpolation, menus and the gamepad as Remastered-only | Corrected: both modes have them |

The rule map gains a "Front end" section with a row and a check for each of these.
