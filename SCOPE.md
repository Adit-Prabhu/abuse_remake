# Scope record: Abuse (Crack dot Com, 1996), Level 1

> **Owner:** the student (Executive Producer and Creative Director). This record writes down the
> scope chosen on 2026-10-13 ("Level 1 only"). **TODO (human):** confirm it matches what the
> instructor agreed in Session 2, and record any change here with its date.

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
   - This is a course choice, not a rule of the game. In single-player mode the original
     reloads the level from the start (health 100), or reloads the save made at the last
     `RESTART_POSITION` console (`people.lsp` `restart_player`).
   - A console saves when the player presses the action key at it and picks a save slot. Health
     is set to 100 for the save unless the difficulty is `extreme` (`restart_ai`).
   - The human game keeps this restart, using an in-memory snapshot as the save; agent episodes
     stop at death.
3. **Timeout.** The scenario's tick limit is reached: 9000 ticks (10 minutes of game time) for
   the full level, or 2700 ticks for segments that start at a restart console. Both limits are
   course choices.

## Out of scope

Other levels (except Remastered's campaign below), network play, the level editor, save files on
disk, a Lisp interpreter (rules are
hand-ported and each one is cited in `docs/rule-source-map.md`), the retail data, the original
sounds and music (copyrighted), and the later add-on content in the Lisp (plasma gun, light
saber, extra powers, boss).

## Optional layer: Remastered mode

Both modes have the 60 fps drawing interpolated between ticks, the menus, mouse aiming and
gamepad support. Remastered adds the wider view, flash lighting, particles, the dash, the stats
screen, the ghost race and the Horde arena (`docs/remastered.md`). The AI spectator
(`abuse-replay`) always shows Classic rules.

- Classic mode shows the original 316x162 view; the wider view, particles, ghost and the other
  presentation features belong to Remastered mode (`docs/remastered.md`). Both modes draw the
  level's own lights; the muzzle-flash and explosion light is Remastered only. (Updated
  2026-10-13 to match the build.)
- Features that change rules exist only behind `--mode remastered`.
- Fidelity tests and agent evaluations always run in Classic mode.

### Remastered campaign (2026-10-14)

> **Drafted by the implementation agent on 2026-10-14 from the student's choices. TODO
> (student):** confirm or edit this paragraph; it records a scope change.

The student chose to extend Remastered mode, not Classic. The extension covers:
- the shareware training level and Level 2, played with Level 1 as a campaign;
- the four original power-ups (speed, flight, invisibility, ultra health);
- a larger Horde.

The extra levels come from the shareware v1.01 release (`data/original/PROVENANCE.md`). Their
objects are hand-ported from the same Lisp and C sources as Level 1's. Each object gets a row in
`docs/rule-source-map.md` and the independent review. The fidelity claim and the agent evaluations
stay on Classic Level 1, and `tests/test_classic_golden.py` pins Classic's behaviour.
