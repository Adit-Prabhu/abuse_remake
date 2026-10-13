# Rule and source map

Every rule the reconstruction enforces, where our code implements it, and the evidence for it.

## Evidence labels

The labels follow the course convention:

| Label | Meaning |
|---|---|
| `code` | Read from the original C engine (`historicalsource/abuse@01cce80`, cited as `abuse/src/file.c:line`) or the original Lisp (`data/original/lisp/file.lsp:line`). |
| `manual` | Stated in the original manual or release notes. |
| `observed` | Seen by running the original (data or compiled original code); the method is named. Tests of our own port are cited as checks, not as evidence. |
| `assumed` | Not yet backed by evidence. Each one is listed under "Open questions". |
| course choice | Not a rule of the game: a decision about the evaluation harness or episode, made for the course and labelled so it is never mistaken for fidelity. |
| course rule | A requirement the course sets (for example, no automatic paid retries). |
| remastered design | A new rule that exists only in Remastered mode. It is not a claim about the original. |

For the Lisp's relation to the 1996 retail release, see `docs/data-lineage.md`.

This map grows with each milestone. Rows for the engine, objects and player interface are added
by the PRs that implement them.

## Timing and episode

| Rule | Our code | Evidence |
|---|---|---|
| Game logic runs at most 15 frames per second; faster frames are delayed | `scope.TICKS_PER_SECOND` | `code`: `abuse/src/game.c:1630-1633` (`calc_speed`). Corroborated by `manual`: the release note's "the 15 Hz (i believe) updates" (historicalsource `README`). |
| One engine tick per original frame, at a fixed 15 Hz, with rendering interpolated in between | `scope.TICKS_PER_SECOND` | `assumed`: the original slows down on hardware that cannot reach 15 fps; we model the full-speed case |
| The play view is 316x162 (x 2..317, y 5..166 on the 320x200 screen); it sets the camera and, with a quarter of its size added on each side, which objects run each tick | `engine/view.py` `VIEW_W`, `VIEW_H` | `code`: `abuse/src/view.c:636-676` (`recalc_local_view_space`), called at start-up from `abuse/src/game.c:1423`, with `xres=319`, `yres=199` from `imlib/port/dos4gw/video.c:333-334` |
| Episode limits: 9000 ticks for the full level, 2700 for checkpoint segments | `scope.FULL_LEVEL_TICK_LIMIT`, `scope.SEGMENT_TICK_LIMIT` | course choice, not a rule of the game |
| Every object type in `level01.spe` is in scope | `scope.LEVEL01_TYPES` | `observed`: `tests/test_scope.py` reads the level file |

## Data formats

