# Neon Protocol third-party assets

`scripts/vendor_neon_assets.py` downloads each pack and copies only the files the game uses into
this folder. It writes `manifest.json` with each file's source archive and member path, the
source bytes' SHA-256 and the vendored bytes' SHA-256. `tests/test_neon_app.py` checks every hash.
Downloaded 2026-10-13.
- Images, sound effects and fonts are unmodified copies.
- Two long music tracks were re-encoded to 128 kbit/s MP3 to keep the repository small. The
  manifest records the transform.

At run time the game slices, flips, rotates and recolours art in memory (the runner's yellow
jacket becomes cyan), but never changes the files. No generative image or audio tool was used.

| Folder | Pack | Author | Licence | Source |
|---|---|---|---|---|
| `city/` | Warped City | Luis Zuno (Ansimuz) | CC0 (`city/public-license.txt`) | https://opengameart.org/content/warped-city |
| `city2/` | Warped City 2 | Luis Zuno (Ansimuz) | CC0 (`city2/public-license.txt`) | https://opengameart.org/content/warped-city-2 |
| `lab/` | Warped Sci-Fi Lab | Luis Zuno (Ansimuz) | CC0 (`lab/public-license.txt`) | https://opengameart.org/content/warped-sci-fi-lab |
| `sideview/` | Sideview Sci-Fi (Patreon collection) | Luis Zuno (Ansimuz) | CC0 (`sideview/public-license.txt`) | https://opengameart.org/content/sideview-sci-fi-patreon-collection |
| `weapons/` | Eradication Wars Weapon Sprite Pack v1.1 | Reactorcore (reactorcoregames.com) | **CC-BY 4.0**: the bundled `!info` file says CC-BY 4.0 while the OpenGameArt page lists CC0, and the stricter terms are followed. Credited on the title screen and here | https://opengameart.org/node/179619 |
| `sfx_scifi/` | Sci-Fi Sounds | Kenney (kenney.nl) | CC0 (`sfx_scifi/License.txt`) | https://opengameart.org/content/sci-fi-sounds |
| `sfx_ui/` | Interface Sounds | Kenney | CC0 (`sfx_ui/License.txt`) | https://opengameart.org/content/interface-sounds |
| `sfx_foley/` | 50 RPG sound effects (footsteps, latches) | Kenney | CC0 (`sfx_foley/license.txt`) | https://opengameart.org/content/50-rpg-sound-effects |
| `sfx_creature/` | 80 CC0 creature SFX #2 | rubberduck | CC0 (OpenGameArt page) | https://opengameart.org/content/80-cc0-creture-sfx-2 |
| `music_darkscifi/` | Dark Sci-Fi Audio Pack: sector, airy, pulse, urgent, victory | SRG774 | CC0 (OpenGameArt page) | https://opengameart.org/content/dark-sci-fi-audio-pack |
| `music_specular/` | Specular City (combat) | vitalezzz | CC0 (OpenGameArt page) | https://opengameart.org/content/specular-city |
| `music_pynchon/` | Pynchon (title) | cinameng (James Gargette) | CC0 (OpenGameArt page) | https://opengameart.org/content/pynchon |
| `music_boss/` | Hard Boss Battle 2 | MintoDog | CC0 (OpenGameArt page) | https://opengameart.org/content/hard-boss-battle-2 |
| `fonts/` | Orbitron; Share Tech Mono | The League of Moveable Type / Matt McInerney; Carrois Type Design | SIL Open Font License 1.1 (`fonts/*-OFL.txt`) | https://github.com/google/fonts/tree/main/ofl |

Some packs contain files the game does not take:
- the Warped City soundtrack, which needs attribution to Pascal Belisle;
- demo code, previews and PSD sources.

Credits appear on the Neon title screen and in release packages: the
`NEON-ASSET-CREDITS.md` file and the `neon-licenses/` folder.

The original Abuse data (`data/original/`) is unrelated to these assets and keeps its own
provenance file.
