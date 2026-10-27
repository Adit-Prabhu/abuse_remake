# Information boundary

What a playing agent may know, how that is enforced, and which tests check it.

## The rule

A player knows what a human player of the original would see on screen, plus what a human
could read in the manual. It never sees the engine's state, the level file, the rule map, the
evaluator's progress measure or credentials.

## What a player receives

Each decision the player gets two things, as plain JSON (`agent/observation.py`, schema
`abuse-obs-1`):

1. **The observation**:
   - `player`: position, health, facing, posture (on the ground, in the air, hurt, dead), the
     current weapon, ammo per weapon owned, and whether it is teleporting. This is the original HUD
     plus what the screen shows of the player.
   - `view`: the 316x162 play view rectangle in level pixels (`abuse/src/view.c:636-676`).
   - `tiles`: the on-screen tiles as classes (open, solid, slope, ledge, overhang, partly solid),
     derived from each tile's collision outline. The one exception is a hidden wall that imitates
     a ledge, floor or pillar, whose cells show as solid (see "Breakable walls" below).
   - `objects`: every object whose picture overlaps the view and that the original draws in
     play. For each one: a stable label (`E3`, `S1`, ...), a public kind, its position and offset
     from the player, and only state that is visible on screen (door open or closed, switch on or
     off, alien hanging or running, turret folded or active, wall cracked).
   - `events`: what happened since the last decision that the player would see or hear on screen
     (within 40 px of the view at the tick it happened), plus its own pickups and the damage it
     took. A refused decision has no events of its own.
   - `last_result`: whether the last action was accepted and, if not, why.
   - `tick`, `ticks_left`, `status`.
2. **The legal actions**: strings built from the same observation (`docs/action-interface.md`).

## What a player never receives

| Never sent | Why it matters | Enforced by |
|---|---|---|
| Objects off screen, and objects the original does not draw in play (sensors, gates, hidden ants before they drop, ambient sounds) | the level's layout and its traps | `visible_objects` filters by picture overlap and by `KINDS` |
| Enemy health, AI state, timers, links, internal variables, the random table and its position | perfect prediction of enemies and logic | only the fields listed above are copied |
| Engine type names and object UIDs | a key into the level file | public kinds and labels, given only when an observation first shows the object, nearest first; an object seen only in the middle of an action uses no label (`test_labels_are_given_only_at_decision_time_nearest_first`) |
| The episode seed | it is the random table's start position, so it would predict every random draw | the start message carries no seed; the random player seeds itself from its first observation |
| The level file, `docs/rule-source-map.md`, the original Lisp | the whole map and every rule | players run as separate processes that get only JSON (`agent/protocol.py`) |
| The evaluator's progress measure and the route to the exit | the answer | computed in `agent/progress.py` on the runner side; the end-of-episode message carries only the episode's own outcome (`test_players_get_the_episode_outcome_without_evaluator_data`) |
| Credentials | | player processes get a minimal environment (`protocol.BASE_ENV`). Only the model player also gets the variables its provider's SDK reads (`MODEL_ENV_PREFIXES`), and those never enter prompts, observations or traces (`test_player_processes_get_no_credentials_unless_they_are_the_model_player`) |

## Two judgement calls

### Breakable walls (the original's "hidden walls") are secrets

The original names these objects `HIDDEN_WALL1` to `HIDDEN_WALL_3FLR`
(`data/original/lisp/doors.lsp:168-197`). Each is drawn in play from `art/chars/sect.spe`, with
no `dev_draw`. It blocks along its figure's outline, which is its whole picture box. Its frame,
`3*(25-hp)//25`, shows cracks as it loses health (`hwall_damage`). Some ignore damage until a
switch activates them, and one strong hit can destroy a wall straight from frame 0.

*Drawn* is not the same as *recognisable*. Two renders show this, both re-rendered by
`scripts/boundary_evidence.py`:
- `evidence/boundary/hidden-wall-types.png`: the first instance of each type in Level 1.
- `evidence/boundary/hidden-wall-frames.png`: the same instances at frames 0, 1 and 2, with
  the blocking outline.

Every sprite is opaque. The dark ones (luminance about 29) copy the background panels, and the
bright ones (about 50) copy the ledges, floors and pillars. So each type has its own look:

| Type | Uncracked, it looks like | Cracks show from frame |
|---|---|---|
| `HIDDEN_WALL1`, `HIDDEN_WALL5` | cracked stone (the column by the start) | 0, so it always looks breakable |
| `HIDDEN_WALL4`, `HIDDEN_WALL_3FLR`, `HIDDEN_WALL_3WAL` | a ledge, a floor, a pillar | 1 |
| `HIDDEN_WALL_2x2` | the background | 1 |
| `HIDDEN_WALL2` | the background | 2 |
| `HIDDEN_WALL3` | the background | never: its cracks are invisible on the dark panels |

