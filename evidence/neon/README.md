# Neon Protocol v2 development evidence

Rebuild with `uv run python scripts/neon_evidence.py` (no network, no model calls). The
screenshots are real pygame frames. The game's art is third-party pixel art credited in
`assets/neon/PROVENANCE.md`; nothing was produced by an image generator.

| File | What it shows |
|---|---|
| `title.png` | Title: Campaign, Horde, Training, Field Manual, Classic/Remastered, credits |
| `manual-controls.png`, `manual-hostiles.png` | The field manual (F1) |
| `training.png` | Lesson 1 of the training deck, with its marker beacon |
| `sector1-fight.png` | Neon Transit: crawlers, sentries, the concourse |
| `sector2-arrival.png`, `sector2-fight.png` | Reactor Stack: Strider (shield arc), Stinger |
| `sector3-arrival.png`, `sector3-fight.png` | The Hive |
| `sector4-arrival.png`, `sector4-fight.png`, `boss-laser.png` | The Core and the Core Warden's sweeping laser |
| `campaign-complete.png` | Protocol complete |
| `horde.png`, `horde-upgrade.png`, `horde-over.png` | Horde arena, upgrade choice, run over |
| `development-campaign.jsonl` | The recorded session (`neon-trace-2`) |
| `validation.json` | Outcome and replay result |

The development autopilot (`engine/neon/autopilot.py`) plays these runs. It has full map
access and presses only normal controls through the app: nothing is granted, moved or
unlocked by hand, and on death the app restores the last checkpoint as a player would.

This is **not** a playing agent, a fair evaluation or a human playtest. The Classic
evaluation reports and traces were not regenerated or relabelled. The student owns real
playtests and acceptance.
