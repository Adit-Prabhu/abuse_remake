---
name: port-classic-rule
description: "Use when porting, changing or removing a rule of the Abuse reconstruction (engine physics, an object's behaviour, the player, weapons, the level loader) or anything the playing agent observes or may do. Ties each change to the original source at its pinned commit, a rule-map row, a test written first, and a summary the independent reviewer can check."
---

# Port a classic rule with evidence

The engine (`src/abuse_remake/engine/`) owns the game state. A rule change touches three things
together: the engine code, its test and its row in `docs/rule-source-map.md`. If one changes
without the others, the reviewer has nothing to check against.

The originals are pinned:
- C engine: `historicalsource/abuse@01cce80`. Clone it into a scratch folder; it is not vendored.
- Lisp rules and data: `data/original/` (`Xenoveritas/abuse@9d1f66f`, provenance in
  `data/original/PROVENANCE.md`).

## Steps

1. **Find the source.** Locate the rule in the original and quote the lines with `file:line`:
   `abuse/src/objects.c:899` for C, `data/original/lisp/ant.lsp:398` for Lisp. If the rule is
   in neither, it is `assumed` or a course choice, and you say so.
2. **Find or add the map row.** Quote the row and its label. Use the strongest honest label:
   - `code`: you read it in the original source;
   - `manual`: the manual or release notes say so;
   - `observed`: you ran the original (data or compiled original code) and name the method.
     Tests of our own port are checks, never `observed`;
   - `assumed`: none of the above. List it under "Open questions".
   Remastered-only rules are labelled `remastered design`; harness choices `course choice`.
   Never promote a label without new evidence.
3. **Write the test first.** Use a short deterministic scenario: a seed, the inputs, the
   expected state. Include at least one refused, illegal or boundary case near the rule. Run
   it and confirm it fails for the reason you expect. A test that already passes proves
   nothing about the change.
4. **Port the rule with the original's arithmetic.**
   - C division truncates toward zero (`cmath.cdiv`, `cmod`), and `>>8` drops fractions.
   - `uchar`, `ushort` and `schar` values wrap.
   - Keep the original's update order and its random draws in the same order
     (`world.rng`). A reordered draw changes every later tick.
   - Lisp: arguments evaluate left to right; `+` and `-` truncate fixed values; Lisp
     `set_aistate` zeroes `aistate_time`; only `nil` deletes an object.
   - Rule changes for Remastered go behind `Game(remastered=True)`, never into Classic.
5. **Check the playing agent's boundary** (`src/abuse_remake/agent/`):
   - `observe` returns only what a player on screen could know;
   - `legal_actions` names nothing the observation has not shown;
   - a refused action changes nothing and is counted;
   - no new path to the World object, level files, the map, the random table or credentials.
   Add or adjust a test in `tests/test_player_interface.py` if the change moves any of these.
6. **Update the map row**: the rule, our `file` and function, the label and the cited source
   lines.
7. **Run the checks**: `uv run pytest` and `uv run ruff check src tests scripts`. If
   `ABUSE_REQUIRE_C_REFERENCE=1` differential tests apply, they must run, not skip. All must
   pass, or you stop and report the failure.
8. **Write the summary for the reviewer**, in this order:
   - the rule as it now reads, with its label and evidence (`file:line`);
   - the test that proves it, and that it failed before the change;
   - any boundary effect from step 5, or "none";
   - anything you assumed.
9. **Hand it to an independent review** with `.claude/agents/rules-reviewer.md`, in a fresh
   context that did not write the change. Record the findings and fixes in
   `docs/reviews/PR-n.md`.

## Do not

- make a rule and its test agree on something no source supports;
- cite our own tests as evidence about the original;
- give the playing agent file access, the World object, the map or evaluator data;
- mark your own work reviewed, merge, or push tags. The student does that.
