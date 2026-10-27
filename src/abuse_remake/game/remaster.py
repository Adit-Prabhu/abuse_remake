"""Remastered front-end features: records, the stats screen data and the ghost race.

These never change the game's rules. The rule-changing mechanic (the dash) is in
``engine/remastered.py``. Records and ghosts are kept per viewer in ``~/.abuse_remake/``
(``ABUSE_REMAKE_HOME`` overrides it), never in the repo.

The ghost race: while you play, the player's position and animation frame are recorded every
tick. When you finish the level faster than your best, that run becomes the ghost, and later
runs show it as a see-through red figure labelled GHOST, at the same tick of the run timer. The
campaign list's GHOST setting (or G in play) hides it; runs are still recorded either way.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

GHOST_VERSION = 1


def data_dir() -> Path:
    return Path(os.environ.get("ABUSE_REMAKE_HOME") or Path.home() / ".abuse_remake")


def run_key(difficulty: str, level: str = "level01") -> str:
    """Records and ghosts are kept per level and difficulty (Level 1's keys are unchanged)."""
    return f"{level}-{difficulty}"


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


def load_settings() -> dict:
    got = _read(data_dir() / "settings.json")
    return got if isinstance(got, dict) else {}


def save_setting(name: str, value) -> None:
    _write(data_dir() / "settings.json", {**load_settings(), name: value})


def ghost_shown() -> bool:
    """The campaign's GHOST setting (on unless switched off). Off only hides the ghost: runs are
    still recorded, and a new best still becomes the ghost."""
    return load_settings().get("ghost", True) is not False


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


def record_finish(difficulty: str, stats: dict, level: str = "level01") -> dict:
    """Store a finished run. Returns {"best": previous best or None, "new_best": bool}."""
    recs = load_records()
    key = run_key(difficulty, level)
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

    def save(self, difficulty: str, level: str = "level01") -> None:
        _write(data_dir() / f"ghost-{run_key(difficulty, level)}.json", {"version": GHOST_VERSION, "rows": self.rows})


def load_ghost(difficulty: str, level: str = "level01") -> list[list] | None:
    got = _read(data_dir() / f"ghost-{run_key(difficulty, level)}.json")
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
    """Draws a recorded row as a see-through red figure with a bright red rim. The light-blue
    ghost it replaced was easy to miss and hard to read at first glance (the student,
    2026-10-27); the app labels it GHOST as well."""

    TINT = (255, 70, 60)  # multiplied into the sprite's colours
    LIFT = (110, 0, 0)  # then added, so the dark armour still reads red
    ALPHA = 165
    RIM = (255, 40, 32, 235)

    def __init__(self, pygame, sprites):
        self.pg = pygame
        self.sprites = sprites
        self.cache: dict = {}

    def _image(self, fig, direction: int):
        """The figure, tinted and faded, inside a one-pixel rim (so the image is two pixels wider
        and taller than the figure)."""
        key = (id(fig), direction > 0)
        img = self.cache.get(key)
        if img is None:
            pg = self.pg
            fwd, back = self.sprites.figure(fig)
            src = fwd if direction > 0 else back
            # tint and fade in the pixels themselves: a surface alpha on top of per-pixel alpha
            # takes pygame-ce's own blitter, which painted the whole rectangle on macOS
            body = src.copy()
            body.fill((*self.TINT, 255), special_flags=pg.BLEND_RGBA_MULT)
            body.fill((*self.LIFT, 0), special_flags=pg.BLEND_RGBA_ADD)
            body.fill((255, 255, 255, self.ALPHA), special_flags=pg.BLEND_RGBA_MULT)
            shape = pg.mask.from_surface(src)
            rim = pg.mask.Mask((src.get_width() + 2, src.get_height() + 2))
            for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
                rim.draw(shape, (dx, dy))
            rim.erase(shape, (1, 1))
            img = rim.to_surface(setcolor=self.RIM, unsetcolor=(0, 0, 0, 0))
            img.blit(body, (1, 1), special_flags=pg.BLEND_RGBA_MAX)  # the rim and body never overlap
            self.cache[key] = img
        return img

    def _blit(self, surf, fig, x, y, direction, xoff, yoff, dy=0) -> int:
        """Draw one half; returns its top edge on ``surf``."""
        left = x - fig.xcfg if direction > 0 else x - (fig.width - fig.xcfg - 1)
        top = round(y - fig.height + 1 + dy - yoff)
        surf.blit(self._image(fig, direction), (round(left - xoff) - 1, top - 1))
        return top

    def draw(self, surf, game, row: list, xoff: float, yoff: float) -> tuple[int, int] | None:
        """Draw the ghost; returns the point above its head on ``surf``, for its label."""
        types = game.world.types
        x, y, d, state, frame = row[:5]
        bot = types.get("DARNEL")
        try:
            fig = bot.sequences[state][frame]
        except (AttributeError, KeyError, IndexError):
            return None
        top = self._blit(surf, fig, x, y, d, xoff, yoff)
        if len(row) >= 9:
            tname, tstate, tframe, td = row[5:9]
            try:
                tfig = types[tname].sequences[tstate][tframe]
            except (KeyError, IndexError):
                return round(x - xoff), top
            tx = x + (4 if d < 0 else 0)  # top_draw's offset (see render.py)
            ty = y + 29 - fig.height
            top = min(top, self._blit(surf, tfig, tx, ty, td, xoff, yoff))
        return round(x - xoff), top


def horde_key(difficulty: str, arena: str = "prison") -> str:
    """The best-run key; the prison arena keeps the original Horde's key."""
    return f"horde-{difficulty}" if arena == "prison" else f"horde-{arena}-{difficulty}"


TOP = 10


def _load_scores() -> dict:
    """The high-score tables. A file that cannot be read is moved aside, like records.json."""
    path = data_dir() / "horde_scores.json"
    got = _read(path)
    if not isinstance(got, dict):
        if path.exists():
            try:
                path.replace(path.with_suffix(".unreadable.json"))
            except OSError:
                pass
        return {}
    return got


def horde_top(difficulty: str, arena: str = "prison") -> list[dict]:
    """The top 10 Horde scores for an arena and difficulty, best first."""
    rows = _load_scores().get(f"{arena}-{difficulty}")
    if not isinstance(rows, list):
        return []
    fields = ("score", "cleared", "kills")
    ok = [r for r in rows if isinstance(r, dict) and all(isinstance(r.get(k), int) for k in fields)]
    return sorted(ok, key=lambda r: -r["score"])[:TOP]


def record_horde(difficulty: str, cleared: int, kills: int, arena: str = "prison", score: int = 0) -> dict:
    """Store a Horde result. Returns {"best": previous best or None, "new_best": bool,
    "rank": 1-based place in the arena's top 10 or None, "top": the table}."""
    recs = load_records()
    key = horde_key(difficulty, arena)
    prev = recs.get(key)
    new_best = prev is None or (cleared, kills) > (prev.get("cleared", 0), prev.get("kills", 0))
    if new_best:
        recs[key] = {"cleared": cleared, "kills": kills}
        _write(data_dir() / "records.json", recs)
    entry = {"score": score, "cleared": cleared, "kills": kills}
    table = sorted(horde_top(difficulty, arena) + [entry], key=lambda r: -r["score"])
    rank = next((i + 1 for i, r in enumerate(table) if r is entry), None)
    if rank is not None and rank > TOP:
        rank = None
    table = table[:TOP]
    got = _load_scores()
    got[f"{arena}-{difficulty}"] = table
    _write(data_dir() / "horde_scores.json", got)
    return {"best": prev, "new_best": new_best, "rank": rank, "top": table}
