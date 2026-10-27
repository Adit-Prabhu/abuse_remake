# Action interface and invalid actions

## Five operations

`agent/interface.py` follows the course's five operations over one Level 1 episode:

| Operation | Used by | What it does |
|---|---|---|
| `reset(seed)` | runner | starts the scenario with that seed |
| `observe(player_id)` | player | the observation (`docs/information-boundary.md`) |
| `legal_actions(player_id)` | player | the actions valid now |
| `step(player_id, action)` | player | runs one action, or refuses it |
| `outcome()` | runner | status, reason, score and counters |

The runner also has `stop(reason)`, which ends an episode for a budget the runner enforces
(`docs/budgets.md`).

## Actions

An action is one string from `legal_actions()`. Matching ignores case and extra spaces.

| Action | Legal when | What the controller does | Ticks |
|---|---|---|---|
| `wait` | always | stand still, aim ahead | 8 |
| `move left`, `move right` | always | run | 6 |
| `jump`, `jump left`, `jump right` | always | press up (and a direction) until landing | up to 15 |
| `explore left`, `explore right` | always | walk along an A* path over the automap toward the furthest seen space that way, or run if there is none | up to 15 |
| `goto <ID>` | the object is on screen and is a pickup, interactive object, door, cracked wall or enemy | walk toward it along the automap | up to 15 |
| `use <ID>` | a switch, console, teleporter, lift or the exit is on screen | walk to it and press the action key (down) | up to 15 |
| `attack <ID>` | an alien, turret, boulder, cracked wall (`wall_block`) or nest is on screen | face it, aim at its middle and fire | up to 12 |
| `fire left`, `fire right`, `fire up`, `fire down` | always | turn that way (left and right), aim 100 px that way and fire the current weapon, naming no target. This is how a player shoots scenery that might break: an uncracked hidden wall is never an object (`docs/information-boundary.md`) | up to 12 |
| `weapon <name>` | a weapon you own other than the current one, with ammo (the laser is always allowed) | press its number key; the laser can have no ammo, so press Ctrl until it is selected, as the original allows (`view.c` `last_weapon`) | 1 (laser: one per Ctrl press) |

Each controller turns the action into the original controls: left, right, up, down, fire and the
aim point (`input.lsp`, `view.c:586-617`). Controllers are deterministic and the same for every
player. An action ends early when the player is hurt, or when a new threat comes into view
(except during `attack`), so a player can react (`test_an_action_stops_when_the_player_is_hurt`,
`test_a_new_threat_stops_an_action_except_attack`). Every accepted action takes at least one tick,
so no player can stop the clock. The per-action cap is `Budgets.max_action_ticks` (15).

## Invalid actions

`step` refuses anything that is not in `legal_actions()` at that moment:

- a reply that is not a string (`None`, a number, an object);
- an empty string, an unknown verb, or a misspelling;
- an object that is not on screen (`attack Z99`);
- a weapon you do not own or have no ammo for.

A refused action:

1. changes no game state and takes no ticks (`state_hash` is unchanged);
2. counts as one invalid action and spends one decision from the budget;
3. returns its reason in `step()`'s result and in the next observation's `last_result`, so the
   player can correct itself.

Nothing is repaired or guessed, and no other action is substituted.

### Where invalid actions come from

| Source | What reaches `step` | Recorded as |
|---|---|---|
| A model answer that is not in the legal list | the answer, unchanged | `not in legal_actions` |
| A model answer whose `action` is not a string | the value, unchanged | `action must be a string` |
| A model reply that is not JSON | `None`; the raw text is kept in the trace | `action must be a string`, with player error `model reply is not a JSON object` |
| A failed request (timeout, rate limit, refusal, truncation, empty answer) | `None` | `action must be a string`, with the player error and its category |
| A rejected or missing credential | `None`, once | as above, category `auth`; the runner then ends the episode as `player failed` |
| A player process whose reply is not a JSON object (even a bare `wait`) | `None`; the raw text is kept in the trace | `action must be a string`, with player error `reply is not a JSON object` |
| A player process that is late | `None`; its late reply is dropped when it comes | as above, with the runner's error |
| A player process that has ended | `None`, once | as above; the runner then ends the episode as `player failed` |

The trace keeps the episode's reason (`error`) and the player's own error (`player_error`)
apart, along with the raw reply, so every refusal can be audited.

## Tests

`tests/test_player_interface.py`:
- `test_invalid_actions_are_refused_counted_and_change_nothing`, over 7 kinds of bad action
- `test_accepted_actions_advance_the_game`
- `test_a_player_that_answers_garbage_is_refused_not_crashed`
- `test_process_player_runs_an_episode_over_the_protocol`

`tests/test_model_player.py`:
- `test_one_request_per_decision_and_the_episode_validates`
- `test_refusals_reach_the_model_through_last_result`
- `test_failed_requests_are_refused_decisions_with_no_retry`
- `test_non_json_answers_are_refused_with_the_raw_text_kept`
- `test_a_bug_in_the_player_refuses_one_decision_instead_of_crashing`
