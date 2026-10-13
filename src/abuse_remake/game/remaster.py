"""Remastered front-end features: records, the stats screen data and the ghost race.

These never change the game's rules. The rule-changing mechanic (the dash) is in
``engine/remastered.py``. Records and ghosts are kept per viewer in ``~/.abuse_remake/``
(``ABUSE_REMAKE_HOME`` overrides it), never in the repo.

The ghost race: while you play, the player's position and animation frame are recorded every
tick. When you finish the level faster than your best, that run becomes the ghost, and later
runs show it as a translucent figure at the same tick of the run timer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

GHOST_VERSION = 1


def data_dir() -> Path:
    return Path(os.environ.get("ABUSE_REMAKE_HOME") or Path.home() / ".abuse_remake")


def run_key(difficulty: str) -> str:
    return f"level01-{difficulty}"


def _read(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write(path: Path, data) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":")))
        tmp.replace(path)
    except OSError:
        pass  # records are a convenience; a read-only home must not stop the game


def load_records() -> dict:
    got = _read(data_dir() / "records.json")
    return got if isinstance(got, dict) else {}


def record_finish(difficulty: str, stats: dict) -> dict:
    """Store a finished run. Returns {"best": previous best or None, "new_best": bool}."""
    recs = load_records()
    key = run_key(difficulty)
    prev = recs.get(key)
    new_best = prev is None or stats["ticks"] < prev.get("ticks", 1 << 30)
    if new_best:
        recs[key] = {k: stats[k] for k in ("ticks", "kills", "secrets", "deaths", "damage_taken")}
        _write(data_dir() / "records.json", recs)
    return {"best": prev, "new_best": new_best}


class GhostRecorder:
    """One compact row per tick: the bottom and top halves' position, state, frame and facing."""

    def __init__(self):
        self.rows: list[list] = []

    def capture(self, game) -> None:
        p = game.player
        row = [p.x, p.y, p.direction, p.state, p.current_frame]
        top = p.objs[0] if p.objs else None
        if top is not None and not top.deleted:
            row += [top.ctype.name, top.state, top.current_frame, top.direction]
        self.rows.append(row)

    def save(self, difficulty: str) -> None:
        _write(data_dir() / f"ghost-{run_key(difficulty)}.json", {"version": GHOST_VERSION, "rows": self.rows})


def load_ghost(difficulty: str) -> list[list] | None:
    got = _read(data_dir() / f"ghost-{run_key(difficulty)}.json")
    if not isinstance(got, dict) or got.get("version") != GHOST_VERSION:
        return None
    rows = got.get("rows")
    return rows if isinstance(rows, list) and rows else None


class GhostPainter:
    """Draws a recorded row as a translucent, tinted figure."""

    TINT = (120, 220, 255)

    def __init__(self, pygame, sprites):
        self.pg = pygame
        self.sprites = sprites
        self.cache: dict = {}

    def _image(self, fig, direction: int):
        key = (id(fig), direction > 0)
        img = self.cache.get(key)
        if img is None:
            fwd, back = self.sprites.figure(fig)
            img = (fwd if direction > 0 else back).copy()
            img.fill((*self.TINT, 255), special_flags=self.pg.BLEND_RGBA_MULT)
            img.set_alpha(110)
            self.cache[key] = img
        return img

    def _blit(self, surf, fig, x, y, direction, xoff, yoff, dy=0) -> None:
        left = x - fig.xcfg if direction > 0 else x - (fig.width - fig.xcfg - 1)
        top = y - fig.height + 1 + dy
        surf.blit(self._image(fig, direction), (round(left - xoff), round(top - yoff)))

    def draw(self, surf, game, row: list, xoff: float, yoff: float) -> None:
        types = game.world.types
        x, y, d, state, frame = row[:5]
        bot = types.get("DARNEL")
        try:
            fig = bot.sequences[state][frame]
        except (AttributeError, KeyError, IndexError):
            return
        self._blit(surf, fig, x, y, d, xoff, yoff)
        if len(row) >= 9:
            tname, tstate, tframe, td = row[5:9]
            try:
                tfig = types[tname].sequences[tstate][tframe]
            except (KeyError, IndexError):
                return
            tx = x + (4 if d < 0 else 0)  # top_draw's offset (see render.py)
            ty = y + 29 - fig.height
            self._blit(surf, tfig, tx, ty, td, xoff, yoff)
