# Remastered mode

`uv run abuse-remake` starts in Remastered mode, and `--mode classic` gives the faithful port.
`--playtest` starts in Classic mode, because playtests are the human reference for the Classic
evaluation. The title screen toggles the mode (M), the difficulty (D) and Horde (H). Horde is
Remastered only, so switching to Classic turns it off.

Classic mode is the reconstruction: the original rules and the original 316x162 view, on
Level 1. Every fidelity test and every evaluation runs Classic rules. Remastered keeps the same
engine and adds the following. Mechanics that change rules live in the engine behind
`Game(remastered=True)`, which Classic and the playing-agent interface never build.

## The campaign: Training, Level 1 and Level 2

Remastered can play more of the original game than Level 1. The shareware v1.01 release has a
training level (`level00`) and Level 2 (`level02`). Both are vendored byte for byte
(`data/original/PROVENANCE.md`). Their objects are ported from the original Lisp and C like
Level 1's, with `code` rows in `docs/rule-source-map.md`. A level is offered once every object in
it is ported (`campaign.playable`), and the title screen lists the playable ones.

- **Where to start.** L on the title screen picks the start level among the playable ones, or
  use `--level`. Classic mode, playtests and Horde stay on Level 1.
- **Exits lead on.** An exit loads the level its number names, as in the original
  (`engine/campaign.py`). The training level ends in the original portal room, with exits to
  Levels 1 to 4. Level 1's exit leads to Level 2, and Level 2's to Level 3.
- **What carries over.** After the stats screen, Enter carries on into the next level. Your
  health, weapons and ammo go with you, and a power-up ends, as in the original's level change
  (`Game(carry=...)`).
- **Exits that cannot lead on.** If the next level cannot be played (Level 3 is not in this
  remake, and a level not yet ported cannot be played), the exit stays shut, with a message, when
  the level has another way on: the training portals to Levels 3 and 4. Otherwise the level ends
  and so does the campaign. Level 1 can therefore always be finished.
- **Restarts.** Quick restart and death go back to this level's last console save. With no save,
  they go to this level's start, at full health, as the original's `restart_player` does.
- **Records.** Best times and ghosts are kept per level and difficulty. A level reached from the
  one before is kept apart from a fresh start of it.
- **Replays.** A recorded session follows the level changes (`abuse-replay --human-trace`).

The shareware levels were built for the 1995 shareware Lisp, while the rules we port are the
2.0-era Lisp (`docs/data-lineage.md`). Differences found in play are listed at the end of this
page.

## The training level and the four power-ups

The training level teaches the controls with the original's own help messages. It has ladders,
lava, springs, a switch ball to shoot, flying robots, and the speed power-up. Its objects and the
power-ups are ported from the original Lisp (`engine/behaviors/campaign_objects.py`). Using a
power was already ported for Level 1 (`cop.c`); Level 1 just never has one.

Hold the special key (right mouse button or Shift) to use the power you carry:

| Power-up | Holding the special key | Otherwise |
|---|---|---|
| Speed | You move twice per tick and leave an afterimage | The pickup flashes the screen white |
| Flight | You rise, trailing clouds | |
| Invisibility | You fade out over 15 ticks, and back in when you let go | |
| Ultra health | | Your health cap is 200, and the pickup gives 100 health (scaled by difficulty) |

The HUD shows the power's original icon at the top right. You keep a power until the level ends.
Training messages appear above the HUD with the modern key in brackets, such as "(or Shift)".

**Where the power-ups are.** The shareware levels have only the speed power-up. Flight,
invisibility and ultra health were registered-version content in 1995. So Remastered places
them itself (`campaign.EXTRA_OBJECTS`, a `remastered design` rule):
- **Training level:** invisibility in the upper corridor past the lift, flight on the ledge before
  the teleport door, and ultra health in the portal room. All three are on the saved route, so
  you meet each one in turn; each replaces the power before.
- **Level 1:** none. Its objects stay the original's, so Remastered Level 1, started fresh,
  still plays exactly like Classic. Reached from the training level, it starts with whatever was
  carried in. Ultra health can carry up to 200 health into Level 1; the power itself ends at
  the level change, as the original's `set_player_defaults` clears it. The next heart there then
  sets health back to the cap of 100 (`give_player_health` adds the cap minus health).

**Proof the level can be finished.** `scripts/route_search.py` searches the engine for inputs
that finish a level. `evidence/routes/level00.json` is the route it found through the training
level: up the lift, across the upper rooms, through the teleporters, past all four power-ups and
into the portal room's exit to Level 1, in 559 ticks (37 seconds) on hard.
`tests/test_campaign_routes.py` replays it exactly, and checks that it picks up all four power-ups.

## Presentation (no rule changes)

- A wider 16:9 view (480x270), 60 fps drawing interpolated between the 15 Hz ticks.
- Dynamic light from muzzle flashes and explosions, and particles for shots, kills, pickups,
  broken walls and dashes. Classic draws only the level's own lights (`render.py`).
