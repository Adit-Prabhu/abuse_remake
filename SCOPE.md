# Scope record: Abuse (Crack dot Com, 1996), Level 1

> **Owner:** the student (Executive Producer and Creative Director). Level 1 was chosen on
> 2026-10-13. This page was last revised on 2026-10-26, and changes are dated at the bottom.

**In one sentence:** the graded game is **Classic mode, Level 1**: a faithful, deterministic port
of the original rules on the original level file, played by people and by agents through the
same rules. Remastered mode is an optional layer on top. It is not graded and never evaluated.

## The classic

Abuse, the 1996 MS-DOS side-scrolling run-and-gun by Crack dot Com. You run and jump through an
alien-infested prison and aim 360° with the mouse, independently of your movement. Provenance
and licence terms for the code and data are in `data/original/PROVENANCE.md`. The evidence that
our data matches the original releases is in `docs/data-lineage.md`.

## The bounded reconstruction

**Level 1 (`levels/level01.spe`)**, the first combat level, loaded straight from the original
file. The file is byte-identical to the 1995 shareware and 1996 retail releases.

The original caps game logic at 15 frames per second (`game.c:1630-1633` delays any frame that
would run faster). Its release note calls these "the 15 Hz updates". The reconstruction runs
exactly one logic tick per original frame, at a fixed 15 Hz. Rendering is interpolated in
between.

Every object type in the file is in scope. `src/abuse_remake/scope.py` lists them, and a test
checks that list against the level file and against this page.

| Area | Object types and rules | Rule source |
|---|---|---|
| Map | foreground and background tile maps; tile collision outlines; background scroll rate | `level.c`, `items.c`, art `.spe` files |
| Player | `START` spawns DARNEL. In scope: run, jump, stop and turn physics; aiming the top half in 360°; health 100; flinch; death | `objects.c` `tick`/`mover`, `cop.c`, `people.lsp` |
| Weapons | laser rifle (`MBULLET`), grenade launcher, firebomb (napalm), rocket launcher; ammo | `cop.c`, `weapons.lsp`, `guns.lsp` |
| Enemies and hazards | `ANT_ROOF`, `HIDDEN_ANT`, `ANT_CRACK` (alien ants), `SPRAY_GUN` (turret), `BOLDER` (boulder) | `ant.c`, `ant.lsp`, `guns.lsp`, `duong.lsp` |
| Pickups | `HEALTH`, `MBULLET_ICON5`, `MBULLET_ICON20`, `GRENADE_ICON2`, `GRENADE_ICON10`, `FBOMB_ICON1`, `ROCKET_ICON2` | `powerup.lsp`, `weapons.lsp` |
| Logic | `SENSOR`, `DEATH_SENSOR`, `GATE_AND`, `GATE_XOR`, `GATE_NOT`, `GATE_DELAY`, `GATE_PULSE`, `SWITCH`, `SWITCH_ONCE`, `SWITCH_MOVER`, `SWITCH_DIMMER` | `switch.lsp`, `gates.lsp`, `light.lsp` |
| World objects | `SWITCH_DOOR`, `FORCE_FIELD`, `TRAP_DOOR2`, `TRAP_DOOR3`, `SMART_PLAT_SMALL`, `TP_DOOR`, `TELE2`, `TELE_BEAM`, `HIDDEN_WALL1`, `HIDDEN_WALL2`, `HIDDEN_WALL3`, `HIDDEN_WALL4`, `HIDDEN_WALL5`, `HIDDEN_WALL_2x2`, `HIDDEN_WALL_3WAL`, `HIDDEN_WALL_3FLR` | `doors.lsp`, `duong.lsp`, `platform.lsp`, `teleport.lsp`, `people.lsp` |
| Progress | `RESTART_POSITION` (save console), `NEXT_LEVEL` and `NEXT_LEVEL_TOP` (the exit) | `people.lsp` |
| Sound emitters | `AMBIENT_SOUND`. It plays a sound, but it also draws from the shared random table, as `NEXT_LEVEL_TOP` does. Leaving either out would change every enemy's random choices | `sfx.lsp` |
| Presentation | camera follow and per-area offsets; lighting from the level's light list and ambient level | `view.c`, `light.c` |
| Difficulty | `easy`, `medium`, `hard`, `extreme` damage and health scaling | `people.lsp` `bottom_damage`, `give_player_health` |

## Ending and episode limit

An episode ends at the first of:

