"""File-format readers against hand-built bytes and the vendored original data."""

import collections
import struct

import pytest

from abuse_remake.formats.cli import verify
from abuse_remake.formats.images import Boundary, Figure, PointList
from abuse_remake.formats.level_file import load_level
from abuse_remake.formats.spec import (
    SPEC_BACKTILE,
    SPEC_CHARACTER2,
    SPEC_DATA_ARRAY,
    SPEC_FORETILE,
    SPEC_GRUE_BGMAP,
    SPEC_GRUE_FGMAP,
    SPEC_IMAGE,
    SpecError,
    SpecFile,
)
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


def test_boundary_inside_flags_match_hand_traces():
    # Traced by hand through abuse/src/items.c:8 (forward) and :100 (flipped copy), and
    # confirmed by the compiled original in tests/test_c_reference.py.
    square = PointList(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
    assert Boundary.from_points(square).inside == (0, 0, 1, 1)
    assert Boundary.from_points(square, flipped=True).inside == (0, 1, 1, 0)
    # A diagonal segment takes the check_down + check_left branch (items.c:44-50).
    triangle = PointList(((0, 0), (10, 10), (0, 10), (0, 0)))
    assert Boundary.from_points(triangle).inside == (0, 1, 1)
    assert Boundary.from_points(triangle, flipped=True).inside == (0, 1, 1)


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


def pstr(text):
    raw = text.encode() + b"\0"
    return bytes([len(raw)]) + raw


def tile_payload(w, h, fore=True):
    body = struct.pack("<HH", w, h) + bytes(w * h)
    if fore:
        body += struct.pack("<H", 0) + b"\0" + bytes([5, 0, 0, 29, 0, 29, 14, 0, 14, 0, 0])
    else:
        body += struct.pack("<H", 0)
    return body


def test_later_tile_file_redefines_a_tile_number(tmp_path):
    (tmp_path / "a.spe").write_bytes(make_spec([(SPEC_FORETILE, "7", tile_payload(30, 15)),
                                               (SPEC_BACKTILE, "0", tile_payload(60, 30, False))]))
    (tmp_path / "b.spe").write_bytes(make_spec([(SPEC_FORETILE, "7", tile_payload(30, 18)),
                                               (SPEC_FORETILE, "0", tile_payload(30, 15))]))
    ts = load_tiles(tmp_path, ("a.spe", "b.spe", "missing.spe"))
    assert ts.fore[7].image.height == 18 and ts.fore[7].source == "b.spe"  # last file wins
    assert ts.redefined == [("fore", 7, "b.spe")]
    assert ts.grid_sizes() == ((30, 15), (60, 30))


def build_level(tmp_path):
    """A hand-built level exercising the loader's signedness and fix-up rules."""
    def arr(rc, fmt, values):
        return bytes([rc]) + b"".join(struct.pack(fmt, v) for v in values)

    fg = struct.pack("<II", 2, 1) + struct.pack("<HH", 0x8000 | 3, 0x4000 | 2)
    bg = struct.pack("<II", 1, 1) + struct.pack("<H", 0)
    entries = [
        (SPEC_GRUE_FGMAP, "fgmap", fg),
        (SPEC_GRUE_BGMAP, "bgmap", bg),
        (SPEC_DATA_ARRAY, "object_descripitions", struct.pack("<H", 2)),
        (SPEC_DATA_ARRAY, "describe_names", pstr("A") + pstr("B")),
        (SPEC_DATA_ARRAY, "describe_states",
         struct.pack("<H", 1) + pstr("stopped") + struct.pack("<H", 2) + pstr("stopped") + pstr("running")),
        (SPEC_DATA_ARRAY, "describe_lvars", struct.pack("<H", 1) + pstr("foo") + struct.pack("<H", 0)),
        (SPEC_DATA_ARRAY, "object_list", struct.pack("<I", 3)),
        (SPEC_DATA_ARRAY, "type", arr(1, "<H", [0, 1, 1])),
        (SPEC_DATA_ARRAY, "state", arr(1, "<H", [0, 1, 0])),
        (SPEC_DATA_ARRAY, "lvars", struct.pack("<h", 1) + bytes([2]) + struct.pack("<i", 42)
         + struct.pack("<h", 0) + struct.pack("<h", 0)),
        (SPEC_DATA_ARRAY, "x", arr(2, "<i", [5, -3, 7])),
        (SPEC_DATA_ARRAY, "y", arr(2, "<i", [1, 2, 3])),
        (SPEC_DATA_ARRAY, "direction", arr(0, "<B", [255, 1, 1])),
        (SPEC_DATA_ARRAY, "cur_frame", arr(1, "<H", [0xFFFF, 0, 1])),
        (SPEC_DATA_ARRAY, "hp", arr(0, "<B", [9, 9, 9])),  # wrong type byte: C skips the var
        (SPEC_DATA_ARRAY, "object_links", bytes([2]) + struct.pack("<i", 3)
         + struct.pack("<ii", 1, 2) + struct.pack("<ii", 1, 0) + struct.pack("<ii", 2, -1)),
        (SPEC_DATA_ARRAY, "light_links", bytes([2]) + struct.pack("<i", 1) + struct.pack("<ii", 3, 1)),
        (SPEC_DATA_ARRAY, "area_list.v1", bytes([2]) + struct.pack("<i", 1)
         + struct.pack("<11i", 10, 20, 30, 40, 0, -1, -1, -30, 2, 4, 4)),
        (SPEC_DATA_ARRAY, "lights", struct.pack("<ii", 1, 70000)
         + struct.pack("<6i", 100, 200, 0, 1, 1, 50) + bytes([8])),
    ]
    path = tmp_path / "tiny.spe"
    path.write_bytes(make_spec(entries))
    return path


def test_hand_built_level_follows_loader_rules(tmp_path):
    lv = load_level(build_level(tmp_path), foretiles={0, 2})
    assert lv.fg == [0, 0x4000 | 2]  # 0x8000 cleared (no player_info), missing tile 3 zeroed
    assert lv.fg_raised(1, 0) and not lv.fg_raised(5, 5)
    a, b1, b2 = lv.objects
    assert (a.type_name, a.state_name, b1.state_name) == ("A", "stopped", "running")
    assert a.vars["direction"] == -1 and a.vars["cur_frame"] == -1  # schar / short
    assert a.lvars == {"foo": 42}
    assert "hp" not in a.vars  # type byte mismatch: the variable is skipped
    assert b1.removed_on_load and not a.removed_on_load  # negative x is deleted on load
    assert [o.index for o in lv.live_objects()] == [1, 3]
    assert a.links == [2]  # the link to 0 resolves to NULL and is ignored
    assert b1.player_links == [1]
    assert b2.light_links == [1]
    area = lv.areas[0]
    assert (area.ambient, area.view_yoff) == (-1, -30)
    assert lv.min_light_level == 70000 & 0xFFFF  # ushort
    assert lv.lights[0].type == 8 and lv.lights[0].outer_radius == 50


def test_level_without_describe_states_loads_no_objects(tmp_path):
    raw = build_level(tmp_path).read_bytes()
    spec = SpecFile(raw)
    kept = [(e.type, e.name, raw[e.offset:e.offset + e.size]) for e in spec.entries
            if e.name != "describe_states"]
    path = tmp_path / "nostates.spe"
    path.write_bytes(make_spec(kept))
    assert load_level(path).objects == []  # level.c:1042 returns before creating objects


def test_level01_signed_fields_and_link_extras():
    lv = load_level(level_path("level01"))
    assert sum(1 for o in lv.objects if o.vars["direction"] == -1) == 20
    assert lv.areas[0].ambient == -1 and lv.areas[0].view_yoff == -30
    light_links = [n for o in lv.objects for n in o.light_links]
    assert len(light_links) == 3 and all(1 <= n <= len(lv.lights) for n in light_links)
    assert not any(o.removed_on_load for o in lv.objects)
    assert not lv.has_player_info and not any(v & 0x8000 for v in lv.fg)
