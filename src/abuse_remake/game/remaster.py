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


RECORD_KEYS = {"level01": ("ticks", "kills", "secrets", "deaths", "damage_taken"), "horde": ("cleared", "kills")}


def _valid_record(key: str, rec) -> bool:
    need = RECORD_KEYS["horde" if key.startswith("horde-") else "level01"]
    return isinstance(rec, dict) and all(isinstance(rec.get(k), int) for k in need)


def load_records() -> dict:
    """Valid records only. A file that cannot be read is moved aside (never silently replaced),
    and entries in the wrong shape are ignored."""
    path = data_dir() / "records.json"
    got = _read(path)
    if got is None and path.exists():
        try:
            path.replace(path.with_suffix(".unreadable.json"))
        except OSError:
            pass
    if not isinstance(got, dict):
        return {}
    return {k: v for k, v in got.items() if isinstance(k, str) and _valid_record(k, v)}


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
    if not isinstance(rows, list) or not rows:
        return None
    for r in rows:  # a hand-edited or partial file must not crash the game
        if not (isinstance(r, list) and len(r) in (5, 9) and all(isinstance(v, int) for v in (r[0], r[1], r[2], r[4]))
                and isinstance(r[3], str)):
            return None
    return rows


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
            import numpy as np

            fwd, back = self.sprites.figure(fig)
            img = (fwd if direction > 0 else back).copy()
            # Bake opacity into the silhouette's alpha. Never tint an opaque bounding box,
            # and keep hidden RGB tinted too so scaled edges cannot acquire black fringes.
            rgb = self.pg.surfarray.pixels3d(img)
            rgb[:] = self.TINT
            del rgb
            alpha = self.pg.surfarray.pixels_alpha(img)
            alpha[:] = np.where(alpha > 0, 110, 0)
            del alpha
            img.set_alpha(255)
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


def record_horde(difficulty: str, cleared: int, kills: int) -> dict:
    """Store a Horde result. Returns {"best": previous best or None, "new_best": bool}."""
    recs = load_records()
    key = f"horde-{difficulty}"
    prev = recs.get(key)
    new_best = prev is None or (cleared, kills) > (prev.get("cleared", 0), prev.get("kills", 0))
    if new_best:
        recs[key] = {"cleared": cleared, "kills": kills}
        _write(data_dir() / "records.json", recs)
    return {"best": prev, "new_best": new_best}
