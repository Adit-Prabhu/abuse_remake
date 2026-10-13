# Neon Protocol (v2)

Neon Protocol is an optional, separate game built on the Abuse remake. It has a neon,
Tron-style look and keeps the feel of Abuse:
- free 360° mouse aim;
- dark corridors;
- aliens that ambush you from the ceiling;
- a maze that goes up and down as much as across.

`--mode neon` selects it. Classic, Remastered, the playing-agent interface and every evaluation
are untouched. Neon is a new design, not a fidelity claim about Abuse, and its rules are
labelled **neon design** in `docs/rule-source-map.md`.

v2 (2026-10-13) replaces v1 completely. The student rejected v1 for four reasons:
- a flat, one-floor map;
- lifeless enemies (the "stalker" was the player's own sprite tinted pink);
- drawn-line weapons;
- synthesised beeps.

The student chose the hero (the Warped City runner) and the scope (three sectors and a boss,
with Horde kept and upgraded). They asked that Remastered and Classic stay exactly as they are.

## Playing

```sh
uv run abuse-remake --mode neon                    # title: campaign, Horde, training, manual
uv run abuse-remake --tutorial --skip-title        # straight into training
uv run abuse-remake --mode neon --horde --skip-title
```

| Action | Keyboard and mouse | Gamepad |
|---|---|---|
| Move | A / D, ← → | left stick |
| Jump (hold for higher, tap for a hop) | Space, or W when not on a ladder | A |
| Climb a ladder | W / S | stick up/down |
| Crouch, crawl through vents | hold S | stick down |
| Drop through a thin ledge | S + Space | |
| Aim (all the way around you) | mouse | right stick |
| Fire | left click, J | right trigger |
| Dash (invulnerable) | Shift, F, right click | X |
| Interact (consoles, switches, elevators, exit) | E, or S | B |
| Weapons | 1–5, Q, mouse wheel, middle click | bumpers |
| Map | Tab | |
| Pause / field manual | Esc / F1 | Start |
| Volume | − / = | |

The controls are also explained in three places:
- the **Training** deck: 10 lessons, each finished by doing it;
- the **Field Manual**: F1 anywhere, with pages for controls, weapons, hostiles and systems;
- prompts shown the first time you meet a ladder or a grating (for at most 7 seconds each).

## Design

All gameplay is in `src/abuse_remake/engine/neon/`:
- pure Python, no pygame;
- 30 ticks per second;
- integer pixels, and velocities in 1/256 px;
- a seeded local RNG;
- exact snapshots and a canonical state hash.

| System | Design | Code |
|---|---|---|
| Maps | ASCII files of 16-px tiles, with a legend: walls `#`, one-way ledges `=`, ladders `H`, cracked walls `%`, energy floors `^`, elevator rails `\|`, doors, switches, keys, pads, consoles, lamps and enemies. Each sector is a vertical maze, from 72×40 (Core) up to 170×56 tiles (Hive) | `tilemap.py`, `maps/*.txt` |
| Movement | Run at 3.5 px/tick with acceleration and friction. Jump −9.6 px/tick: up to 72 px, holding the button for full height. 5-tick coyote time and a 6-tick jump buffer. Ladders. Drop through ledges and ladder tops. Crouch to 26 px and crawl through 2-tile vents. Dash: 8 ticks × 9 px, invulnerable, 30-tick cooldown. Knock-back and stun when hit. The Vault Boots add one air jump. Movement steps one pixel at a time, so nothing tunnels | `player.py`, `physics.py` |
| Weapons | **Pulse Carbine**: unlimited cyan bolts. **Scatter Arc**: 5-way laser fan with knock-back. **Rail Lance**: hitscan, pierces every enemy, stops at walls. **Plasma Mortar**: arcs, bounces twice, bursts, breaks cracked walls. **Seeker Swarm**: 3 homing missiles. Firing makes noise that enemies hear | `weapons.py` |
| Enemies | **Xeno Crawler** (the Abuse ant reimagined): hangs from ceilings and walks them, drops on you, climbs walls, spits acid, leaps gaps, crouches then pounces, dodges, retreats when hurt, and its scream wakes its neighbours. **Stinger**: circles, telegraphs, dives. **Sentry**: hides in walls and ceilings, pops out, shows a laser sight, fires a leading burst, armoured while hidden. **Strider**: frontal shield (pulse and scatter deflect; weak from behind), lobbed plasma, telegraphed stomp shockwave, slow turn. **Watcher drone**: searchlight; spotting you or being shot raises an alarm that opens vent nests. **Vent nest**: releases crawlers | `enemies.py` |
| Boss | **Core Warden**, in three phases: (1) volleys and a telegraphed stomp; (2) roars, ceiling vents release crawlers; (3) a sweeping laser to jump over (low) or crouch under (high), after which its core is exposed and takes double damage | `enemies.py` `Warden` |
| World | Save consoles (repair, ammo top-up, checkpoint). Switch doors, some timed. Red keycard gate. Elevators that carry riders and can be called. Teleport pads. Cracked-wall secrets. Timed energy floors | `objects.py` |
| Power-ups | Health, ammo, Shield (absorbs 50), Overcharge (×2 damage), Haste, Phase (longer dash), Vault Boots (permanent), keycards | `game.py` `collect` |
| Campaign | Neon Transit → Reactor Stack (climbed bottom to top: elevator, boots, key, gate, teleporter, or a double-jump shaft) → The Hive (ceiling crawlers, crawl vent, the drone hall's 10-second timed door) → The Core (boss). Your arsenal and boots carry over between sectors | `game.py` |
| Horde | A three-tier arena with vents and ladders. Waves grow: crawlers, then stingers from wave 2, striders from wave 4, elites every 5th wave. Each wave hostiles have +6% integrity and hit +3% harder. After each wave, pick 1 of 2 upgrades (each at most 3 times). A hostile stuck for 20 s returns to a vent | `horde.py` |
| Training | 10 lessons: run, jump, ladder, drop, crawl, aim and fire, weapons, dash, switches, save. Nothing can hurt you | `training.py`, `maps/training.txt` |
| Difficulty | Incoming damage ×50 / 75 / 100 / 140%; enemy integrity ×80 / 90 / 100 / 125% (easy, medium, hard, extreme) | `game.py` |

## Presentation

`src/abuse_remake/game/neon/` reads the simulation and never changes it.

**Render.**
- The 640×360 scene is drawn on a 1280×720 canvas, with interpolation between ticks.
- Parallax backdrops from Ansimuz's corridor, lab, hive and bulkhead art, plus deterministic
  background furniture and animated signs.
- Tiles are dark machined plates with Tron-style neon edges, behind a grid on the back wall.
- An Abuse-style darkness light map, lit by lamps, the runner, shots, muzzle flashes and
  explosions.
- An emissive layer with two-level bloom.
- Particles, gibs, decals, after-images and screen shake.
- The gun turns toward the mouse in 32 steps and flips so it is never upside down.
- Enemies telegraph their attacks: a crawler's crouch, a Stinger's red eye, a Sentry's laser
  sight, the Strider's glow and shield, the Warden rearing up, and the beam warning.

**HUD.**
- Integrity and shield, power-up timers, keys and boots.
- A weapon panel with the real gun art.
- A dash pip, the objective, Horde wave info and the boss bar.
- An automap (Tab) of explored tiles, and the upgrade cards.

**Sound.**
- Recorded effects for each event, with random variants, distance falloff, stereo pan and
  per-sound rate limits.
- Footsteps and an ambient hum.
- Music that follows the action: a calm track per sector, the combat track while alerted
  hostiles are near, and the boss track. Tracks fade between each other.

**Traces.** `--record` writes `neon-trace-2`, including weapon selections, upgrade choices,
restores and state-hash checks. `abuse-replay --human-trace` replays it without pygame. Neon v1
traces are refused with a clear message.

## Assets

Every third-party file is listed in `assets/neon/PROVENANCE.md` and `assets/neon/manifest.json`
(source archive, member path, SHA-256). `scripts/vendor_neon_assets.py` recreates them.
- **Art**: Luis Zuno (Ansimuz), CC0: Warped City 1 and 2, Warped Sci-Fi Lab, Sideview Sci-Fi.
- **Weapon art**: Reactorcore, Eradication Wars. CC-BY 4.0 per the bundled file, so it is
  credited on the title screen and in the release.
- **Sound**: Kenney (CC0) and rubberduck (CC0).
- **Music**: vitalezzz, cinameng, SRG774 and MintoDog (all CC0). Two tracks are re-encoded to
  128 kbit/s MP3.
- **Fonts**: Orbitron and Share Tech Mono (SIL OFL).

No generative image or audio tool was used.

## Validation

| Check | Where |
|---|---|
| Movement feel, collisions, ladders, ledges, crouch, dash, elevators, pads, doors, keys | `tests/test_neon_engine.py` (small inline maps) |
| Enemy behaviour: ceiling ambush only with line of sight, scream radius, pounce and flinch, wall climb, sentry armour, Strider shield, alarm opens nests, Warden phases and telegraph | `tests/test_neon_engine.py` |
| Every console, exit, switch, weapon, key and boots can be reached in a tile-graph model (`nav.py`). The red key needs the boots; secrets need explosives | `tests/test_neon_engine.py` |
| The development autopilot finishes the whole campaign with the real physics on easy and hard | `tests/test_neon_engine.py` |
| Determinism, snapshots, Horde scaling and its stuck failsafe | `tests/test_neon_engine.py` |
| App: menus, manual, pause and map freeze the game; rendering is read-only; aim mapping; trace round trip across a sector change and restores; Horde upgrade recording; transparency; asset manifest; silent audio fallback; mode handoff | `tests/test_neon_app.py` |
| Screenshots and a replay-checked development trace | `evidence/neon/` (`scripts/neon_evidence.py`) |

The autopilot (`engine/neon/autopilot.py`) has full map access. It is a development tool for
proving the maps can be completed and for producing evidence. It is not a playing agent, a
fair evaluation or a human playtest.

During development it found real bugs, all fixed:
- two holes in the Transit walls that let you bypass the security door;
- a jump into the timed-door tunnel that was too tight;
- an arena block the Strider could not fit under;
- an attack cooldown that the Warden and Strider shared between contact damage and the stomp.

Balance runs on seeds 1–3: the autopilot wins the campaign with 0 deaths on hard and 0–6 on
extreme.
