"""Vendored artist assets retain verified bytes and clear licence provenance."""

import hashlib
import json

from abuse_remake.paths import assets_root


def test_neon_art_manifest_matches_vendored_files_and_includes_licenses():
    root = assets_root() / "neon"
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["author"] == "Luis Zuno (Ansimuz)"
    paths = {entry["path"] for entry in manifest["files"]}
    assert {f"{pack}/public-license.txt" for pack in ("city", "city2", "lab")} <= paths
    for entry in manifest["files"]:
        path = root / entry["path"]
        assert path.suffix.lower() in (".png", ".txt")  # music and demo code are excluded
        assert entry["archive"].startswith("https://opengameart.org/sites/default/files/")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
