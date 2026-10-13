# Progress and handoff notes

This page lets a fresh session (human or agent) pick up the build. Update it with every push.
The approved plan is summarised in the "Milestones" table below; `SCOPE.md` is the scope
record.

## Branches and PRs (stacked; the student merges in order, agents never merge)

| Milestone | Branch | PR | State |
|---|---|---|---|
| 1. Scaffold, data, format readers | `feat/scaffold-data` | #1 | review done (`docs/reviews/PR-1.md`), CI green, awaiting merge |
| 2. Engine core | `feat/engine-core` (on top of #1) | #2 | done; independent review running |
| 3. Every Level 1 object | `feat/level01-objects` (on top of #2) | #3 | done: all 44 types ported, strict load passes, tests green |
| 4. Playable game (pygame, modern rendering) | `feat/game-app` | | not started |
| 5. Player interface (observe, legal actions, step, outcome) | `feat/player-interface` | | not started |
| 6. Baselines and evaluation | `feat/baselines-eval` | | not started |
| 7. Model player (Vertex, Anthropic, OpenAI) | `feat/model-player` | | not started |
| 8. Remastered mode | `feat/remastered` | | not started |
| 9. Evidence, docs, release | `docs/evidence` | | not started |

## Current state (milestones 2 and 3)

The full Level 1 runs in strict mode: every in-scope Lisp or C behaviour has a Python port.
600 ticks take about 0.08 s headless. Key modules:

- `engine/` (pure Python): `cmath`, `tables`, `geometry`, `chardefs`, `obj`, `world`, `view`,
  `game`.
- `engine/behaviors/`:
  - `player.py`: cop.c and people.lsp;
  - `weapons.py`: guns.lsp, weapons.lsp, explo.lsp, debris;
  - `logic.py`: gates, switches, sensors, dimmers, ambient sound, exit, consoles;
  - `world_objects.py`: doors, force field, walls, teleporters, platforms, boulder;
  - `enemies.py`: ants (ant.c), the crack, the spray gun, pickups.
- Tests:
  - `tests/test_engine_core.py`: includes the differential test against compiled
    `intsect.c`;
  - `tests/test_level01_objects.py`.

Next: milestone 4, the playable pygame app (`src/abuse_remake/game/`). Plan:

- render with the original palette and sprites, at a 311x151 logical view scaled up;
- 60 fps interpolation between 15 Hz ticks; lighting from the level lights and the view's
  ambient level; particles for the `panim`/explosion events;
- HUD: health, weapons and ammo;
- input: keyboard and mouse, mapped to `Inputs`;
- a restart from the in-memory save on death (set `world.globals["save_hook"]` to snapshot);
- `--record` writes human traces;
- CC0 audio mapped from the sound event names.

Then milestone 5, the player interface (`agent/`).

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