- Mouse and gamepad aiming, and the mouse wheel or bumpers to switch weapon.

## New mechanics (rule changes, Remastered only)

| Feature | Controls | What it does | Code |
|---|---|---|---|
| Dash | F, gamepad X | 4 ticks at +13 px per tick through the engine's own collision (it never passes walls), invulnerable for 7 ticks from the start, an 18-tick cooldown, not while teleporting or before play starts | `engine/remastered.py` |
| Horde | `--horde`, or H on the title screen | An arena on the longest flat floor of Level 1 (x 1680-2400) with the level's objects removed. Ants come in growing waves, released the way the original's cracks release them; tougher ant types from wave 3. Health and ammo drop between waves, and the run ends on death | `engine/horde.py` |

## Quality-of-life features (no rule changes)

| Feature | Controls | What it does | Code |
|---|---|---|---|
| Quick restart | R | Back to the last console save at once (the original reloads the save after death) | `game/app.py` |
| Stats screen | at the exit | Time, kills, secrets, deaths, damage taken, the player's own shots fired, distinct enemies hit, dashes, and your best time | `game/app.py`, `game/remaster.py` |
| Ghost race | G toggles it | Your best finished run is shown as a translucent figure at the same tick of the run timer. Unlike the player, it is not interpolated between ticks | `game/remaster.py` |
| AI spectator and replay | `abuse-replay --player scripted` or `--trace FILE` | Watch any player (scripted, random, the model, or a `cmd:` program) under Classic rules, with a panel showing what it sees and chooses. A watched player gets the same budgets and fatal-error stops as in `abuse-agent`. Or replay a trace: every observation hash, every step and the final outcome must match. The output goes to the screen, or to MP4 with `--video` | `game/spectate.py` |

Records and ghosts are kept per player in `~/.abuse_remake/`, never in the repo. Set
`ABUSE_REMAKE_HOME` to keep them elsewhere.

## Tests

`tests/test_remastered.py` checks:
- Classic games and agent episodes never build Remastered or Horde rules;
- Remastered without a dash gives the same state hash as Classic on Level 1 (the campaign never shuts Level 1's exit);
- the dash's distance, its stop at walls, its invulnerability and cooldown, and that it survives a
  save and restore;
- Horde's waves, drops and end, its determinism, and its app screen;
- records, the ghost's recording, saving and drawing, quick restart, and the stats screen;
- replays (including detecting a tampered trace), that spectating leaves the game unchanged, and
  video output.

`tests/test_campaign.py` checks:
- the vendored levels' bytes against the shareware v1.01 release;
- each level's object types against `scope.py`;
- strict loading;
- the exits and what a level change carries;
- locked exits;
- the app's level choice and carry-on;
- a human trace across a level change.

`tests/test_classic_golden.py` pins Classic state hashes computed on `main` before the campaign
work, so Classic cannot drift.

## Known differences in the campaign levels

The shareware levels were built for the 1995 shareware Lisp; we port the 2.0-era rules. Where
this shows:
- **Training messages.** The 1995 `train_ai` also froze the player for 100 ticks while a message
  appeared. The 2.0 version, ported here, does not.
- **Registered content.** In the 1995 shareware, flyers (FLYER, GREEN_FLYER) and the flight,
  invisibility and ultra health power-ups were registered-version content, loaded from files the
  shareware lacks. The 2.0 Lisp defines them, and their art is in the shareware data, so
  Remastered can use them.
- **A flyer saved with no health.** One of the training level's flyers is saved with 0 health,
  so it explodes as soon as it is switched on. That is what the data says, so it is kept.
- **Flyers hurting flyers.** Without the registered flyer file, the 1995 Lisp makes FLYER and
  GREEN_FLYER other names for WHO (`FLYER.LSP:123-128`). So in 1995 a WHO ignored rockets fired
  by any WHO. In 2.0, which we port, only FLYER and GREEN_FLYER are spared. The training level's
  flyers are all WHOs, so here they can hurt, and kill, each other and themselves.
- **Kills.** The 1995 `flyer_ai` adds no kill when a flyer dies; 2.0 does.
- **Flight and invisibility need the registered engine.** The C runs them only when the
  registration file is present (`cop.c:444`, `cop.c:483`, `game.c:2545-2555`). Remastered
  plays as the registered build. A shareware engine would ignore the special key for these two.
- **Training message text.** The 1995 messages run 0 to 10, with different text for 2, 6, 7 and
  8; message 6 was "Click with the RIGHT mouse button to select weapons". We show the 2.0 text
  (`english.lsp`), which names the CTRL and INS keys our controls also have.
- **Health and damage on extreme.** The 1995 `give_player_health` divides by 4 on extreme, and
  its `bottom_damage` doubles damage; 2.0 divides by 5 and triples. This changes hearts, ultra
  health and every hit on extreme, in every level (Level 1 already follows 2.0;
  `docs/data-lineage.md`).
