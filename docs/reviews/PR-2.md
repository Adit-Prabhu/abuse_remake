# Review record: PR #2 (engine core)

- **Reviewer:** an independent read-only agent (Claude, `Explore` type, fresh context, no edit
  tools), briefed with `.claude/agents/rules-reviewer.md`. The implementation agent did not
  review its own change.
- **Input:** the diff `feat/scaffold-data..feat/engine-core`, the original C at
  `historicalsource/abuse@01cce80`, and `data/original/lisp`.
- **Date:** 2026-10-13. The reviewer found no blocking issues.

The student decides every finding; this table records what changed in response.

| # | Severity | Finding (summarised) | Resolution |
|---|---|---|---|
| 1 | should fix | The default play view is 316x162, not 311x151. `recalc_local_view_space` (`view.c:636-676`) runs at start-up, and the view size decides which objects run each tick | Fixed in `engine/view.py`. The map row is now `code`, and the open question is closed |
| 2 | should fix | The laser-rate tests used ranges, so they could not catch a change in the fire delay | They now assert exact intervals: 3 ticks with ammo, 5 without |
| 3 | should fix | The jump test never checked `yvel == -15` | It asserts `yvel == -15` and a 15 px rise on the jump tick |
| 4 | should fix | The RNG test compared the generator with itself | It pins the first five table entries, derived from the jrand.c LCG |
| 5 | should fix | No tests for damage and health scaling, the random order in `bottom_damage`, `hurt_radius`, grenade and rocket behaviour, the ammo cap and weapon switching, or weapon refusal | Added a test for each |
| 6 | should fix | `World.bg` (the map) shadowed the `bg()` method | Renamed the map to `bg_map` |
| 7 | note | The integer `*` evaluates each argument twice, so `(* dir (random 10))` draws two numbers | Ported in `create_dead_parts`; documented in `lmul` and in the map |
| 8 | note | The rocket's top speed is 15/11, not 14/10 | Map row corrected; a test checks the 7, 9, 11, 13, 15 sequence |
| 9 | note | `rocket_ai` used the raw `set_aistate`; the Lisp version zeroes `aistate_time` | Now uses the Lisp semantics |
| 10 | note | `create` runs `defaults()` at (0,0) before setting x and y | Ported in that order |
| 11 | note | `decide()` treated a returned 0 as nil | Only nil (`None` or `False`) deletes an object now |
| 12 | note | Some citations lacked line numbers | Added: collide.c 147-222 and 212, explo.lsp 25-36, jrand.c 8-21, the lisp.c cases, options.lsp 14 and 36, abuse.lsp 40-42 |
| 13 | note | Rows labelled `observed` cited only our own tests | `observed` now means running the original's data or compiled code; port tests are cited as checks |
| 14 | note | The differential test would skip without a compiler | CI sets `ABUSE_REQUIRE_C_REFERENCE=1`, so a missing compiler fails the build. The CI logs show the C tests running |

The reviewer also checked these against the original, line by line, and found no difference:

- the trig and atan tables;
- `setback_intersect`, `foreground_intersect`, `check_collisions`;
- `tick`, `mover`, `float_tick`, `bmove`, `try_move`, `next_sequence`, `damage_fun`;
- `hurt_radius`, `add_actives`/`pull_actives`, and the level tick order;
- `top_ai`, `player_fire_weapon`, the three ufuns, `cop_mover`, `bottom_damage`, `give_player_health`;
- the view's ammo and weapon cycling;
- `sgun_ai`, `fire_object` types 2, 3, 5 and 10, the grenade, firebomb and rocket AIs, and `do_explo`.
