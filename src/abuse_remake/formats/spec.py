"""Reader for the SPEC1.0 container used by every Abuse data file.

Layout (imlib/include/specs.hpp, comment block; imlib/specs.c ``startup``):
8-byte signature ``SPEC1.0\\0``, a little-endian u16 entry count, then per
entry: type (u8), name length (u8), name (NUL-terminated), flags (u8),
size (u32) and offset (u32). This engine version never writes linked
entries, and ``startup`` always reads size and offset, so neither do we.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

SIGNATURE = b"SPEC1.0"

SPEC_INVALID_TYPE = 0
SPEC_COLOR_TABLE = 1
SPEC_PALETTE = 2
SPEC_IMAGE = 4
SPEC_FORETILE = 5
SPEC_BACKTILE = 6
SPEC_CHARACTER = 7
SPEC_MORPH_POINTS_8 = 8
SPEC_MORPH_POINTS_16 = 9
SPEC_GRUE_OBJS = 10
SPEC_EXTERN_SFX = 11
SPEC_DMX_MUS = 12
SPEC_PATCHED_MORPH = 13
SPEC_NORMAL_FILE = 14
SPEC_COMPRESS1_FILE = 15
SPEC_VECTOR_IMAGE = 16
SPEC_LIGHT_LIST = 17
SPEC_GRUE_FGMAP = 18
SPEC_GRUE_BGMAP = 19
SPEC_DATA_ARRAY = 20
SPEC_CHARACTER2 = 21
SPEC_PARTICLE = 22
SPEC_EXTERNAL_LCACHE = 23


class SpecError(ValueError):
    """The bytes are not a well-formed SPEC1.0 file."""


@dataclass(frozen=True)
class SpecEntry:
    type: int
    name: str
    size: int
    offset: int


class Reader:
    """Little-endian cursor over a byte buffer (bFILE::read_short/read_long)."""

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def seek(self, pos: int) -> None:
        if not 0 <= pos <= len(self.data):
            raise SpecError(f"seek to {pos} outside file of {len(self.data)} bytes")
        self.pos = pos

    def _take(self, n: int) -> bytes:
        end = self.pos + n
        if end > len(self.data):
            raise SpecError(f"read of {n} bytes at {self.pos} runs past end of file")
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def u8(self) -> int:
        return self._take(1)[0]

    def s8(self) -> int:
        return struct.unpack("<b", self._take(1))[0]

    def u16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def s16(self) -> int:
        return struct.unpack("<h", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def s32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def bytes(self, n: int) -> bytes:
        return self._take(n)

    def pstring(self) -> str:
        """Length-prefixed string; the stored length includes the NUL."""
        n = self.u8()
        return self._take(n).split(b"\0", 1)[0].decode("latin-1")


class SpecFile:
    def __init__(self, data: bytes, path: str = "<bytes>"):
        self.data = data
        self.path = path
        if data[: len(SIGNATURE)] != SIGNATURE:
            raise SpecError(f"{path}: missing SPEC1.0 signature")
        r = Reader(data, 8)
        total = r.u16()
        entries = []
        for _ in range(total):
            etype = r.u8()
            name = r.pstring()
            r.u8()  # flags; SPEC_FLAG_LINK is never set in shipped data
            size = r.u32()
            offset = r.u32()
            if offset + size > len(data):
                raise SpecError(f"{path}: entry {name!r} points past end of file")
            entries.append(SpecEntry(etype, name, size, offset))
        self.entries: tuple[SpecEntry, ...] = tuple(entries)
        self._first: dict[str, SpecEntry] = {}
        for e in self.entries:
            # spec_directory::find returns the first entry with a matching name.
            self._first.setdefault(e.name, e)

    @classmethod
    def open(cls, path: str | Path) -> SpecFile:
        p = Path(path)
        return cls(p.read_bytes(), str(p))

    def find(self, name: str, etype: int | None = None) -> SpecEntry | None:
        if etype is None:
            return self._first.get(name)
        for e in self.entries:
            if e.name == name and e.type == etype:
                return e
        return None

    def of_type(self, etype: int) -> list[SpecEntry]:
        return [e for e in self.entries if e.type == etype]

    def reader(self, entry: SpecEntry) -> Reader:
        return Reader(self.data, entry.offset)
