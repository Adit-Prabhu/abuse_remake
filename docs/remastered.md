# Remastered mode

`uv run abuse-remake` starts in Remastered mode, and `--mode classic` gives the faithful port. The title
screen toggles the mode (M), the difficulty (D) and Horde (H).

Classic mode is the reconstruction: the original rules and the original 316x162 view. Every
fidelity test and every evaluation runs Classic rules. Remastered keeps the same engine and level
and adds the following. Mechanics that change rules live in the engine behind
`Game(remastered=True)`, which Classic and the playing-agent interface never build.

## Presentation (no rule changes)

- A wider 16:9 view (480x270), 60 fps drawing interpolated between the 15 Hz ticks.
- Dynamic light from muzzle flashes and explosions, and particles for shots, kills, pickups,
  broken walls and dashes.
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
| Stats screen | at the exit | Time, kills, secrets, deaths, damage taken, shots, accuracy, dashes, and your best time | `game/app.py`, `game/remaster.py` |
| Ghost race | G toggles it | Your best finished run is shown as a translucent figure at the same tick of the run timer | `game/remaster.py` |
| AI spectator and replay | `abuse-replay --player scripted` or `--trace FILE` | Watch any player (scripted, random, the model, or a `cmd:` program) under Classic rules, with a panel showing what it sees and chooses. Or replay a trace, checking every observation hash, to the screen or to MP4 with `--video` | `game/spectate.py` |

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
