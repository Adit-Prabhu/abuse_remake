# Review record: PR #1 (scaffold, data, format readers)

- **Reviewer:** an independent read-only agent (Claude, `Explore` type, fresh context, no edit
  tools), briefed with `.claude/agents/rules-reviewer.md`. The implementation agent did not
  review its own change.
- **Input:** the change summary, the diff on `feat/scaffold-data`, and the original C source at
  `historicalsource/abuse@01cce80` for comparison.
- **Date:** 2026-10-13.

The student decides every finding. The table records what the implementation agent changed in
response; the student accepts or overrides it by merging, or by asking for more changes.

| # | Severity | Finding (summarised) | Resolution |
|---|---|---|---|
| 1 | blocking | `PROVENANCE.md` wrongly claimed the data is unmodified original data. The upstream `abuse.lsp` differs from the source release, the upstream copy carries 1996–2008 community edits, the README releases only the *code* to the public domain, and the README quote was altered | Researched the lineage. Downloaded the 1995 shareware v1.01 and the 1996 retail 2.00 releases and compared them (`scripts/compare_original_data.py`, `docs/data-lineage.md`). `level01.spe` and the palette are byte-identical to both. The Lisp matches retail 2.00 in 401 of 409 definitions, and no difference touches a Level 1 rule. Rewrote `PROVENANCE.md`: exact quotes, code (public domain) versus shareware data (use permission), and the community-edit lineage |
| 2 | should fix | `docs/rule-source-map.md` was referenced but missing; the 15 Hz wording and the tick limits had no source | Added the map with labelled rows for every reader rule. The 15 Hz rule is `code` (a cap) plus `assumed` (a fixed rate); the tick limits are course choices |
| 3 | should fix | `NEXT_LEVEL_TOP` and `AMBIENT_SOUND` were missing from the scope table, yet both draw from the shared random table | Added both. `scope.LEVEL01_TYPES` and `tests/test_scope.py` now hold `SCOPE.md` and the level file to the same set of types |
| 4 | should fix | The loader fix-ups were missing: clearing the seen bit, zeroing missing tiles, deleting bad objects | Implemented, with citations and a hand-built level test |
| 5 | should fix | The `items.c:87` citation was wrong | Corrected to `:100`, and the line where the two versions differ (`:42` versus `:125`) is cited |
| 6 | should fix | Tests would not catch regressions in signedness, area and light signs, diagonal and skip-next inside flags, tile redefinition, light links, links of 0 or less, or a mismatched type byte | Added: a hand-built level file test; a tile-redefinition test; level01 signed-field checks; a triangle hand trace; and a **differential test that compiles the original `items.c` boundary code verbatim** and compares all 998 shipped outlines plus 400 random polygons |
| 7 | note | Player links and link numbering | Implemented the rule that 0 resolves to NULL and is ignored; documented in the map |
| 8 | note | Python raised where C carries on | Missing `describe_states`/`type` now yields no objects; a type mismatch in the lvars stops lvar loading. Tested |
| 9 | note | Field narrowings | `min_light_level` is now u16, `tick_counter` u32, and `fg_raised` is bounds-checked |
| 10 | note | Tile-size comment | Fixed. The review also led to finding that background tiles are **60x30, not 64x64**; the reader now takes both sizes from tile 0, as `loader2.c:439-442` does |
| 11 | note | Entry points for modules that do not exist yet | Removed until their milestones land |
| 12 | note | Restart and save details | `SCOPE.md` now states them with citations |

Notes still open for later milestones: the engine must fall back to `stopped` when a state's
sequence is missing (`level.c:1157-1159`), and reset `cur_frame` when it is out of range
(`level.c:1228-1232`).
