# Remastered mode

`uv run abuse-remake` starts in Remastered mode, and `--mode classic` gives the faithful port.
`--playtest` starts in Classic mode, because playtests are the human reference for the Classic
evaluation. The title is a menu (see "The interface" below): play the campaign, play Horde, and
set the difficulty and the mode. Horde is Remastered only, so switching to Classic turns it off.

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

- **Where to start.** The title's PLAY CAMPAIGN line starts at Training; left and right pick
  another playable level (L does the same), or use `--level`. `--skip-title` with no `--level`
  starts at Level 1, as before. Classic mode and playtests stay on Level 1; Horde picks its map
  by arena.
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
- **Level 2:** ultra health on the upper corridor just after the first cleaner robot, flight in
  the long hall, and invisibility on the way to the far-right ladders. All three are on the
  saved route. Level 2 also has the original speed power-up, off the route.
- **Level 1:** none. Its objects stay the original's, so Remastered Level 1, started fresh,
  still plays exactly like Classic. Reached from the training level, it starts with whatever was
  carried in. Ultra health can carry up to 200 health into Level 1; the power itself ends at
  the level change, as the original's `set_player_defaults` clears it. The next heart there then
  sets health back to the cap of 100 (`give_player_health` adds the cap minus health).

**Proof the level can be finished.** `scripts/route_search.py` searches the engine for inputs
that finish a level. `evidence/routes/level00.json` is the route it found through the training
level: up the lift, across the upper rooms, through the teleporters, past all four power-ups and
into the portal room. It was found for the portal to Level 1 (559 ticks); now that Level 2 is
playable, the portal to Level 2 opens on its way there, so the saved route ends at that portal,
in 556 ticks (37 seconds) on hard.
`tests/test_campaign_routes.py` replays it exactly, and checks that it picks up all four power-ups.

## Level 2

Level 2 is a large loop: its exit is just below the start, behind a long way round. Its new
objects are breakable blocks, steps that come and go with their switches, pushers, ceiling
tracking guns that fire rockets, cleaner robots that roll out of hiding, and Juggernauts that
stomp toward you and throw grenades. They are ported from the original Lisp
(`engine/behaviors/campaign_objects.py`, rows in `docs/rule-source-map.md`). Level 1's exit now
leads on to Level 2, and so does the training level's second portal. Level 2's own exit leads to
Level 3, which is not in this remake, so the campaign ends there.

**Proof Level 2 can be finished.** `evidence/routes/level02.json` finishes it in 2,435 ticks (2:42)
on hard. On the way it fights the cleaner robots, opens the start corridor, rides three lifts,
uses two teleport doors and three teleporters, solves the three-switch gate puzzle, crosses the
lava room, loops round the far right, saves at the console that opens the last door, and springs
up the left shaft to the exit. It also picks up the three placed power-ups. No unguided search
could find so long a loop: the route was built segment by segment, from short searches
(`route_search.py --prefix --to`) and scripted steps (a switch press, a lift ride, a teleport),
then replayed whole. The small scripts that chained those segments were development scratch work
and are not in the repo, so the route can be replayed from the repo but not rebuilt from it.
`tests/test_campaign_routes.py` replays it exactly and checks that it ends the level, alive, on
its last input, with the three pickups; it does not check each step of the walkthrough above.
The proof is for Remastered Level 2 with its placed power-ups, on hard with seed 0: it does not
show whether the level can be finished without the ultra health it picks up early.

## The interface (no rule changes)

Remastered's screens are drawn from the original game's own interface art (`game/ui.py`): its
8x8 and 5x7 fonts (`art/fonts.spe`), its window texture and bevel colours (`art/frame.spe`),
the status bar's weapon icons (`art/statbar.spe`), the title art (`art/title.spe`) and the
power-up and pickup sprites. Everything is measured in game pixels, so the interface keeps the
pixel size of the world.

