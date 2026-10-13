# Neon Protocol

The student approved this separate futuristic campaign and Horde expansion on 2026-10-13.
It extends the optional layer; the bounded Classic reconstruction and all model evaluations
remain Level 1 with Classic rules. Neon is a new design, not a fidelity claim about Abuse or
a licensed Tron game. It uses its own engine (`engine/neon.py`) and front end.

## Milestones and merge order

1. `feat/neon-engine`: deterministic campaign, Horde, tutorial and combat contracts.
2. `feat/neon-playable`: neon presentation, menus, visible controls and playable tutorial;
   stacked on the engine branch.
3. `feat/neon-validation`: integration evidence, release support, final fixes and handoff;
   stacked on the playable branch.

Each milestone is a separate pushed PR with an independent read-only review using
`.claude/agents/rules-reviewer.md`. The student merges in order; agents never merge or tag.
The latest branch contains the full playable build before merges.

## Design rules (new optional design)

All gameplay runs at 15 Hz with integer positions and velocities and a local seeded RNG.
Snapshots include RNG, timers, projectiles, pickups, tutorial progress and wave state.
The renderer does not change gameplay. No Neon state reaches the Classic agent interface.

| System | Design |
|---|---|
| Campaign | A new 4200 px digital facility, floor y=520, three relays at x=1260/2600/3850, two sector barriers at 1400/2740, extraction at 4050. Clear hostiles within 360 px in the current sector, then press action within 60 px of a relay. Relay activation restores health and at least 24 rail/8 vortex charges and emits a checkpoint. Extraction needs all relays, grounded proximity within 70 px, and action |
| Movement | 22×42 player, 7 px/tick running, 10 with speed; jump velocity −22, gravity +2, max fall 18 (110 px rise reaches the 95 px first platform). Full solid platforms, pixel-stepped collision; ceiling/world edges block movement. Jump and interaction require a released key between presses |
| Dash | 4 ticks at 24 px/tick; 24-tick cooldown; 6 ticks of invulnerability, including the request tick. Uses movement direction or facing. Refused when dead, finished or cooling down; cannot cross barriers |
| Pulse | Infinite ammo, 12 damage, speed 30, cooldown 3 ticks; stops at first target |
| Rail | 40 damage, speed 70, cooldown 12 ticks; pierces separate enemies once per shot and bypasses sentry shielding; starts with 24 charges |
| Vortex | Speed 18, 14 impact damage, cooldown 18 ticks; creates a radius-95 field for 45 ticks, dealing 14 damage every 5 ticks; starts with 8 charges |
| Enemies | Drone: 36 HP, hovering/ranged. Stalker: 48 HP, fast melee/obstacle jump, 12 contact damage. Sentry: 80 HP, stationary ranged, frontal pulse damage ÷3. Titan: 240 HP, slow melee (22 damage) and three-shot ranged burst. Ranged attacks have 10-tick windup; bullets speed 9. Enemies activate within 850 px horizontally |
| Damage | Difficulty scales incoming damage by 50/75/100/150 percent. Successful damage grants 8-tick protection, including the damage tick; protection decays after combat. Tutorial has no player damage. Lethal damage stops before healing or interaction and freezes simulation |
| Power-ups | Shield: 60 absorb capacity for 150 ticks. Overcharge: double weapon damage for 90 ticks. Speed: faster run for 120 ticks. Health restores 30 up to 100; full health leaves pickup. Ammo gives 12 rail/4 vortex up to 48/16. Pickups expire after 900 ticks. Kills have a seeded 1-in-3 chance of a random supply |
| Hazards | Campaign energy strips: 60 safe ticks (last 15 warning), then 30 active ticks, repeating; 14 damage while grounded on them. Jump or dash avoids them |
| Horde | Separate 1100 px arena. 45-tick initial preparation; wave n has 2+2n enemies in seven repeating bounded edge slots. Stalkers/drones initially, sentries from wave 2, one titan every third wave. Clear all enemies for four supplies and 75-tick break. Death ends the run |
| Tutorial | Separate safe 1100 px deck. Seven performed-action lessons: move 70 px, jump, hit target, change weapon, dash, collect power-up, activate relay. New pickup provided for the pickup lesson if necessary |

## Art and sound provenance

Neon art is authored in the repository as pygame vector drawing code: an armored courier,
four robot silhouettes, digital platforms, parallax skyline, circuitry, energy weapons and
transparent particle effects. No third-party sprites, fonts, trademark logos, or original
sound recordings are downloaded. This gives all characters a consistent palette and clean
alpha, with no black sprite backgrounds. Sound effects are synthesized locally.

The user permitted Internet sprites; that permission is optional, and this implementation
does not depend on an external asset service or add asset licensing obligations.

## Validation

Engine contracts were written first and initially failed to collect because the Neon engine
did not exist. `tests/test_neon_engine.py` checks campaign/Horde separation, movement, locked
barriers, relay edge/proximity/security conditions, extraction, shields, piercing and area
weapons, ammo refusal, Horde progression, actual tutorial completion, deterministic hashes,
repeated saves, and Classic agent isolation. These are design tests, not original-game evidence.
App smoke checks and review records will be added with their milestones.
