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
     derived from each tile's collision outline.
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
no `dev_draw`, and its picture changes as it takes damage (`hwall_damage`). Some only break
after a switch activates them, because `hwall_damage` checks `(activated)`.

*Drawn* is not the same as *recognisable*. `evidence/boundary/hidden-wall-types.png` shows the
first instance of each of the eight types in Level 1, in place, in Classic:
- **Cracked stone, visibly unlike the scenery:** `HIDDEN_WALL1`, and partly `HIDDEN_WALL5`.
- **Indistinguishable from the floor, wall or dark background around them:** the other six.
  The front end even counts a destroyed one as a "secret".

`evidence/boundary/hidden-walls-classic.png` is the full view at the first column.
`scripts/boundary_evidence.py` re-renders both.

**Finding (2026-10-26).** Until this was checked, the observation reported every hidden wall on
screen as a `wall_block` object, and `attack W<n>` was legal for it. So the observation and the
legal-action list told an agent which pieces of scenery are breakable, which a human playing
for the first time would not know. That is a leaked secret. The interface is being changed
before any tuning or live run, so that an undamaged hidden wall shows only as what it looks
like. The change will be described here once it lands.

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
