# Scope record: Abuse (Crack dot Com, 1996), Level 1

> **Owner:** the student (Executive Producer and Creative Director). This record writes down the
> scope chosen on 2026-10-13 ("Level 1 only"). **TODO (human):** confirm it matches what the
> instructor agreed in Session 2, and record any change here with its date.

## The classic

Abuse, the 1996 MS-DOS side-scrolling run-and-gun by Crack dot Com. You run and jump through an
alien-infested prison and aim 360° with the mouse, independently of your movement. The source code
and the shareware data are public domain (see `data/original/PROVENANCE.md`).

## The bounded reconstruction

**Level 1 (`levels/level01.spe`)**, the first combat level, loaded straight from the original
file. The game logic runs at the original fixed rate of 15 ticks per second.

| Area | What is in scope | Rule source |
|---|---|---|
| Map | foreground and background tile maps; tile collision outlines; background scroll rate | `level.c`, `items.c`, art `.spe` files |
| Player (DARNEL) | run, jump, stop and turn physics; the top half aiming in 360°; health 100; flinch; death | `objects.c` `tick`/`mover`, `cop.c`, `people.lsp` |
| Weapons | laser rifle (`MBULLET`), grenade launcher, firebomb (napalm), rocket launcher; ammo and pickups | `cop.c`, `weapons.lsp` |
| Enemies | `ANT_ROOF`, `HIDDEN_ANT`, `ANT_CRACK` (alien ants), `SPRAY_GUN` (turret), `BOLDER` (boulder) | `ant.c`, `ant.lsp`, `guns.lsp`, `duong.lsp` |
| Pickups | `HEALTH`, ammo icons (`MBULLET_ICON5/20`, `GRENADE_ICON2/10`, `FBOMB_ICON1`, `ROCKET_ICON2`) | `powerup.lsp`, `weapons.lsp` |
| Logic | `SENSOR`, `DEATH_SENSOR`, `GATE_AND/XOR/NOT/DELAY/PULSE`, `SWITCH`, `SWITCH_ONCE`, `SWITCH_MOVER`, `SWITCH_DIMMER` | `switch.lsp`, `gates.lsp`, `light.lsp` |
| World objects | `SWITCH_DOOR`, `FORCE_FIELD`, `TRAP_DOOR2/3`, `HIDDEN_WALL*`, `SMART_PLAT_SMALL`, `TP_DOOR`, `TELE2`, `TELE_BEAM`, `RESTART_POSITION`, `START`, `NEXT_LEVEL` | `doors.lsp`, `duong.lsp`, `platform.lsp`, `teleport.lsp`, `people.lsp` |
| Presentation | camera follow and per-area offsets, lighting from the level's light list and ambient level | `view.c`, `light.c` |
| Difficulty | `easy`, `medium`, `hard`, `extreme` health scaling | `people.lsp` `give_player_health` |

## Ending and episode limit

An episode ends at the first of:

1. The player stands at `NEXT_LEVEL` and presses the action key. **Win.** (`people.lsp`
   `next_level_ai`: `touching_bg` and `pressing_action_key`.)
2. The player dies. **Loss.** This is a course choice, not a rule of the game. In single-player
   mode the original reloads the level from the start, or reloads the save made at the last
   `RESTART_POSITION` console the player activated (`people.lsp` `restart_player`,
   `restart_ai`). The human game keeps that restart, using an in-memory snapshot as the save;
   agent episodes stop.
3. The tick limit for the scenario is reached. **Timeout.** Defaults: 9000 ticks (10 minutes of
   game time) for the full level, and 2700 ticks for checkpoint segments.

## Out of scope

Other levels, network play, the level editor, save games, a Lisp interpreter (rules are
hand-ported and each one is cited in `docs/rule-source-map.md`), the retail data, the original
sounds and music (copyrighted), and the `frabs` add-ons.

## Optional layer: Remastered mode

The modern features (60 fps interpolation, dynamic lighting, particles, menus, gamepad support,
dash, stats, ghost race, AI spectator, Horde arena) are listed in `README.md`.

- Purely visual features apply in both modes.
- Features that change rules exist only behind `--mode remastered`.
- Fidelity tests and agent evaluations always run in Classic mode.