- **Title menu** (`game/screens.py`). The original title art and a menu:
  - PLAY CAMPAIGN (from Training, or another start level);
  - HORDE (choose the arena; your best score is shown);
  - DIFFICULTY, MODE, CONTROLS and QUIT.
  Up and down (or W and S, or the mouse) pick a line; left and right (or the arrows on it)
  change it; Enter or a click starts it. The backdrop shows what Enter would start. The old letter
  keys still work: M, D, H, A and L.
- **The HUD** (`game/modern_hud.py`). Every part is labelled:
  - HEALTH: a heart, a meter and health over its limit (200 with ultra health);
  - DASH: its key and a meter that refills after each dash;
  - weapons: the original icons, each with its key and ammo; the one in your hands is lit and
    framed, and the laser's ammo shows the original font's infinity sign when it cannot run out;
  - TIME, KILLS and, in the campaign, SECRETS;
  - POWER at the top right: the power's icon, HOLD SHIFT / RMB for the ones you hold, and in Horde
    the wave it ends with. It pulses until you first hold the key.
- **Power prompts.** Getting a power shows a large prompt, such as "FLIGHT! HOLD SHIFT OR RIGHT
  MOUSE TO FLY". Right Shift works as well as left Shift in Remastered.
- **Horde.**
  - A briefing before wave 1: the goal, the upgrades, power-ups, score and the controls.
  - One panel at the top left: WAVE, ENEMIES LEFT (or STARTS IN 3, 2, 1 between waves), SCORE and
    COMBO with its time left.
  - The boss's health, with a notch between lives.
  - Between waves, each pickup on the floor is named.
  - The upgrade screen: "WAVE n CLEARED" with the bonuses earned, then three cards. Each card
    shows the item's sprite, what it does, how to use it and how long it lasts. Choose with 1, 2
    or 3, a click, the arrows and Enter, or the gamepad. While the cards are up, play holds still
    (a Horde rule in the engine, so replays agree): the arrows choose instead of walking, nothing
    jumps or fires, a dash is refused and one under way stops. Switching weapons still works.
  - HORDE OVER: Enter plays again in the same arena; Esc goes to the title.
  - R does nothing in Horde play: there are no consoles, and it used to restart the run. The pause
    screen's R restarts the run on purpose.
- **Controls screen.** F1 (or CONTROLS on the title) lists every control, and says what each part
  of the screen means.
- **Pause, death and level complete** use the same panels; T on the pause screen goes back to the
  title.
- **The window.** It can be resized, and the frame is scaled to fit, letterboxed. F11, Alt+Enter
  or Cmd+F (Ctrl+Cmd+F, the macOS shortcut, too) switch full screen in every mode and screen, and
  the green window button works on macOS (`game/display.py`).
- **macOS display fix.** A macOS window surface has an alpha channel. Frames used to be drawn
  straight onto it: the tiles left its alpha at 0, and pygame-ce then filled every text box and
  the ghost's whole rectangle. The HUD's text showed as white bars and the ghost race runner had a
  black box. Frames are now drawn on surfaces with no alpha channel and copied to the window
  (`tests/test_display.py` stands in for the macOS format). This also fixes Classic's HUD on macOS.

Classic keeps its own HUD and pause, death and end screens; only the title menu, the controls
screen and the window are shared.

## Presentation (no rule changes)

- A wider 16:9 view (480x270), 60 fps drawing interpolated between the 15 Hz ticks.
- Dynamic light from muzzle flashes and explosions, and particles for shots, kills, pickups,
  broken walls and dashes. Classic draws only the level's own lights (`render.py`).
- Mouse and gamepad aiming, and the mouse wheel or bumpers to switch weapon.

## New mechanics (rule changes, Remastered only)

