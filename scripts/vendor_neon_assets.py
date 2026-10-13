"""Fetch and vendor the third-party art, sound and music used by Neon Protocol.

Downloads each archive once into ``cache/neon-sources/`` (git-ignored), copies only the files
the game uses into ``assets/neon/<pack>/``, and writes ``assets/neon/manifest.json`` with the
source archive, the member path, the source bytes' SHA-256 and the vendored bytes' SHA-256.
Images and sound effects are copied unchanged. Two long music tracks are re-encoded to 128 kbit/s
MP3 with ffmpeg to keep the repository small; the manifest records that transform.

Run: uv run python scripts/vendor_neon_assets.py   (needs network access and ffmpeg)
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "neon"
CACHE = ROOT / "cache" / "neon-sources"
OGA = "https://opengameart.org/sites/default/files/"
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"

PACKS = {
    "city": {
        "title": "Warped City", "author": "Luis Zuno (Ansimuz)", "licence": "CC0 (bundled public-license.txt)",
        "page": "https://opengameart.org/content/warped-city", "archive": OGA + "warped_city_files.zip",
        "root": "warped city files/",
        "files": ["public-license.txt", "SPRITES/player/*/*.png", "SPRITES/misc/*/*.png",
                  "ENVIRONMENT/background/*.png", "ENVIRONMENT/tileset.png",
                  "ENVIRONMENT/props/banner-neon/*.png", "ENVIRONMENT/props/control-box-*.png",
                  "ENVIRONMENT/props/monitorface/*.png", "ENVIRONMENT/props/banner-big/*.png"],
    },
    "city2": {
        "title": "Warped City 2", "author": "Luis Zuno (Ansimuz)", "licence": "CC0 (bundled public-license.txt)",
        "page": "https://opengameart.org/content/warped-city-2", "archive": OGA + "cyberpunk_city_2_files.zip",
        "root": "cyberpunk city 2 files/",
        "files": ["public-license.txt", "Environment/background/back.png", "Environment/background/middle.png",
                  "Environment/background/front.png", "Environment/props/lights/*.png",
                  "Sprites/explosion-a/*.png", "Sprites/enemy-shoot/*.png", "Sprites/player-shoot/*.png"],
    },
    "lab": {
        "title": "Warped Sci-Fi Lab", "author": "Luis Zuno (Ansimuz)", "licence": "CC0 (bundled public-license.txt)",
        "page": "https://opengameart.org/content/warped-sci-fi-lab", "archive": OGA + "scifi_lab_files.zip",
        "root": "Scifi lab Files/",
        "files": ["public-license.txt", "layers/back.png", "layers/middle.png", "layers/front.png",
                  "layers/Props/*.png"],
    },
    "sideview": {
        "title": "Sideview Sci-Fi (Patreon collection)", "author": "Luis Zuno (Ansimuz)",
        "licence": "CC0 (bundled public-license.txt)",
        "page": "https://opengameart.org/content/sideview-sci-fi-patreon-collection",
        "archive": OGA + "Sideview%20Sci-Fi%20-%20Patreon%20Collection.zip",
        "root": "Sideview Sci-Fi - Patreon Collection/",
        "files": ["public-license.txt",
                  "Sprites/alien-walking-enemy/PNG/alien-enemy-*.png", "Sprites/alien-flying-enemy/sprites/*.png",
                  "Sprites/bipedal-Unit/PNG/sprites/*.png", "Sprites/mech-unit/sprites/*.png",
                  "Sprites/Explosion/sprites/*.png", "Sprites/space-marine/PNG/bullet.png",
                  "Sprites/space-marine/PNG/wall-impact-blast.png",
                  "Environments/cyberpunk-corridor-files/PNG/layers/*.png",
                  "Environments/alien-environment/PNG/layers/*.png",
                  "Environments/sci-fi-environment-background-files/PNG/back.png",
                  "Environments/sci-fi-environment-background-files/PNG/sky.png",
                  "Environments/bulkhead-walls/PNG/*.png",
                  "Environments/cyberpunk-detective-prop-files/PNG/*.png"],
        "skip": ["*PREVIEW*", "*preview*"],
    },
    "weapons": {
        "title": "Eradication Wars Weapon Sprite Pack", "author": "Reactorcore (reactorcoregames.com)",
        "licence": "CC-BY 4.0 (the bundled !info file; the OpenGameArt page lists CC0, and the stricter "
                   "bundled terms are followed, so Reactorcore is credited)",
        "page": "https://opengameart.org/node/179619", "archive": OGA + "eradication_wars_weapon_sprite_pack_v1.1.zip",
        "root": "Eradication Wars Weapon Sprite Pack/",
        "files": ["!info Eradication Wars Weapon Sprite Pack.txt", "Tiny Bonus/tiny weapons/*.png",
                  "Tiny Bonus/tiny projectiles/*.png", "Tiny Bonus/tiny muzzles/*.png"],
    },
    "sfx_scifi": {
        "title": "Sci-Fi Sounds", "author": "Kenney (kenney.nl)", "licence": "CC0 (bundled License.txt)",
        "page": "https://opengameart.org/content/sci-fi-sounds", "archive": OGA + "sci-fi_sounds.zip", "root": "",
        "files": ["License.txt", "Audio/laserSmall_*.ogg", "Audio/laserLarge_*.ogg", "Audio/laserRetro_*.ogg",
                  "Audio/explosionCrunch_*.ogg", "Audio/lowFrequency_explosion_*.ogg", "Audio/impactMetal_*.ogg",
                  "Audio/forceField_*.ogg", "Audio/doorOpen_*.ogg", "Audio/doorClose_*.ogg",
                  "Audio/computerNoise_*.ogg", "Audio/thrusterFire_00[0-2].ogg", "Audio/slime_*.ogg",
                  "Audio/spaceEngineLow_000.ogg", "Audio/engineCircular_000.ogg"],
    },
    "sfx_ui": {
        "title": "Interface Sounds", "author": "Kenney (kenney.nl)", "licence": "CC0 (bundled License.txt)",
        "page": "https://opengameart.org/content/interface-sounds", "archive": OGA + "kenney_interfaceSounds.zip",
        "root": "",
        "files": ["License.txt", "Audio/click_00[1-3].ogg", "Audio/confirmation_00[1-4].ogg", "Audio/back_00[1-2].ogg",
                  "Audio/select_00[1-3].ogg", "Audio/error_00[1-4].ogg", "Audio/glitch_00[1-4].ogg",
                  "Audio/switch_00[1-3].ogg", "Audio/maximize_00[1-3].ogg", "Audio/toggle_00[1-2].ogg"],
    },
    "sfx_foley": {
        "title": "50 RPG sound effects", "author": "Kenney (kenney.nl)", "licence": "CC0 (bundled license.txt)",
        "page": "https://opengameart.org/content/50-rpg-sound-effects", "archive": OGA + "RPGsounds_Kenney.zip",
        "root": "", "files": ["license.txt", "OGG/footstep0[0-9].ogg", "OGG/metalLatch.ogg", "OGG/metalClick.ogg",
                              "OGG/metalPot[1-3].ogg"],
    },
    "sfx_creature": {
        "title": "80 CC0 creature SFX #2", "author": "rubberduck", "licence": "CC0 (OpenGameArt page)",
        "page": "https://opengameart.org/content/80-cc0-creture-sfx-2", "archive": OGA + "80-CC0-creature-sfx-2.zip",
        "root": "", "files": ["alien_*.ogg", "bug_*.ogg", "die_*.ogg", "monster_1[0-9].ogg", "roar_*.ogg",
                              "slime_0[1-6].ogg", "attack_0[1-5].ogg", "stomp_01.ogg", "weird_0[6-9].ogg",
                              "human_0[1-8].ogg"],
    },
    "music_darkscifi": {
        "title": "Dark Sci-Fi Audio Pack", "author": "SRG774", "licence": "CC0 (OpenGameArt page)",
        "page": "https://opengameart.org/content/dark-sci-fi-audio-pack", "archive": OGA + "ogg.zip", "root": "ogg/",
        "files": ["sector.ogg", "airy.ogg", "pulse.ogg", "urgent.ogg", "victory.ogg"],
    },
    "music_specular": {
        "title": "Specular City", "author": "vitalezzz", "licence": "CC0 (OpenGameArt page)",
        "page": "https://opengameart.org/content/specular-city", "file": OGA + "specular_city_1.mp3",
        "save_as": "specular_city.mp3", "transcode": True,
    },
    "music_pynchon": {
        "title": "Pynchon", "author": "cinameng (James Gargette)", "licence": "CC0 (OpenGameArt page)",
        "page": "https://opengameart.org/content/pynchon", "file": OGA + "pynchon.mp3", "save_as": "pynchon.mp3",
    },
    "music_boss": {
        "title": "Hard Boss Battle 2", "author": "MintoDog", "licence": "CC0 (OpenGameArt page)",
        "page": "https://opengameart.org/content/hard-boss-battle-2", "file": OGA + "hard_boss_battle_2_bpm210_0.ogg",
        "save_as": "hard_boss_battle_2.mp3", "transcode": True,
    },
    "fonts": {
        "title": "Orbitron and Share Tech Mono", "author": "Matt McInerney (Orbitron); Carrois Type Design",
        "licence": "SIL Open Font License 1.1 (bundled OFL.txt files)",
        "page": "https://github.com/google/fonts/tree/main/ofl",
        "direct": [(GF + "orbitron/Orbitron%5Bwght%5D.ttf", "Orbitron.ttf"),
                   (GF + "orbitron/OFL.txt", "Orbitron-OFL.txt"),
                   (GF + "sharetechmono/ShareTechMono-Regular.ttf", "ShareTechMono-Regular.ttf"),
                   (GF + "sharetechmono/OFL.txt", "ShareTechMono-OFL.txt")],
    },
}
TRANSCODE = ["-vn", "-c:a", "libmp3lame", "-b:a", "128k"]


def fetch(url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    name = "_".join(url.split("/")[-2:]) if url.startswith(GF) else url.rsplit("/", 1)[1]
    path = CACHE / name.replace("%20", "_").replace("%5B", "[").replace("%5D", "]")
    if not path.exists():
        print("downloading", url)
        req = urllib.request.Request(url, headers={"User-Agent": "abuse-remake-vendor/1"})
        with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:  # noqa: S310 - fixed https URLs
            shutil.copyfileobj(r, f)
    return path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def vendor() -> dict:
    if OUT.exists():
        for child in OUT.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
    files = []
    for pack_id, pack in PACKS.items():
        dest = OUT / pack_id
        dest.mkdir(parents=True, exist_ok=True)
        if "direct" in pack:
            for url, name in pack["direct"]:
                data = fetch(url).read_bytes()
                out = dest / name
                out.write_bytes(data)
                files.append({"path": out.relative_to(OUT).as_posix(), "pack": pack_id, "source": url,
                              "source_sha256": sha(data), "sha256": sha(data), "transform": None})
            continue
        if "file" in pack:
            src = fetch(pack["file"])
            data = src.read_bytes()
            out = dest / pack["save_as"]
            transform = None
            if pack.get("transcode"):
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), *TRANSCODE, str(out)], check=True)
                transform = "ffmpeg " + " ".join(TRANSCODE)
            else:
                out.write_bytes(data)
            files.append({"path": out.relative_to(OUT).as_posix(), "pack": pack_id, "source": pack["file"],
                          "source_sha256": sha(data), "sha256": sha(out.read_bytes()), "transform": transform})
            continue
        archive = fetch(pack["archive"])
        with zipfile.ZipFile(archive) as z:
            members = [n for n in z.namelist() if not n.startswith("__MACOSX") and not n.endswith("/")]
            chosen = []
            for n in members:
                rel = n[len(pack["root"]):] if n.startswith(pack["root"]) else None
                if rel is None or not any(fnmatch.fnmatchcase(rel, pat) for pat in pack["files"]):
                    continue
                if any(fnmatch.fnmatchcase(rel, pat) for pat in pack.get("skip", ())):
                    continue
                chosen.append((n, rel))
            if not chosen:
                raise SystemExit(f"{pack_id}: nothing matched")
            for n, rel in sorted(chosen):
                data = z.read(n)
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
                files.append({"path": out.relative_to(OUT).as_posix(), "pack": pack_id,
                              "source": pack["archive"] + "#" + n, "source_sha256": sha(data), "sha256": sha(data),
                              "transform": None})
    manifest = {"note": "Third-party assets for Neon Protocol. See PROVENANCE.md. Generated by "
                        "scripts/vendor_neon_assets.py; do not edit by hand.",
                "packs": {k: {f: v[f] for f in ("title", "author", "licence", "page")} for k, v in PACKS.items()},
                "files": files}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


if __name__ == "__main__":
    m = vendor()
    total = sum((OUT / f["path"]).stat().st_size for f in m["files"])
    print(f"vendored {len(m['files'])} files, {total / 1e6:.1f} MB", file=sys.stderr)
