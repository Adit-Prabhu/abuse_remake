"""File-format readers against hand-built bytes and the vendored original data."""

import collections
import struct

import pytest

from abuse_remake.formats.cli import verify
from abuse_remake.formats.images import Boundary, Figure, PointList
from abuse_remake.formats.level_file import load_level
from abuse_remake.formats.spec import SPEC_CHARACTER2, SPEC_IMAGE, SpecError, SpecFile
from abuse_remake.formats.tiles import load_palette, load_tiles
from abuse_remake.paths import data_root, level_path


def make_spec(entries):
    """Build SPEC1.0 bytes from (type, name, payload) triples."""
    header = bytearray(b"SPEC1.0\0" + struct.pack("<H", len(entries)))
    dir_size = sum(1 + 1 + len(name) + 1 + 1 + 8 for _, name, _ in entries)
    offset = len(header) + dir_size
    body = bytearray()
    for etype, name, payload in entries:
        raw = name.encode() + b"\0"
        header += bytes([etype, len(raw)]) + raw + b"\0" + struct.pack("<II", len(payload), offset)
        offset += len(payload)
        body += payload
    return bytes(header + body)


def test_spec_directory_reads_hand_built_file():
    spec = SpecFile(make_spec([(SPEC_IMAGE, "a", b"\x01\x00\x01\x00\x07"), (SPEC_IMAGE, "a", b"x")]))
    assert [e.name for e in spec.entries] == ["a", "a"]
    first = spec.find("a")
    assert first.size == 5  # spec_directory::find returns the first match
    assert spec.data[first.offset + 4] == 7


def test_spec_rejects_bad_signature_and_truncated_entry():
    with pytest.raises(SpecError):
        SpecFile(b"NOTSPEC\0\0\0")
    good = bytearray(make_spec([(SPEC_IMAGE, "a", b"12345")]))
    with pytest.raises(SpecError):
        SpecFile(bytes(good[:-2]))


def test_square_boundary_inside_flags_match_hand_trace():
    # Traced by hand through abuse/src/items.c:8 (forward) and :87 (flipped copy).
    square = PointList(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
    assert Boundary.from_points(square).inside == (0, 0, 1, 1)
    assert Boundary.from_points(square, flipped=True).inside == (0, 1, 1, 0)


def test_boundary_requires_closed_polygon():
    with pytest.raises(ValueError):
        Boundary.from_points(PointList(((0, 0), (5, 0), (5, 5))))


def test_vendored_data_matches_checksums():
    assert verify(data_root()) == []


def test_palette_is_256_eight_bit_colours():
    pal = load_palette(data_root())
    assert len(pal.colors) == 256
    assert pal.colors[0] == (0, 0, 0)
    assert max(max(c) for c in pal.colors) > 63  # 8-bit values, not 6-bit VGA DAC values


def test_level01_layout_and_objects():
    lv = load_level(level_path("level01"))
    assert (lv.fg_width, lv.fg_height) == (100, 120)
    assert (lv.bg_width, lv.bg_height) == (33, 38)
    assert len(lv.objects) == 317
    counts = collections.Counter(o.type_name for o in lv.objects)
    # The object census that defines the Level 1 scope (SCOPE.md).
    assert counts["ANT_ROOF"] == 19
    assert counts["HIDDEN_ANT"] == 13
    assert counts["ANT_CRACK"] == 10
    assert counts["SPRAY_GUN"] == 16
    assert counts["BOLDER"] == 5
    assert counts["HEALTH"] == 22
    assert counts["START"] == 1 and counts["NEXT_LEVEL"] == 1
    assert None not in counts  # every saved type name is known
    start = lv.objects_of("START")[0]
    assert (start.x, start.y) == (167, 43)
    exit_ = lv.objects_of("NEXT_LEVEL")[0]
    assert (exit_.x, exit_.y) == (2715, 306)
    assert sum(len(o.links) for o in lv.objects) == 426
    assert all(1 <= n <= len(lv.objects) for o in lv.objects for n in o.links)
    assert len(lv.lights) == 95 and len(lv.areas) == 7


def test_level01_tiles_all_resolve():
    lv = load_level(level_path("level01"))
    tiles = load_tiles(data_root())
    fg = {lv.fg_tile(x, y) for x in range(lv.fg_width) for y in range(lv.fg_height)}
    bg = {lv.bg_tile(x, y) for x in range(lv.bg_width) for y in range(lv.bg_height)}
    assert fg <= set(tiles.fore) | {0}
    assert bg <= set(tiles.back)
    for n in fg - {0}:
        b = tiles.fore[n].boundary
        assert b.tot == 0 or b.points[0] == b.points[-1]


def test_player_frames_parse_with_hit_and_damage_data():
    spec = SpecFile.open(data_root() / "art" / "cop.spe")
    names = {e.name for e in spec.of_type(SPEC_CHARACTER2)}
    # people.lsp DARNEL: (running (seq "4wlk" 1 10)) expands to 4wlk0001.pcx ... 4wlk0010.pcx
    assert {f"4wlk{i:04d}.pcx" for i in range(1, 11)} <= names
    fig = Figure.read(spec.reader(spec.find("4wlk0001.pcx")), SPEC_CHARACTER2)
    assert 0 < fig.xcfg < fig.width
    assert fig.f_damage.tot >= 4
    assert fig.f_damage.points[0] == fig.f_damage.points[-1]
