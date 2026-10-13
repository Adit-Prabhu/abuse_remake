# Progress and handoff notes

This page lets a fresh session (human or agent) pick up the build. Update it with every push.
The approved plan is summarised in the "Milestones" table below; `SCOPE.md` is the scope
record.

## Branches and PRs (stacked; the student merges in order, agents never merge)

| Milestone | Branch | PR | State |
|---|---|---|---|
| 1. Scaffold, data, format readers | `feat/scaffold-data` | #1 | review done (`docs/reviews/PR-1.md`), CI green, awaiting merge |
| 2. Engine core | `feat/engine-core` (on top of #1) | not yet opened | in progress (see below) |
| 3. Every Level 1 object | `feat/level01-objects` | | not started |
| 4. Playable game (pygame, modern rendering) | `feat/game-app` | | not started |
| 5. Player interface (observe, legal actions, step, outcome) | `feat/player-interface` | | not started |
| 6. Baselines and evaluation | `feat/baselines-eval` | | not started |
| 7. Model player (Vertex, Anthropic, OpenAI) | `feat/model-player` | | not started |
| 8. Remastered mode | `feat/remastered` | | not started |
| 9. Evidence, docs, release | `docs/evidence` | | not started |

## Milestone 2 status

Done and pushed:

- `engine/cmath.py`: C truncating division, narrow-type wraps, `lisp_sin/cos/atan2`, and the
  original random table (`JRand`; the episode seed sets `rand_on`).
- `engine/tables.py`, generated from `trig.c` (the atan table's last entry is an implicit
  zero).
- `engine/geometry.py`: `setback_intersect` and `foreground_intersect`, with a prefilter.
  `foreground_intersect_reference` exists so tests can prove the prefilter changes nothing.
- `engine/chardefs.py`: 152 character types parsed from the original `def_char` forms;
  every frame resolves.
- `engine/obj.py`: `GameObject`, a port of `objects.c` (tick, mover, try_move, float_tick,
  bmove, states, damage).
- `engine/world.py`: object list, active set, `step`, collisions, `hurt_radius`, finders,
  platform and push helpers.

Next steps for milestone 2:

1. `engine/view.py`: the `View` class. A port of `view.c`:
   - view rectangle 311x151 (`game.c` `make_screen_size(311,160)`);
   - `shift_down` 15, `no_x*` scroll ranges 0, ambient 32;
   - weapons start at -1, with `weapons[0] = 0`;
   - `add_ammo` is capped at 999; when the current weapon empties it switches to the most
     powerful weapon, skipping index 3 (`switch_to_powerful` is true);
   - `next_weapon` / `last_weapon` / number keys;
   - `configure_for_area`; `apply_pending_weapon_change`;
   - `has_weapon` = god or the weapon is not -1.
2. `engine/behaviors/`: a registry of Lisp function name → Python callable.
   - Player: `cop_mover`, `top_ai`, `laser_ufun`, `top_ufun`, `player_rocket_ufun`,
     `bottom_damage`, `cop_ufun`, all from `cop.c` and `people.lsp`.
   - Weapons: `fire_object` (`guns.lsp:34`), `sgun_ai` (C), `grenade_ai`, `firebomb_ai`,
     `rocket_ai`, explosions (`exp_ai`, `explo_light`, `do_explo`).
   - Setting up a player: create DARNEL at START (`add_object_after`); `cop_mover` creates the
     `MGUN_TOP` top half.
3. `engine/game.py`: a `Game` facade that loads the level, creates the player view, holds the
   difficulty and seed, and offers `step(inputs)`.
4. Tests:
   - physics goldens (run speed, jump arc, stop);
   - a differential test of `setback_intersect` against the compiled original `intsect.c`
     (add `tests/c_reference/intsect.c` built from the original verbatim);
   - prefilter equivalence;
   - determinism (same seed and inputs give the same state hash).
5. Add rows to `docs/rule-source-map.md`, run an independent review (save it as
   `docs/reviews/PR-2.md`), then open PR #2.

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

## Handoff (2026-10-13, session limit reached)

Branch heads (all pushed):

| Branch | PR | State |
|---|---|---|
| `feat/scaffold-data` | #1 | done, reviewed |
| `feat/engine-core` | #2 | review received; code fixes pushed (`da329b2`); test and map fixes still to do |
| `feat/level01-objects` | #3 | built and tested; its independent review was cut off by the usage limit, so re-run it |
| `feat/game-app` | not opened | playable app works (`uv run abuse-remake`); needs `feat/engine-core` merged in |

To do next, in order:

1. **On `feat/engine-core`, finish the PR #2 review fixes** (findings are in the PR #2 review; record them in
   `docs/reviews/PR-2.md` the same way as `PR-1.md`):
   - Tests:
     - assert exact laser intervals: 3 ticks with ammo, 5 without;
     - assert `yvel == -15` on the jump tick;
     - pin `JRand(0)`'s first values to `[976, 25285, 23126, 7218, 62995]` (from the jrand.c LCG with seed "FUCK");
     - add tests for: `bottom_damage` scaling and its random order (random 2, then do_flinch's jrandom 2, then random 4); `give_player_health`; the `hurt_radius` falloff and push; grenade, firebomb and rocket (speed 5, 7, ... 15 for the player, 11 for others); the `add_ammo` cap of 999 and its switch to the most powerful weapon; `select_weapon` refusing a weapon with 0 ammo.
   - Map:
     - the rocket row should say max speed 15/11, not 14/10;
     - add line numbers for collide.c 147-222 (hity at 212), explo.lsp 24-35, jrand.c, lisp.c 1904-1931 / 2512-2518, options.lsp:36, abuse.lsp:40-42;
     - relabel rows that cite only our own tests as `code` (our tests test the port, not the original);
     - the view-size row is now `code`: 316x162 from `view.c:636-676`, `game.c:1423`, `video.c:333-334`; remove it from the open questions.
2. Merge `feat/engine-core` into `feat/level01-objects`, then into `feat/game-app`. Expect conflicts in `world.py`, where `bg_map` was renamed on both branches. Push each.
3. Re-run the independent review on PR #3 (same prompt as PR #2's), fix what it finds, and write `docs/reviews/PR-3.md`.
4. Open the PR for `feat/game-app` (milestone 4). Then milestone 5, the player interface: `agent/interface.py` with the five operations, the observation boundary, legal actions, JSON-lines player processes, budgets and traces.
