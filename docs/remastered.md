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

Remastered plays more of the original game than Level 1. The shareware v1.01 release has a
training level (`level00`) and Level 2 (`level02`), and both are vendored byte for byte
(`data/original/PROVENANCE.md`). Their objects are ported from the original Lisp and C like
Level 1's, with `code` rows in `docs/rule-source-map.md`.

- **Where to start.** L on the title screen picks the start level, or use `--level level00`.
  Only levels whose objects are all ported are offered. Classic mode, playtests and Horde stay on
  Level 1.
- **Exits lead on.** An exit loads the level its number names, as in the original
  (`engine/campaign.py`). The training level ends in the original portal room, with exits to
  Levels 1 to 4. Level 1's exit leads to Level 2.
- **What carries over.** After the stats screen, Enter carries on into the next level. Your
  health, weapons and ammo go with you, and a power-up ends, as in the original's level change
  (`Game(carry=...)`).
- **Locked exits.** Exits to Levels 3 and 4, and to any level not yet ported, stay shut and say
  so.
- **Restarts.** Quick restart and death go back to this level's last console save, or to its
  start.
- **Records.** Best times and ghosts are kept per level and difficulty.
- **Replays.** A recorded session follows the level changes (`abuse-replay --human-trace`).

The shareware levels were built for the 1995 shareware Lisp, while the rules we port are the
2.0-era Lisp (`docs/data-lineage.md`). Differences found in play are listed at the end of this
page.

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
- Remastered without a dash gives the same state hash as Classic;
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

None recorded yet.