**What a player gets** (`observation.HIDDEN_WALL_LOOK`, `wall_look`):
- **Looks cracked:** a `wall_block` object, with `cracks` (0 to 2), that `attack` and `goto` can
  name.
- **Looks like a ledge, floor or pillar:** solid cells (`#`) in the tile grid, exactly the
  cells inside its outline. The navigation map remembers them off screen, like any wall seen
  earlier, until it sees them without the wall. So nothing tells such a cell apart from a real
  wall.
- **Looks like the background:** nothing. The tile grid shows the tiles behind it. Collision
  stops a player there, as it stops a human who walks into what looks like empty space.

No wall is ever named before it looks breakable. A player shoots scenery that might break with
`fire left|right|up|down`, which names nothing. A human can always shoot at a wall, so every
player now can too.

**History.** Until 2026-10-26 every hidden wall on screen was reported as a `wall_block`, which
leaked six types' secrets. The first fix (PR #25) showed every uncracked wall as solid. Its
review found two remaining leaks:
- a solid lump appeared where the screen shows background;
- the plain `HIDDEN_WALL1` was hidden while it looks exactly like the cracked ones beside it.

Rendering every frame of every type produced the table above. Its tests are:
- `test_each_hidden_wall_shows_only_as_it_looks` (all eight types, uncracked and cracked);
- `test_no_wall_is_named_before_it_looks_breakable_at_the_start`;
- `test_solid_looking_walls_are_remembered_off_screen_like_any_wall`;
- `test_a_cracked_wall_blocks_navigation_over_its_whole_outline`.

### The Classic HUD covers a band of the view

Classic draws its HUD over the play view, at fixed window pixels:
- the health bar and the selected-weapon box are opaque;
- the time, kills and secrets are bare text;
- the band runs from 46 to 24 window pixels above the bottom, which is about 7 game pixels at
  scale 3 (it shrinks as the window scale grows).

The original drew its status bar outside the play view: the view is y 5..166 of the 320x200
screen (`abuse/src/view.c:636-676`, the Timing table of the rule map). An agent's observation
covers the whole view, so in that band it can see a little that a human cannot. Agents and
humans are never scored against each other. Any comparison with human playtests has to say
this.

## How it is enforced

- **Process isolation.** By default every player is a child process speaking JSON lines
  (`agent/protocol.py`). It holds no reference into the game and gets a minimal environment. The
  in-process mode for fast tests passes JSON copies (`InProcessPlayer`). Process isolation is a
  boundary on what the runner hands over; it is not a security sandbox against a hostile program.
- **Copies, not views.** `observe()` returns a detached JSON copy; a player that edits it
  changes nothing (`test_in_process_player_gets_copies`).
- **One builder.** `legal_actions()` and the motor skills use the same visibility filter as the
  observation, so an action can only name an object on screen.
- **The motor skills plan only over the automap.** The `goto`, `use` and `explore` skills search
  only the tiles the player has already seen (`agent/nav.py`, modelled on
  `abuse/src/automap.c`). All players get the same skills.
- **The model player imports no engine code** (`test_model_player_imports_no_engine_code`).
  Its prompt is a pure function of the observation, the legal actions and its own memory
  (`test_prompt_is_a_pure_function_of_the_observation`).

## The model player's prior knowledge

The system prompt (`agent/prompts.py`) holds only manual-level knowledge: the goal, the controls
as actions, what each kind of object is (as the screen shows it), and the weapons. It also
holds the same priors the scripted baseline's rules contain, so neither player starts with more:
head right first, shoot
breakable walls, try switches, heal when hurt, deal with threats first. It contains no map
knowledge: nothing about where the exit, switches or secrets are
(`test_system_prompt_has_no_map_knowledge`).

## Memory conditions

All three conditions are built only from observations the player already received
(`agent/memory.py`):

- **M0**: the current observation.
- **M1**: plus the last 8 turns: action, result, health, position and events.
- **M2**: plus the model's own notes (at most 600 characters, cut if longer) and an automap
  summary: how far it has seen, and the objects it saw that are now off screen, with their last
  known state.

## Tests

`tests/test_player_interface.py`:
- `test_observation_exposes_nothing_internal`
- `test_only_on_screen_and_drawn_objects_are_visible`
- `test_legal_actions_only_name_visible_objects`
- `test_off_screen_events_are_not_reported`
- `test_in_process_player_gets_copies`

`tests/test_model_player.py`:
- `test_model_player_imports_no_engine_code`
- `test_prompt_is_a_pure_function_of_the_observation`
- `test_system_prompt_has_no_map_knowledge`
- `test_memory_conditions_show_what_they_promise`
- `test_automap_remembers_objects_off_screen_and_forgets_ones_that_vanished`