| Rule | Our code | Evidence |
|---|---|---|
| SPEC1.0 container: signature, u16 count, then per entry type, name, flags, size, offset | `formats/spec.py` `SpecFile` | `code`: `imlib/specs.c:739-789`, `imlib/include/specs.hpp` (layout comment) |
| `find` returns the first entry with a matching name | `SpecFile.find` | `code`: `imlib/specs.c:680-688` |
| Image: u16 width, u16 height, then palette indices; index 0 is transparent in sprites | `formats/images.py` `Image` | `code`: `imlib/image.c:132`; `trans_image` |
| Point list: u8 count, then (x, y) byte pairs | `PointList` | `code`: `abuse/src/points.c:17` |
| Boundary "inside" flags; the flipped copy checks vertical segments to the right | `images._inside_flags` | `code`: `abuse/src/items.c:8-98` and `:100-183`; the difference is at `items.c:42` versus `:125` |
| Character frame: image, hit damage, `xcfg`, signed advance, damage boundary, hit list | `Figure.read` | `code`: `abuse/src/items.c:270-292`, `abuse/inc/items.hpp:51-58` |
| Palette: u16 count, then RGB byte triples (8 bits per channel) | `tiles.Palette` | `code`: `imlib/palette.c:22-31`; `observed`: values above 63 in `backgrnd.spe` |
| A tile's number is its entry name; a later file redefines an earlier number | `tiles.load_tiles` | `code`: `abuse/src/loader2.c:157-264` |
| Tile file order | `tiles.TILE_FILES` | `code`: `data/original/lisp/startup.lsp:36-54` |
| Tile grid is the size of tile 0: foreground 30x15, background 60x30 | `TileSet.grid_sizes` | `code`: `abuse/src/loader2.c:439-442`; `observed`: `tests/test_formats.py` |
| Foretile: image, u16 next, u8 damage (unused), boundary | `tiles.load_tiles` | `code`: `abuse/src/items.c:197-257` |
| Level maps: u32 width, u32 height, u16 cells; the foreground value is `cell & 0x3FFF` | `level_file._read_map`, `fg_tile` | `code`: `abuse/src/level.c:1303-1335`, `abuse/inc/level.hpp:22-24` |
| With no `player_info`, the 0x8000 seen bit is cleared; cells naming missing tiles become 0 | `load_level` | `code`: `abuse/src/level.c:1357-1374` |
| Objects: per-type names, states and local variables; then one array per base variable | `level_file._load_objects` | `code`: `abuse/src/level.c:1005-1240`, `abuse/src/objects.c:47-82` |
| `direction`, `active`, `fade_dir` and `frame_dir` are signed chars; `cur_frame` is a short | `SIGNED_CHAR_VARS`, `SIGNED_SHORT_VARS` | `code`: `abuse/inc/extend.hpp` (`simple_object`) |
| An lvar whose type byte is not `RC_L` stops lvar loading | `_load_objects` | `code`: `abuse/src/level.c:1166-1190` |
| Objects with an unknown type or negative x or y are deleted after loading | `LevelObject.removed_on_load` | `code`: `abuse/src/level.c:1393-1399` |
| Links: 1-based object numbers. A target of 0 or less is a player; 0 resolves to NULL and is ignored | `level_file._load_links` | `code`: `abuse/src/level.c:2001-2050`, `abuse/src/objects.c:1503-1510`, `abuse/src/extend.c:49-57` |
| Areas: x, y, w, h, active, ambient, view offsets and speeds (signed) | `AreaController` | `code`: `abuse/src/level.c:2085-2144` |
| Lights: count, minimum light level, then x, y, shifts, radii and a type byte | `level_file.Light` | `code`: `abuse/src/light.c:1243-1272` |


## Engine core: arithmetic, collision and physics

