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

### Breakable walls (the original's "hidden walls")

The original names these objects `HIDDEN_WALL1` to `HIDDEN_WALL_3FLR`
(`data/original/lisp/doors.lsp:168-197`), but they are not invisible. Each is an ordinary drawn
object:
- its pictures come from `art/chars/sect.spe`, with no `dev_draw`, so it is drawn in play like
  any enemy;
- its picture changes as it takes damage (`hwall_damage`).

`evidence/boundary/hidden-walls-classic.png` shows Level 1's first column of them, at x 210 in
Classic at scale 3: cracked stone, unlike the smooth pillar to its left. A careful human can see
it. `scripts/boundary_evidence.py` re-renders the screenshot.

So a visible one is reported as `wall_block`, with whether it is damaged, and `attack W<n>` is
legal while it is on screen. What a human cannot see is never reported:
- its health;
- whether it is activated (some break only after a switch activates them; `hwall_damage` checks
  `(activated)`);
- any wall off screen.

The prompt's "a breakable wall; shoot it" is manual-level advice. A wall that is not yet active
simply does not break, and the player sees that.

### The Classic HUD covers the bottom strip of the view

Classic draws its health, weapons and time over the bottom of the 316x162 play view: a strip
44 window pixels high, about 15 game pixels at scale 3. The original drew its status bar below
the view. An agent's observation covers the whole view, so at the very bottom of the screen it
sees a little more than a human does. Agents and humans are never scored against each other,
and `EVALUATION.md` notes this where it quotes human playtests.

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
