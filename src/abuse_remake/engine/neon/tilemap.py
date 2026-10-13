"""Neon tile maps: ASCII sector files, a legend of tiles and entities, and tile queries.

A map file has a header (``key: value`` lines and ``legend X = kind args`` lines), a line
``---``, then one text row per tile row. Tiles are 16 pixels square. Characters that are
entities (the player start, enemies, pickups, consoles ...) stand on an empty tile.

The tile array is copied into each game, because doors open and breakable walls fall; the
parsed file itself is shared and never changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

TILE = 16
SHIFT = 4  # pixel -> tile

EMPTY, SOLID, ONEWAY, LADDER, HAZARD, BREAK, DOOR, RAIL = range(8)
OPAQUE = frozenset((SOLID, BREAK, DOOR))  # blocks bodies, shots and sight

# character -> (kind, *args). Lower-case a-d are switch doors opened by the upper-case switch.
DEFAULT_LEGEND: dict[str, tuple] = {
    "#": ("tile", SOLID), "=": ("tile", ONEWAY), "H": ("tile", LADDER), "^": ("tile", HAZARD),
    "%": ("tile", BREAK), "|": ("tile", RAIL), ".": ("tile", EMPTY), " ": ("tile", EMPTY),
    "a": ("door", "a"), "b": ("door", "b"), "c": ("door", "c"), "d": ("door", "d"),
    "A": ("switch", "a"), "B": ("switch", "b"), "C": ("switch", "c"), "D": ("switch", "d"),
    "R": ("door", "key:red"), "G": ("door", "key:gold"),
    "r": ("pickup", "key_red"), "g": ("pickup", "key_gold"),
    "P": ("player",), "S": ("console",), "E": ("exit",), "L": ("elevator",),
    "T": ("teleport", "1"), "V": ("teleport", "1"), "Y": ("teleport", "2"), "Z": ("teleport", "2"),
    "x": ("enemy", "crawler"), "w": ("enemy", "stinger"), "s": ("enemy", "sentry"),
    "m": ("enemy", "strider"), "o": ("enemy", "drone"), "W": ("enemy", "warden"),
    "n": ("nest",), "f": ("spawn", "flyer"), "M": ("marker",), "l": ("lamp",),
    "+": ("pickup", "health"), "*": ("pickup", "ammo"), "$": ("pickup", "shield"),
    "!": ("pickup", "overcharge"), ">": ("pickup", "haste"), "&": ("pickup", "phase"),
    "j": ("pickup", "boots"),
    "2": ("pickup", "weapon1"), "3": ("pickup", "weapon2"), "4": ("pickup", "weapon3"),
    "5": ("pickup", "weapon4"),
}


@dataclass(frozen=True)
class Entity:
    kind: str
    args: tuple
    tx: int
    ty: int
    char: str


@dataclass(frozen=True)
class MapData:
    name: str
    title: str
    theme: str
    width: int
    height: int
    tiles: bytes
    entities: tuple[Entity, ...]
    doors: dict = field(default_factory=dict)  # group -> tuple of (tx, ty)
    header: dict = field(default_factory=dict)

    def entities_of(self, kind: str) -> list[Entity]:
        return [e for e in self.entities if e.kind == kind]


def parse_map(text: str, name: str = "custom") -> MapData:
    head, sep, body = ("\n" + text).partition("\n---\n")
    if not sep:
        head, body = "", text
    legend = dict(DEFAULT_LEGEND)
    header: dict[str, str] = {}
    for raw in head.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("legend "):
            ch, _, spec = line[7:].partition("=")
            ch, parts = ch.strip(), spec.split()
            if len(ch) != 1 or not parts:
                raise ValueError(f"{name}: bad legend line {raw!r}")
            kind, args = parts[0], tuple(parts[1:])
            legend[ch] = ("tile", _TILE_NAMES[args[0]]) if kind == "tile" else (kind, *args)
            continue
        key, _, value = line.partition(":")
        header[key.strip()] = value.strip()
    rows = body.split("\n")
    while rows and not rows[-1].strip():
        rows.pop()
    if not rows:
        raise ValueError(f"{name}: empty map")
    width = max(len(r) for r in rows)
    height = len(rows)
    tiles = bytearray(width * height)
    entities: list[Entity] = []
    doors: dict[str, list] = {}
    for ty, row in enumerate(rows):
        for tx, ch in enumerate(row.ljust(width)):
            spec = legend.get(ch)
            if spec is None:
                raise ValueError(f"{name}: unknown map character {ch!r} at column {tx}, row {ty}")
            if spec[0] == "tile":
                tiles[ty * width + tx] = spec[1]
            elif spec[0] == "door":
                tiles[ty * width + tx] = DOOR
                doors.setdefault(spec[1], []).append((tx, ty))
            else:
                entities.append(Entity(spec[0], tuple(spec[1:]), tx, ty, ch))
    return MapData(name=name, title=header.get("title", name.upper()), theme=header.get("theme", "transit"),
                   width=width, height=height, tiles=bytes(tiles), entities=tuple(entities),
                   doors={k: tuple(v) for k, v in doors.items()}, header=header)


_TILE_NAMES = {"empty": EMPTY, "solid": SOLID, "oneway": ONEWAY, "ladder": LADDER, "hazard": HAZARD,
               "break": BREAK, "rail": RAIL}

MAP_DIR = Path(__file__).with_name("maps")


@cache
def load_map(name: str) -> MapData:
    return parse_map((MAP_DIR / f"{name}.txt").read_text(), name)


class Grid:
    """The live tile array of one game (mutable copy of ``MapData.tiles``)."""

    def __init__(self, data: MapData):
        self.w, self.h = data.width, data.height
        self.cells = bytearray(data.tiles)

    def at(self, tx: int, ty: int) -> int:
        if 0 <= tx < self.w and 0 <= ty < self.h:
            return self.cells[ty * self.w + tx]
        return SOLID  # outside the map is wall

    def set(self, tx: int, ty: int, code: int) -> None:
        if 0 <= tx < self.w and 0 <= ty < self.h:
            self.cells[ty * self.w + tx] = code

    def at_px(self, x: int, y: int) -> int:
        return self.at(x >> SHIFT, y >> SHIFT)

    def opaque_px(self, x: int, y: int) -> bool:
        return self.at(x >> SHIFT, y >> SHIFT) in OPAQUE

    def ladder_top(self, tx: int, ty: int) -> bool:
        """A ladder tile with no ladder above: its top edge can be stood on."""
        return self.at(tx, ty) == LADDER and self.at(tx, ty - 1) != LADDER

    def line_clear(self, x0: int, y0: int, x1: int, y1: int, step: int = 6) -> bool:
        """True if no opaque tile lies on the segment (sampled every ``step`` pixels)."""
        dx, dy = x1 - x0, y1 - y0
        n = max(abs(dx), abs(dy)) // step + 1
        for i in range(n + 1):
            if self.opaque_px(x0 + dx * i // n, y0 + dy * i // n):
                return False
        return True

    def rect_hits(self, x: int, y: int, w: int, h: int, codes) -> bool:
        for ty in range(y >> SHIFT, ((y + h - 1) >> SHIFT) + 1):
            for tx in range(x >> SHIFT, ((x + w - 1) >> SHIFT) + 1):
                if self.at(tx, ty) in codes:
                    return True
        return False
