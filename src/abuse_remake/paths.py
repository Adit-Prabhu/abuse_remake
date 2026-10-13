"""Locations of the vendored original data and bundled assets.

Works from a source checkout and from a PyInstaller bundle (``sys._MEIPASS``).
``ABUSE_DATA_DIR`` overrides the data location.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    override = os.environ.get("ABUSE_DATA_DIR")
    if override:
        return Path(override)
    return repo_root() / "data" / "original"


def assets_root() -> Path:
    return repo_root() / "assets"


def level_path(name: str = "level01") -> Path:
    return data_root() / "levels" / f"{name}.spe"