| Rule | Our code | Evidence |
|---|---|---|
| Integer division and remainder truncate toward zero, as in C | `engine/cmath.py` `cdiv`, `cmod` | `code`: the C semantics the engine is written in |
| Fixed-point trig: `sin_table` of 360 entries ×65536; cosine indexes 90 ahead; negative angles index from the end | `cmath.lisp_sin`, `lisp_cos`, `engine/tables.py` | `code`: `abuse/src/trig.c`, `abuse/src/lisp.c:676-688` |
| `atan2` uses a 1662-entry table and returns 260 (not 270) for steep down-right angles | `cmath.lisp_atan2` | `code`: `abuse/src/lisp.c:690-775` (the port is checked in `tests/test_engine_core.py`) |
| Randomness: a fixed 1024-entry table from seed "FUCK"; only the start index (`rand_on`) varies. We set it from the episode seed; the original uses `time() % 1024` | `cmath.JRand` | `code`: `imlib/jrand.c:8-21`, `imlib/include/jrand.hpp`; the first entries are pinned in a test; seeding is a course choice |
| Lisp `+` and `-` truncate fixed-point values to integers; `*` multiplies in fixed point when its first argument is fixed; `/` is integer only; `mod` is C `%` | `behaviors/lispfns.py` | `code`: `abuse/src/lisp.c:1893-1903` (+), `:1955-1964` (-), `:1904-1931` (*), `:1932-1954` (/), `:2512-2518` (mod). The integer `*` evaluates each argument twice and multiplies the second values, so `(* dir (random 10))` draws two random numbers |
| A move is cut short one pixel before it crosses a boundary segment; the `inside` flag picks the blocking side | `geometry.setback_intersect` | `code`: `abuse/src/intsect.c:139-233`; `observed`: a differential test against the compiled original, 20,000 cases |
| Tile collision checks the tiles around the move, with tile-edge points pushed 1 px outward | `TileMap.foreground_intersect` | `code`: `abuse/src/level.c:2584-2665` |
| Our bounding-box prefilter never changes a result (a property of our code, not a rule) | `TileMap.foreground_intersect` | check: `tests/test_engine_core.py` compares against the unfiltered reference |
| Character data (states, frames, abilities, flags, ranges, variables) comes from the original `def_char` forms and the helpers that generate them | `engine/chardefs.py` | `code`: `abuse/src/chars.c:272-420` and the cited Lisp lines |
| Gravity adds 200/256 to the vertical acceleration each tick, so it builds up over time | `obj.GameObject.tick` | `code`: `abuse/src/objects.c:910-920` |
| Collision response: land, hit a ceiling or wall, step up slopes, descend small drops | `obj.GameObject.tick` | `code`: `abuse/src/objects.c:936-1095` |
| Walking and running: right sets `xvel` to `run_top_speed` at once; left only sets `xacel` (the original's asymmetry) | `obj.GameObject.mover` | `code`: `abuse/src/objects.c:1256-1273` (port checked by `test_running_right_reaches_top_speed_at_once_but_left_accelerates`) |
| Stopping: with no key held, `stop_accel` slows the player; if it is at least the speed, the player stops and turns `stopped` | `mover` | `code`: `abuse/src/objects.c:1294-1323` |
| Jump: `yvel = jump_yvel`; horizontal speed becomes `jump_top_speed` if moving | `mover` | `code`: `abuse/src/objects.c:1341-1352` |
| Speed limits per state: walk, run and jump top speeds; no horizontal drift in the air without a key | `mover` | `code`: `abuse/src/objects.c:1401-1419` |
| Ballistic movement for projectiles; the fractional velocity is added unsigned | `obj.bmove` | `code`: `abuse/src/objects.c:1441-1487` |
| DARNEL: start_hp 100, walk 3, run 9, jump_yvel −15, jump_top 10, jump_xvel 9, start_accel 8, stop_accel 9, push range 9 | `chardefs` (from the Lisp) | `code`: `data/original/lisp/people.lsp:566-611` |
| Only objects inside the view plus a quarter of its size (and each object's `range`) run each tick; objects linked to an active object run right after it | `World.activate_for_views`, `add_actives` | `code`: `abuse/src/game.c:1983-1998`, `abuse/src/level.c:176-242` |
| Per tick: the player moves from its inputs; every other active object runs its AI and is deleted if the AI returns nil; then attack frames are checked against hurtable targets | `World.step`, `check_collisions` | `code`: `abuse/src/level.c:596-760`, `abuse/src/collide.c:147-222`, `abuse/src/objects.c:418` (only nil deletes) |
| Hit position uses `y1+y1` (a typo in the original) | `World.check_collisions` | `code`: `abuse/src/collide.c:212` |
| Explosions hurt within radius `r`, falling off with an octagonal distance, and push targets | `World.hurt_radius` | `code`: `abuse/src/level.c:2979-3019` |
| `push_characters` leaves `tvy` uninitialised when the push is upward; we use 0 | `World.push_characters` | `code`: `abuse/src/level.c:2840-2867`; **deviation**: undefined behaviour in the original |
| The default difficulty is `hard`; `max_hp` is 200 | `world.DEFAULT_DIFFICULTY`, `MAX_HP` | `code`: `abuse/hardness.lsp`, `data/original/lisp/startup.lsp:19-20`, `abuse/src/clisp.c:137-138` |

## Player and weapons

| Rule | Our code | Evidence |
|---|---|---|
| The player spawns at START with defaults: ambient 35, aistate 0, no power | `engine/game.py`, `behaviors/player.set_player_defaults` | `code`: `abuse/src/level.c:1814-1830`, `data/original/lisp/people.lsp:101-115`, `level.c:3068-3088` |
| The top half (gun) is created on the first tick and linked both ways; its type follows the current weapon | `player.cop_mover`, `top_ai` | `code`: `abuse/src/cop.c:613-618`, `:183` |
| Aiming picks the gun frame (of 24) closest to the pointer angle; the RNG index advances by the aim angle each tick | `player.top_ai` | `code`: `abuse/src/cop.c:125-188` |
| Shots leave from the gun tip, cut short by walls and blocking objects | `player.player_fire_weapon` | `code`: `abuse/src/cop.c:191-234` |
| Laser: every 3 ticks using 1 ammo, or every 5 ticks with no ammo (it never runs dry) | `player.laser_ufun` | `code`: `abuse/src/cop.c:238-265` (exact intervals checked in tests) |
| Grenade and firebomb: every 6 ticks, need ammo | `player.top_ufun` | `code`: `abuse/src/cop.c:280-303` |
| Rocket: every 6 ticks; locks onto the nearest targetable bad guy within 160x130 | `player.player_rocket_ufun` | `code`: `abuse/src/cop.c:358-404`; bad guy list: `data/original/abuse.lsp:40-42` |
| Weapon slots: laser 0, grenade 1, rocket 2, firebomb 3; the first is owned with 0 ammo; ammo is capped at 999; an empty weapon switches to the most powerful one, skipping slot 3 | `engine/view.py` | `code`: `abuse/src/view.c:40-96, 189-262`; `data/original/lisp/options.lsp:14, 36` (`change_on_pickup`, `switch_to_powerful`) |
| Damage to the player is scaled by difficulty (easy ½, medium ¾, hard ×1, extreme ×3), with a random flinch and debris on death | `player.bottom_damage` | `code`: `data/original/lisp/people.lsp:328-370` |
| Health pickups are scaled by difficulty (hard gives half) up to 100 | `player.give_player_health` | `code`: `data/original/lisp/people.lsp:49-66` |
| Laser bolt: speed ×6/5 per tick, 6-tick life, 5 damage, explodes on walls | `weapons.sgun_ai`, `fire_object` | `code`: `abuse/src/cop.c:888-928`, `data/original/lisp/guns.lsp:34-193` |
| Grenade: thrown at speed 20 plus the thrower's velocity; explodes on contact or near a bad guy (radius 40, 36 damage) | `weapons.grenade_ai`, `do_explo` | `code`: `data/original/lisp/weapons.lsp:28-39`, `explo.lsp:25-36` |
| Firebomb: burns for up to 20 ticks (radius 60, 40 damage) | `weapons.firebomb_ai` | `code`: `data/original/lisp/weapons.lsp:43-55` |
| Rocket: speed starts at 5 and rises by 2 while below `max_speed` (14 for the player, else 10), so it tops out at 15 or 11; turns up to 23° per tick toward its target, has 4 HP, explodes (radius 40, 50 damage) | `weapons.rocket_ai` | `code`: `data/original/lisp/weapons.lsp:356-425`, `guns.lsp:83-101` |
| Smoke and debris restore the random table, so they never change gameplay randomness | `rocket_ai`, `create_dead_parts` | `code`: `weapons.lsp:357-362`, `ant.lsp:348-378` |
| `frame_panic` is false (single player, full speed) | `weapons.FRAME_PANIC` | `code`: `abuse/src/clisp.c:1971-1977` |
| Which of two C function arguments with `jrand()` is evaluated first is unspecified; we take left to right | `weapons.sgun_ai` | `assumed`: it changes only where an explosion sprite appears (±3 px) |


## Level 1 objects

Each object's AI is in `src/abuse_remake/engine/behaviors/`. An object's `aistate` is its
output signal, and `activated` reads the first linked object's signal (`abuse/src/clisp.c`
l_caller case 39).

| Rule | Our code | Evidence |
|---|---|---|
| AND, XOR, NOT, DELAY and PULSE gates | `logic.and_ai`, `xor_ai`, `not_ai`, `delay_ai`, `pulse_ai` | `code`: `data/original/lisp/gates.lsp:4-162` (check: `test_and_and_xor_gates_follow_their_truth_tables`, `test_not_gate_inverts_its_first_link`, `test_delay_gate_copies_input_after_delay_time_ticks`; PULSE has no test yet) |
| SENSOR turns on inside its (xvel, yvel) box and off outside its (xacel, yacel) box, or after `hp` ticks; `unoffable` sensors stay on | `logic.sensor_ai` | `code`: `abuse/src/sensor.c` (compiled C; the Lisp version at `switch.lsp:142-157` is commented out) |
| A new SENSOR gets `aitype` 1, which sets its boxes to 50x50 (on) and 100x100 (off) | `logic.sensor_cons`, `sensor_ct` | `code`: `switch.lsp:137-140, 186-198`; `abuse/src/objects.c:1564-1592` (`change_aitype` runs the type-change function) |
| SWITCH toggles when the player is within 20x30 and presses the action key; the key must be released before it can toggle again | `logic.switcher_ai` | `code`: `switch.lsp:4-26` (check: `test_switch_toggles_with_the_action_key_and_needs_a_release` )|
| SWITCH_ONCE draws a random number, from a leftover debug `(print (random 1000))` | `logic.switch_once_ai` | `code`: `switch.lsp:29-39` |
| Switches, switch doors, consoles and TP_DOORs move to the front of the object list on load (`lower`) | `logic.lower_reload` | `code`: `switch.lsp:41`, `clisp.c` case 240, `level.c:2548` |
| DEATH_SENSOR turns on when its linked object dies | `logic.death_sen_ai` | `code`: `switch.lsp:284-291` |
| SWITCH_DIMMER fades the light or ambient level when signalled | `logic.switch_dim_ai` | `code`: `data/original/lisp/light.lsp:4-62, 82-90` |
| AMBIENT_SOUND repeats a sound every `xvel + random(xacel+1)` ticks while activated, drawing from the random table | `logic.amb_sound_ai` | `code`: `sfx.lsp:230-244` |
| Exit: touching NEXT_LEVEL and pressing the action key ends the level | `logic.next_level_ai` | `code`: `people.lsp:915-923` (check: `test_exit_needs_touch_and_action_key` )|
| NEXT_LEVEL_TOP shifts the random table by 80 every tick it is active | `logic.next_level_top_ai` | `code`: `people.lsp:932-937` (check: `test_next_level_top_shifts_the_random_table_by_80_each_tick`) |
| A RESTART_POSITION console saves when touched with the action key; health is 100 in the save unless the difficulty is extreme | `logic.restart_ai` | `code`: `people.lsp:873-904`. **Deviation:** the original's save-slot dialog is replaced by one in-memory slot |
| SWITCH_DOOR and TRAP_DOOR open while signalled and close when not; only SWITCH_DOOR pushes the player out while closed (`sdoor_ai` passes T, `strap_door_ai` passes nil) | `world_objects.general_sdoor_ai`, `push_char` | `code`: `doors.lsp:29-62`, `duong.lsp:156-172`, `common.lsp:15-23` |
| FORCE_FIELD pushes the player back 35 px while activated, and draws a random number every tick | `world_objects.ff_ai` | `code`: `doors.lsp:79-108` |
| Hidden walls take damage only while activated, show cracks in proportion to damage, and explode (radius 50, 60 damage; big walls 110, 120) at 0 HP or when signalled | `world_objects.hwall_ai`, `big_wall_ai`, `hwall_damage` | `code`: `doors.lsp:130-166` (check: `test_hidden_wall_cracks_then_breaks_when_its_saved_hp_runs_out`, `test_linked_wall_ignores_damage_until_its_signal_then_explodes`) |
| TELE2 teleports the player to its linked destination after its 15-frame animation; the player cannot be hurt meanwhile (`is_teleporting`) | `world_objects.tp2_ai` | `code`: `duong.lsp:231-266`, `people.lsp:330` |
| TP_DOOR opens when the player is near; down at the door moves the player to the linked door | `world_objects.tpd_ai` | `code`: `teleport.lsp:36-58` |
| SMART_PLAT_SMALL moves between its two linked markers when called (action key) or signalled, carrying the player | `world_objects.platform_ai` | `code`: `platform.lsp:28-95`, `level.c:2789-2838` |
| BOLDER rolls and bounces, hurts what it touches (radius 19, 30 damage) and bursts into five rocks at 0 HP. Its position-restore `let` binds variables named `set_x`/`set_y` instead of calling them, so its platform push is always (0, 0) | `world_objects.bolder_ai`, `small_rock_ai` | `code`: `duong.lsp:279-404` |
| Ants: hang until the player passes below within 130 px (or a signal), fall, land, then run, shoot (aitype 0 fires yellow bolts), pounce, dodge and walk on ceilings | `enemies.ant_ai` | `code`: `abuse/src/ant.c:115-423`, `abuse/inc/ant.hpp` (compiled C) |
| An ant crouching to pounce leaps once its `aistate_time` exceeds 6 (easy), 4 (medium), 2 (hard) or 1 (extreme) | `enemies._alien_wait_time` | `code`: `abuse/src/ant.c:78-88` |
| `ant_congestion` compares x with the other ant's y (a typo in the original) | `enemies._ant_congestion` | `code`: `abuse/src/ant.c:45` |
| Ant HP by aitype: 15, 50, 25, 35, 35, 20; ants are not hurt by ants or ant bullets, nor while hanging | `enemies.ant_ct`, `ant_damage` | `code`: `ant.lsp:398-449` (check: `test_ant_dies_after_fifteen_damage_and_flinches_when_hit`, `test_hanging_ant_ignores_damage`, `test_ants_do_not_hurt_each_other`) |
| A dying ant usually drops its aitype's ammo; with chance 1/(2, 5, 8 or 20, by difficulty) it drops nothing, unless a 1-in-4 roll gives the next ammo type | `enemies.ant_damage` | `code`: `ant.lsp:420-427`, `guns.lsp:19-27` |
| ANT_CRACK releases `create_total` ants once triggered (player within 50x70, or a signal) | `enemies.crack_ai` | `code`: `ant.lsp:524-570` |
| SPRAY_GUN unfolds when activated and the player is within 450x400; it sweeps 270°→350° and back in 10° steps, firing `fire_object` of its aitype at each step; a step happens once `state_time` exceeds `fire_delay` (4), which with the reset and `decide`'s +1 is every 5 ticks (6 or 7 when the sweep turns round); it is only hurt while unfolded and is never pushed | `enemies.spray_gun_ai`, `guner_damage` | `code`: `guns.lsp:196-306`, `weapons.lsp:300-317` |
| HEALTH gives 20 (scaled by difficulty) unless health is full, then disappears | `enemies.hp_up` | `code`: `powerup.lsp:9-15` (check: `test_health_pickup_is_scaled_by_difficulty`, `test_health_pickup_is_left_when_health_is_full`) |
| Ammo icons fall to the floor, then give their `start_hp` as ammo. A weapon you did not have is selected at once (`change_on_pickup`) | `enemies.weapon_icon_ai`, `giver` | `code`: `weapons.lsp:161-237`, `options.lsp` (check: `test_ammo_pickup_gives_weapon_selects_it_and_adds_ammo`) |

## Playing-agent interface (course choices, not rules of the game)

These rows describe the evaluation harness. None of them changes a game rule; each is a choice
made for the course and labelled as one. Details are in `docs/action-interface.md`,
`docs/information-boundary.md` and `docs/budgets.md`.

| Choice | Our code | Evidence |
|---|---|---|
| Death ends the episode as a loss; the original respawns the player at the last console | `agent/interface.py` `_status` | course choice. In the original, a dead player who presses a key is restarted by `cop_mover` (`abuse/src/cop.c:668-674`) through `restart_player`, which in single player reloads the level or the last console save (`data/original/lisp/people.lsp:503-521`). Our game app keeps that restart (`game/app.py`) |
| A player sees the 316x162 play view: visible objects and their visible state, the HUD, on-screen tiles and on-screen events. Objects the original does not draw in play (`dev_draw`: sensors, gates, hidden ants before they drop) are never reported | `agent/observation.py` | course choice; the view size is `code` (Timing table). Checked by `test_observation_exposes_nothing_internal`, `test_only_on_screen_and_drawn_objects_are_visible`, `test_off_screen_events_are_not_reported` |
| Tiles are reported as classes derived from each tile's collision outline | `observation.tile_class` | course choice; outlines are `code` (Data formats table) |
| Actions are strings from `legal_actions()`. Each runs a deterministic controller that emits the original controls for 1 to 15 ticks and stops early when the player is hurt or a new threat comes into view | `interface.AbuseEpisode._execute` | course choice. Controls are `code`: `input.lsp`, `view.c:586-617` |
| Navigation skills plan only over tiles the player has seen (the automap) | `agent/nav.py` | course choice modelled on `abuse/src/automap.c` |
| A refused action changes nothing, takes no ticks, counts as invalid and spends one decision; the reason goes back in `last_result` | `interface.AbuseEpisode.step`, `_refuse` | course choice. Checked by `test_invalid_actions_are_refused_counted_and_change_nothing` |
| Every accepted action takes at least one tick, and none runs past the per-action cap or the tick limit | `interface.AbuseEpisode._execute` | course choice, so a player cannot stall the clock. Checked by `test_every_accepted_action_takes_at_least_one_tick`, `test_every_action_is_capped_at_max_action_ticks`, `test_tick_limit_ends_the_episode` |
| `weapon <name>` presses the original keys: a number key for a weapon with ammo, Ctrl (one press per tick) to reach the laser | `interface.AbuseEpisode._execute` | course choice; the keys are `code`: `abuse/src/view.c:590-603` and `last_weapon`. Checked by `test_switching_to_the_laser_uses_the_original_keys_and_takes_effect_at_once` |
| Progress (`1 - d_best / d_start`, sampled every tick) is computed by the runner and never shown to players. `d` is the A* cost over the full map. It is optimistic: doors, hidden walls and force fields are ignored, and teleporters always work. It is pessimistic in one way: lifts are not modelled | `agent/progress.py`, `runner.run_episode` | course choice. Checked by `test_progress_is_zero_at_the_start_one_at_the_exit_and_uses_teleporters` |
| Token and wall-clock budgets are enforced by the runner from the usage the player reports; a model request is one attempt with a 20 s timeout | `agent/runner.py` `budget_stop`, `agent/providers/` | course rule (no automatic paid retries) |

## Front end (presentation; nothing here changes a rule)

| Behaviour | Our code | Evidence |
|---|---|---|
| Light levels start at the ambient level (clamped 0..63). Each light adds `(outer - r2) * mul_div >> 16` with octagonal distance and the light's shifts, capped at 63. A type-9 rectangle sets the level to its inner radius | `game/lighting.py` `light_levels` | `code`: `abuse/src/light.c:695-740` (`calc_light_value`), `:134` (`mul_div`), `:835-842` (`min_light_level`). Checked by `test_light_levels_follow_light_c`. We compute per pixel; the original uses 4x4 patches |
| Classic darkens each 8-bit colour channel by `63 - level` | `game/render.py` `_apply_lighting` | `code`: `abuse/src/light.c:230-245` (`white_light`), palette in 8 bits (`imlib/port/dos4gw/video.c:483`). The original then snaps to the nearest palette colour; we do not. Checked by `test_classic_darkening_subtracts_from_each_channel` |
| Sound volume: dropped below 15; silent beyond 500 px (octagonal distance from the player); full within 100 px; then `(400 - (d - 100)) * sfx_volume / 400 - (127 - vol)` | `game/audio.py` `original_volume` | `code`: `abuse/src/game.c:134-166` (`play_sound`), `view.c:264-278` (`x_center` is the focus). Checked by `test_sound_volume_follows_game_play_sound`. Classic has no stereo pan; Remastered adds pan |
| Classic draws only the active objects | `game/render.py` `render` | `code`: `abuse/src/level.c:792-804` (`first_active`). Checked by `test_classic_draws_only_active_objects` |
| The camera and positions are interpolated between ticks, at 60 fps | `game/render.py` `note_tick`, `camera` | course choice (presentation). The original had an equivalent development switch, off by default: `abuse/src/dev.c:26`, `game.c:1573-1576`. Checked by `test_the_camera_is_interpolated_between_ticks` |
| On death, space restarts from the last console save, or from the level start if there was none. Restarting the level from the pause menu forgets the old run's save | `game/app.py` `_restore` | `code`: `abuse/src/cop.c:668-674`, `data/original/lisp/people.lsp:503-521`. Checked by `test_restarting_the_level_forgets_the_old_runs_console` and `test_restores_can_be_repeated_any_number_of_times`. One difference: the original keeps the world running while the player lies dead; we pause it |
| Controls: left wins when both directions are held. Ctrl/Home select the previous weapon, Insert/PageUp the next, and the middle button the previous. Down is the action key; the left button fires; the right button is special | `game/app.py` `read_inputs`, `on_key`, `run` | `code`: `data/original/lisp/input.lsp:42-43, 82, 89-91`, `abuse/src/view.c:606-612`, `clisp.c:891-895`. Checked by `test_input_mapping_left_wins_and_the_aim_follows_the_drawn_camera` and `test_original_weapon_keys` |
| After a stall, the app runs at most 4 owed ticks | `game/app.py` `MAX_CATCHUP` | course choice. The original ran one frame per loop with no catch-up. Checked by `test_a_long_stall_runs_only_a_few_ticks` |
| Human sessions are recorded as replayable traces, checked by state hashes and scored with the evaluator's progress | `game/app.py` `_write`, `game/human_replay.py` | course choice. Checked by `test_human_trace_round_trip_with_a_save_restarts_and_a_level_restart` |

## Remastered mode (new rules, not in the original)

These rules exist only with `--mode remastered`. Classic mode, the fidelity tests and every
evaluation run without them (`test_classic_games_and_agent_episodes_never_build_remastered_rules`,
`test_remastered_without_a_dash_plays_exactly_like_classic`). Details are in `docs/remastered.md`.

| Rule | Our code | Evidence |
|---|---|---|
| Dash: 4 ticks at +13 px per tick with feet and head collision (the top half moves with it), 7 ticks without damage, an 18-tick cooldown; a teleport or death cancels it | `engine/remastered.py`; the damage check is in `player.bottom_damage` behind `player_iframes`, which Classic never sets | remastered design, not the original. Checked by the dash tests in `tests/test_remastered.py`, including a run where the player is hurt in both modes with identical results |
| Horde: the arena is the longest flat floor with headroom in Level 1 (x 1680-2400). Ants start in `run_jump` with aistate 6, the state a crack releases them in. Waves are 2 + 2n ants, one every 18 ticks, with a 45-tick start and 90-tick breaks; aitype 0 until wave 3, then a mix. Ants spawn 30 px above the floor at the arena's ends, at the front of the object list, moving at 12 px per tick. After wave n, 2 + n//2 drops: health, then ammo. The player starts with 100 laser rounds and 6 grenades | `engine/horde.py` | remastered design. Only the release state follows `code`: `ant.lsp:524-551` (`crack_ai`). A crack instead adds the ant after itself, moving at 20 px per tick, with the crack's aitype. Checked by `test_horde_waves_drops_and_the_end` |

## Open questions

- `assumed`: the fixed 15 Hz tick. See the timing table.
- `assumed`: the left-to-right argument order for `jrand()` in `sgun_ai` explosions (visual only).