| Feature | Controls | What it does | Code |
|---|---|---|---|
| Dash | F, gamepad X | 4 ticks at +13 px per tick through the engine's own collision (it never passes walls), invulnerable for 7 ticks from the start, an 18-tick cooldown, not while teleporting or before play starts | `engine/remastered.py` |
| Horde | HORDE on the title menu, or `--horde`; left and right on it (or A, or `--arena`) pick the arena; 1, 2, 3, a click, the arrows and Enter, or gamepad A/B/X pick an upgrade | Waves of enemies in a sealed arena: the prison floor of Level 1, Level 2's rooftop, or Level 2's Juggernaut floor. Each arena is a room of a real level, and Horde removes the ladders and lifts that lead out of it, so walls and floors made of the level's own tiles close every drop and way out when it loads: nobody can fall, walk, dash or fly out, and every enemy stays in the arena and comes for you (tested for every kind, from both ends). The whole arena is awake: in the original only what is near the view acts, so an enemy released at the far end of a long arena used to stand still until you walked over. Ants first, then flyers, cleaner robots and Juggernauts, and a boss Juggernaut with extra lives every fifth wave. Between waves you get health and ammo, and choose one of three upgrade cards (a power-up for the next wave, full health, ammo, the rocket launcher, or a faster dash). Your kills score points times a combo; a wave without damage earns a bonus. The run ends on death, with a top-10 table per arena and difficulty. Supplies land on the floor, in sight to one side of you. A Horde game recorded before the arenas were sealed cannot be replayed (`horde_version` 3) | `engine/horde.py` |

## Quality-of-life features (no rule changes)

| Feature | Controls | What it does | Code |
|---|---|---|---|
| Quick restart | R | Back to the last console save at once (the original reloads the save after death) | `game/app.py` |
| Stats screen | at the exit | Time, kills, secrets, deaths, damage taken, the player's own shots fired, distinct enemies hit, dashes, and your best time | `game/app.py`, `game/remaster.py` |
| Ghost race | G toggles it | Your best finished run is shown as a translucent figure at the same tick of the run timer. Unlike the player, it is not interpolated between ticks | `game/remaster.py` |
| AI spectator and replay | `abuse-replay --player scripted` or `--trace FILE` | Watch any player (scripted, random, the model, or a `cmd:` program) under Classic rules, with a panel showing what it sees and chooses. A watched player gets the same budgets and fatal-error stops as in `abuse-agent`. Or replay a trace: every observation hash, every step and the final outcome must match. The output goes to the screen, or to MP4 with `--video` | `game/spectate.py` |

Records, ghosts and Horde's high scores are kept per player in `~/.abuse_remake/`, never in the repo. Set
`ABUSE_REMAKE_HOME` to keep them elsewhere.

## Tests

`tests/test_display.py` checks that frames are drawn on surfaces with no alpha channel, that a
window with one (as on macOS) shows exactly the drawn frame, that the ghost has no box around it,
and the window's resizing and full-screen keys. `tests/test_menus.py` checks the title menu (the
campaign starts with Training; keys, mouse and the old letters), the Horde briefing, the controls
screen, the upgrade cards' keys, the power prompt, that R never ends a Horde run, and that every
screen draws in both modes at several scales. `tests/test_horde2.py` checks that every spot on an
arena's floor holds the player, that nobody leaves an arena by walking, jumping, dashing, flying
or running fast (and that the same check finds the way out once an arena's seals are taken
away), that every enemy kind released at either end stays in the arena and comes for the player,
that the seals use only the level's own tiles and only in Horde, that supplies land on the floor
40 to 140 px from the player, and that play holds still while the cards are up, also in a replay.

`tests/test_remastered.py` checks:
- Classic games and agent episodes never build Remastered or Horde rules;
- Remastered without a dash gives the same state hash as Classic on Level 1 (the campaign never shuts Level 1's exit);
- the dash's distance, its stop at walls, its invulnerability and cooldown, and that it survives a
  save and restore;
- Horde's waves, drops and end, its determinism, and its app screen (and `tests/test_horde2.py`: the arenas, roster, boss, cards, combos, high scores, and a recorded card choice that replays);
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
  by any WHO. In 2.0, which we port, only rockets fired by a FLYER or GREEN_FLYER are ignored. The training level's
  flyers are all WHOs, so here they can hurt, and kill, each other and themselves.
- **Kills.** The 1995 `flyer_ai` and `jug_ai` add no kill when a flyer or a Juggernaut dies;
  2.0 does. The Juggernaut's death timing is the same.
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
