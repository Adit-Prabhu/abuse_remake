"""Palettes and tile sets.

Sources (historicalsource/abuse@01cce80):
- palette:   imlib/palette.c:22 (u16 colour count, then count RGB byte triples)
- foretile:  abuse/src/items.c:197 (image, u16 next, u8 damage (unused), boundary)
- backtile:  abuse/src/items.c:185 (image, u16 next)
- numbering: abuse/src/loader2.c:157 ``load_tiles`` (entry name is the tile number;
             a later file redefines an earlier number)
- tile file list and order: data/lisp/startup.lsp ``load_tiles`` (Xenoveritas/abuse@9d1f66f)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .images import Boundary, Image
from .spec import SPEC_BACKTILE, SPEC_FORETILE, SPEC_PALETTE, SpecFile

FORE_W, FORE_H = 30, 15  # abuse foreground tile size (checked on load below)
BACK_W, BACK_H = 64, 64

# data/lisp/startup.lsp, (load_tiles ...): foreground files then background files.
TILE_FILES = (
    "art/fore/foregrnd.spe",
    "art/fore/techno.spe",
    "art/fore/techno2.spe",
    "art/fore/techno3.spe",
    "art/fore/techno4.spe",
    "art/fore/cave.spe",
    "art/fore/alien.spe",
    "art/fore/trees.spe",
    "art/fore/endgame.spe",
    "art/fore/trees2.spe",
    "art/back/backgrnd.spe",
    "art/back/intro.spe",
    "art/back/city.spe",
    "art/back/cave.spe",
    "art/back/tech.spe",
    "art/back/alienb.spe",
    "art/back/green2.spe",
    "art/back/galien.spe",
)
PALETTE_FILE = "art/back/backgrnd.spe"  # startup.lsp: (load_palette "art/back/backgrnd.spe")


@dataclass(frozen=True)
class Palette:
    colors: tuple[tuple[int, int, int], ...]

    @classmethod
    def from_spec(cls, spec: SpecFile, name: str | None = None) -> Palette:
        entries = spec.of_type(SPEC_PALETTE)
        if name is not None:
            entries = [e for e in entries if e.name == name]
        if not entries:
            raise ValueError(f"{spec.path}: no palette entry")
        r = spec.reader(entries[0])
        n = r.u16()
        raw = r.bytes(3 * n)
        return cls(tuple((raw[i], raw[i + 1], raw[i + 2]) for i in range(0, 3 * n, 3)))


@dataclass(frozen=True)
class ForeTile:
    number: int
    image: Image
    next: int
    damage: int
    boundary: Boundary
    source: str


@dataclass(frozen=True)
class BackTile:
    number: int
    image: Image
    next: int
    source: str


@dataclass
class TileSet:
    fore: dict[int, ForeTile] = field(default_factory=dict)
    back: dict[int, BackTile] = field(default_factory=dict)
    redefined: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def nforetiles(self) -> int:
        return max(self.fore, default=-1) + 1

    @property
    def nbacktiles(self) -> int:
        return max(self.back, default=-1) + 1


def _number(name: str) -> int | None:
    # sscanf("%d"): leading digits (after optional whitespace/sign) form the number.
    s = name.strip()
    digits = ""
    for i, ch in enumerate(s):
        if ch.isdigit() or (i == 0 and ch in "+-"):
            digits += ch
        else:
            break
    try:
        return int(digits)
    except ValueError:
        return None


def load_tiles(data_root: str | Path, files: tuple[str, ...] = TILE_FILES) -> TileSet:
    root = Path(data_root)
    ts = TileSet()
    for rel in files:
        path = root / rel
        if not path.exists():
            continue  # load_tiles prints a warning and carries on
        spec = SpecFile.open(path)
        for e in spec.entries:
            if e.type not in (SPEC_FORETILE, SPEC_BACKTILE):
                continue
            num = _number(e.name)
            if num is None:
                continue
            r = spec.reader(e)
            im = Image.read(r)
            if e.type == SPEC_FORETILE:
                # foretile::foretile (items.c:197) does not check the image size; a few
                # shipped tiles (e.g. techno4.spe #300) are 30x18 and overdraw the tile below.
                nxt = r.u16()
                damage = r.u8()
                bnd = Boundary.read(r, "foretile boundry")
                if num in ts.fore:
                    ts.redefined.append(("fore", num, rel))
                ts.fore[num] = ForeTile(num, im, nxt, damage, bnd, rel)
            else:
                nxt = r.u16()
                if num in ts.back:
                    ts.redefined.append(("back", num, rel))
                ts.back[num] = BackTile(num, im, nxt, rel)
    return ts


def load_palette(data_root: str | Path) -> Palette:
    return Palette.from_spec(SpecFile.open(Path(data_root) / PALETTE_FILE))