1. **Win.** The player stands at `NEXT_LEVEL` and presses the action key, which is down
   (`people.lsp` `next_level_ai`: `touching_bg` and `pressing_action_key`, where
   `pressing_action_key` is `(> (player_y_suggest) 0)`).
2. **Loss.** The player dies.
   - This is a `design` choice (harness), not a rule of the game. In single-player mode the original
     reloads the level from the start (health 100), or reloads the save made at the last
     `RESTART_POSITION` console (`people.lsp` `restart_player`).
   - A console saves when the player presses the action key at it and picks a save slot. Health
     is set to 100 for the save unless the difficulty is `extreme` (`restart_ai`).
   - The human game keeps this restart, using an in-memory snapshot as the save; agent episodes
     stop at death.
3. **Timeout.** The scenario's tick limit is reached: 9000 ticks (10 minutes of game time) for
   the full level, or 2700 ticks for segments that start at a restart console. Both limits are
   `design` choices (harness).
4. **Agent budgets.** For agents only: the decision budget (200 per segment, 600 for the full
   level in the declared suite), token and wall-clock budgets, and a player that fails. Each
   ending is reported under its own name (`docs/budgets.md`).

A human plays the same rules with the original restart at the last console. Agent episodes are
the bounded version of the same level. The episode interface is specified in
`docs/action-interface.md`, what a player may know in `docs/information-boundary.md`, and the
declared evaluation in `SUITE.md`.

## Optional layer: Remastered mode (not graded, not evaluated)

`--mode remastered`, the default in the title menu, adds features that change rules. Each of
those rules lives behind the mode and is labelled `design` (Remastered) in
`docs/rule-source-map.md`, or `code` where it ports an original object. Classic mode, the
fidelity tests and every agent evaluation run without them. `tests/test_classic_golden.py` pins
Classic's behaviour, and `test_classic_games_and_agent_episodes_never_build_remastered_rules`
checks the separation.

- **Feel:** the wider view, flash lighting, particles, the dash, quick restart, the stats
  screen and the ghost race (`docs/remastered.md`).
- **Campaign (added 2026-10-14):** the shareware training level, then Level 1, then Level 2. The
  two extra levels are the byte-identical shareware v1.01 files
  (`data/original/PROVENANCE.md`). Their objects are hand-ported from the same Lisp and C as
  Level 1's, with map rows and independent reviews (PRs #15-#17). It also has the original four
  power-ups (speed, flight, invisibility, ultra health).
- **Horde:** waves on three sealed arenas, with mixed enemies, a boss every fifth wave, upgrade
  cards, score and high scores (PRs #18 and #20).
- **Interface:** a title menu, a controls screen, the HUD in the original interface art, a
  gamepad, a resizable window and full screen.

**Every level in the build can be finished, with evidence.** Each has a saved input route that
CI replays to the level's exit (`evidence/routes/`, `tests/test_campaign_routes.py`): the
training level and Level 2 under Remastered rules, and Level 1 under Classic rules.

Both modes draw the level's own lights and interpolate 60 fps rendering between the 15 Hz ticks.
The AI spectator (`abuse-replay`) always shows Classic rules.

## Out of scope

- Levels other than Level 1, except the training level and Level 2 in Remastered's campaign.
- Network play, the level editor, save files on disk, and a Lisp interpreter (rules are
  hand-ported, and each is cited in `docs/rule-source-map.md`).
- The retail data, and the original sounds and music (copyrighted; the game synthesises its own).
- The later add-on content in the Lisp: the plasma gun, light saber, extra powers beyond the
  original four, and the boss.
- **Not part of this submission:**
  - *Neon Protocol*, a separate original-game experiment (PRs #9-#14);
  - the developer-assisted interactive bridge (`feat/codex-bridge`). It let a coding assistant
    with repository access choose moves, so it can't meet the player boundary, and it is used
    for nothing reported.

## Changes to this scope

| Date | Change | Decided by |
|---|---|---|
| 2026-10-13 | Abuse, Level 1 only; a Classic core plus a Remastered mode; Vertex AI for the live player | the student |
| 2026-10-14 | Remastered grows: the training level, Level 2, the four power-ups, a bigger Horde. Classic and the evaluation unchanged | the student, against the agent's advice to finish the required items first |
| 2026-10-26 | The graded scope restated as Classic Level 1, with Remastered optional and ungraded. Neon and the bridge excluded. The evaluation suite re-declared before any live call (`SUITE.md`) | the student, after the midterm audit (`docs/reviews/midterm-audit-2026-10-26.md`) |
