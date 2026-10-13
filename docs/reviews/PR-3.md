# Review record: PR #3 (Level 1 objects)

- **Reviewer:** an independent read-only agent (Claude, `Explore` type, fresh context, no edit
  tools), briefed with `.claude/agents/rules-reviewer.md`. The first run was cut off by a usage
  limit and was re-run in full.
- **Input:** the diff `feat/engine-core..feat/level01-objects`, `data/original/lisp`, and the
  original C (`ant.c`, `sensor.c`, `objects.c`, `clisp.c`, `lisp.c`).
- **Date:** 2026-10-13.

**Result:** no fidelity bugs in the rule logic. The reviewer compared the following against the
sources, checking random-draw order, short-circuits, state numbers and nil/T returns:

- `ant_ai`, `sensor_ai`, the gates, switches, dimmer and ambient sound, and the exit and console;
- the doors, the force field, the walls, TELE2, TP_DOOR and the platform;
- `bolder_ai` (including its `set_x`/`set_y` `let` quirk), `small_rock_ai`/`bounce_move`;
- `ant_damage`/`ant_ct`/`crack_ai`, the spray gun, the pickups, and `change_type`/`change_aitype`.

| # | Severity | Finding (summarised) | Resolution |
|---|---|---|---|
| 1 | should fix | Object rows labelled `observed` cited only our own tests | Relabelled as checks |
| 2 | should fix | No test calls `ant_ai`; the extra random draws (`switch_once`, `ff_ai`, ...) and many objects are untested; the determinism test cannot catch reordered draws | Added tests: the hanging ant's drop rule and its one draw per tick, `switch_once`'s debug-print draw, the force field's per-tick shift, doors following their signal, the turret cadence, and the crack spawning an ant |
| 3 | should fix | No test of `bounce_move`'s return value, which decides rock deletion | Test: a rock returns T in flight and nil on landing |
| 4 | should fix | The wall test had no refused case and no signalled case | Test: a linked wall ignores damage while its signal is off, and explodes when signalled |
| 5 | should fix | The SENSOR row cited the wrong lines | Corrected to `switch.lsp:142-157` |
| 6 | note | Gates used the raw `set_aistate`; the Lisp version zeroes `aistate_time` | Gates now use the Lisp semantics |
| 7 | note | `amb_sound_ct` used the raw `set_aitype` | Now uses `change_aitype`, as the Lisp does |
| 8 | note | The turret cadence and ant pounce rows were worded wrongly | Rewritten. The test shows gaps of 5 ticks, and 6 or 7 when the sweep turns |
| 9 | note | The door row claimed trap doors push the player | Corrected, citing `duong.lsp:156-172` |
| 10 | note | The drop-roll citation and several docstring line ranges were off | Corrected |
| 11 | note | `set_light_r2` drops `calc_range` | Drawing only; noted in the code |
| 12 | note (boundary) | Some engine events had a uid but no position, so an observation could not filter off-screen ones | Every visible-kind event now carries x and y; `observe()` filters by screen. Covered by the boundary tests on the interface branch |
