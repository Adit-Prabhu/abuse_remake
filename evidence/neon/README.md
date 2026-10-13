# Neon Protocol development evidence

Rebuild with `uv run python scripts/neon_evidence.py` (no network or model calls).
The script creates these screenshots and `development-smoke.jsonl`; `validation.json`
records the result. The screenshots are actual pygame output, not image-generation mockups.
The final screenshots use artist-authored shaded sprites and textures; credits/licences and
asset checksums are recorded in `assets/neon/PROVENANCE.md` and `manifest.json`.

- `title.png`: campaign, Horde, training and controls cards.
- `campaign.png`: new environment, courier, enemies and combat HUD.
- `core.png`: final sector and heavy Titan security unit.
- `horde.png`: separate arena and wave counter.
- `training.png`: first performed-action lesson.
- `controls.png`: in-game field manual.
- `extraction.png`: completed campaign.

The smoke controller has full development access to the engine/map. It is **not** a playing
agent, a fair agent evaluation or a human playtest. It supplies normal controls without
granting health, moving objects directly, removing enemies or unlocking relays. At seed 7,
Hard, it finishes all three relays, defeats all 11 enemies and extracts in 533 ticks.
Replay checks four hashes with zero mismatches. Five independent Hard campaign seed runs
also complete in `tests/test_neon_engine.py`; this is reachability evidence, not a balance study.

Existing Classic evaluation reports, traces and recordings have not been regenerated or
relabelled as Neon results. The student still owns real playtests and acceptance.
