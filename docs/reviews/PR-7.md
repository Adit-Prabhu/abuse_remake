# Review record: PR #7 (Remastered mode)

- **Reviewer:** an independent read-only agent (Claude, `Explore` type, fresh context, no edit
  tools), briefed with `.claude/agents/rules-reviewer.md`. It read the branch through git
  objects, and ran engine code in memory from `git show` output to measure behaviour. The first
  run was cut off by a usage limit and was re-run in full.
- **Input:** the diff `feat/model-player..feat/remastered` at `00f97df`.
- **Date:** 2026-10-13.
- **Process note:** the reviewer wrote one unused helper file to the session scratchpad, outside
  the repo, against its read-only brief. The implementer deleted it. Nothing in the repo was touched.

**Result:** no blocking findings. Nothing in the change alters Classic behaviour or determinism:
- Classic never sets `player_iframes`;
- snapshots carry the Remastered and Horde state;
- neither new engine module imports pygame or uses unseeded randomness;
- `by_player` never reaches a player.

The implementer also checked that Classic state hashes are identical before and after the
fixes, for a scripted input run and for a scripted-baseline episode.

| # | Severity | Finding (summarised) | Resolution |
|---|---|---|---|
| 1 | should fix | Watching `--player model` skipped the runner's token, wall-clock and fatal-error stops, and the config check | The runner's stop logic is now shared (`runner.stop_reason`). The spectator sends the budgets, enforces them, takes `--max-*` options and checks a model player's setup. Test: `test_a_runner_stopped_trace_replays_and_spectating_enforces_budgets` |
| 2 | should fix | The replay check could pass a truncated trace, an edited outcome, an interrupted replay, or a runner-stopped trace | Now every step must be replayed and the outcome must match. A runner-stopped trace is ended the same way. Exit codes: 1 for a mismatch, 2 for an interrupted replay. Tests cover each case |
| 3 | should fix | The `dash` event was always lost, because `World.step` clears events | Emitted after the step. Tested |
| 4 | should fix | `--playtest` ran Remastered rules by default, and recordings left out dashes and Horde | `--playtest` defaults to Classic. Traces record dashes, `horde` and `rules`. `--horde --mode classic` is an error. Tested |
| 5 | should fix | The Horde map row claimed fidelity to `crack_ai` that the code does not have | The row and the docstring now list every difference and every Horde constant as `remastered design` |
| 6 | should fix | The "Remastered without a dash equals Classic" test never reached the damage hook | New test: the player is hurt in both modes, with the same health and state hash |
| 7 | should fix | On a slow frame, ticks continued after the level end, and `record_finish` ran again and lost "NEW BEST" | `App.advance` stops at the end. Test: 7 owed ticks give 1 tick and 1 record |
| 8 | should fix | "Accuracy" counted ants' shots and every explosion and wall hit | Replaced by the player's own shots (a new output-only `shot` event with `by_player`) and the distinct enemies hit. Damage events carry `source_uid` |
| 9 | note | The `by_player` test never used a real projectile | It now fires real player and ant shots through `fire_object` |
| 10 | note | A dash started on a teleport's first tick moved the player off the pad | A teleport or death cancels the rest of a dash. Tested |
| 11 | note | The dash left the top half 13 px behind | The top half moves with the dash |
| 12 | note | The 7-tick invulnerability was not pinned, and refusals and Horde restore were untested | Parametrised tests over ticks 1–8, refusal tests, and a Horde snapshot test |
| 13 | note | The ghost was drawn one tick ahead and not interpolated | Index fixed. The docs now say it is not interpolated |
| 14 | note | Bad records or ghost files could crash the game, and an unreadable records file was silently replaced | Entries are validated. An unreadable file is moved aside. Tested |
| 15 | note | M on the title screen could not leave Horde for Classic | Switching to Classic turns Horde off |
| 16 | note | `SCOPE.md` said visual features apply in both modes | Corrected to match the build |
| 17 | note | Horde constants had no source | Listed in the map as `remastered design` |

The agent interface's `shots_fired` counter, which PR #5's review also flagged, now counts
only the player's own `shot` events.
