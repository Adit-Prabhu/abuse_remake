"""Reader for Abuse level files (``levels/levelNN.spe``).

Ported from historicalsource/abuse@01cce80 abuse/src/level.c:
- maps:        level::level (lines 1286-1345): ``fgmap``/``bgmap`` are u32 width, u32 height,
               then width*height u16 tile values; foreground values keep flag bits 0x4000/0x8000
- options:     level::load_options (2085-2144): ``bg_scroll_rate``, ``area_list.v1``, ``tick_counter``
- objects:     level::load_objects (1005-1240): type names, state names and local-variable names
               are stored per type, then one array per base variable across all objects
- links:       level::load_links (2001-2050): 1-based object numbers; negative targets are players
- lights:      abuse/src/light.c:1243 ``read_lights``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .spec import Reader, SpecFile

RC_C, RC_S, RC_L = 0, 1, 2

# objects.c:47 object_descriptions, in save order, with their storage type.
BASE_VARS: tuple[tuple[str, int], ...] = (
    ("fade_dir", RC_C), ("frame_dir", RC_C), ("direction", RC_C), ("gravity_on", RC_C),
    ("fade_count", RC_C), ("fade_max", RC_C), ("active", RC_C), ("flags", RC_C),
    ("aitype", RC_C), ("xvel", RC_L), ("fxvel", RC_C), ("yvel", RC_L), ("fyvel", RC_C),
    ("xacel", RC_L), ("fxacel", RC_C), ("yacel", RC_L), ("fyacel", RC_C), ("x", RC_L),
    ("fx", RC_C), ("y", RC_L), ("fy", RC_C), ("hp", RC_S), ("mp", RC_S), ("fmp", RC_S),
    ("cur_frame", RC_S), ("aistate", RC_S), ("aistate_time", RC_S), ("targetable", RC_C),
)
# extend.hpp: these simple_object fields are ``schar``; the rest of the RC_C ones are ``uchar``.
SIGNED_CHAR_VARS = frozenset({"fade_dir", "frame_dir", "direction", "active"})
# cur_frame is a ``short`` (simple_object::current_frame).
SIGNED_SHORT_VARS = frozenset({"cur_frame"})


def _signed(v: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (v & (sign - 1)) - (v & sign)


@dataclass
class LevelObject:
    index: int  # 1-based position in the saved object list, as links use it
    type_name: str | None  # None when the saved type no longer exists
    state_name: str
    vars: dict[str, int]
    lvars: dict[str, int]
    links: list[int] = field(default_factory=list)  # object numbers this object holds
    player_links: list[int] = field(default_factory=list)  # links to players (negative numbers)
    light_links: list[int] = field(default_factory=list)  # 1-based light numbers

    @property
    def x(self) -> int:
        return self.vars["x"]

    @property
    def y(self) -> int:
        return self.vars["y"]


@dataclass(frozen=True)
class AreaController:
    x: int
    y: int
    w: int
    h: int
    active: int
    ambient: int
    view_xoff: int
    view_yoff: int
    ambient_speed: int
    view_xoff_speed: int
    view_yoff_speed: int


@dataclass(frozen=True)
class Light:
    type: int
    x: int
    y: int
    xshift: int
    yshift: int
    inner_radius: int
    outer_radius: int


@dataclass
class LevelFile:
    path: str
    first_name: str | None
    fg_width: int
    fg_height: int
    fg: list[int]  # raw values, flags included; use fg_tile() for the tile number
    bg_width: int
    bg_height: int
    bg: list[int]
    bg_scroll: tuple[int, int, int, int]  # xmul, xdiv, ymul, ydiv
    areas: list[AreaController]
    tick_counter: int
    objects: list[LevelObject]
    min_light_level: int
    lights: list[Light]

    def fg_tile(self, x: int, y: int) -> int:
        if 0 <= x < self.fg_width and 0 <= y < self.fg_height:
            return self.fg[x + y * self.fg_width] & 0x3FFF  # level.hpp fgvalue()
        return 0

    def fg_raised(self, x: int, y: int) -> bool:
        return bool(self.fg[x + y * self.fg_width] & 0x4000)  # level.hpp above_tile()

    def bg_tile(self, x: int, y: int) -> int:
        if 0 <= x < self.bg_width and 0 <= y < self.bg_height:
            return self.bg[x + y * self.bg_width]
        return 0

    def objects_of(self, type_name: str) -> list[LevelObject]:
        return [o for o in self.objects if o.type_name == type_name]

    def object(self, number: int) -> LevelObject:
        return self.objects[number - 1]


def _read_map(spec: SpecFile, name: str) -> tuple[int, int, list[int]]:
    e = spec.find(name)
    if e is None:
        raise ValueError(f"{spec.path}: no {name}")
    r = spec.reader(e)
    w = r.u32()
    h = r.u32()
    raw = r.bytes(2 * w * h)
    return w, h, [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def _read_value(r: Reader, rc: int) -> int:
    if rc == RC_C:
        return r.u8()
    if rc == RC_S:
        return r.u16()
    return r.s32()


def load_level(path: str | Path) -> LevelFile:
    spec = SpecFile.open(path)
    first_name = None
    e = spec.find("first name")
    if e is not None:
        first_name = spec.reader(e).pstring()

    fg_w, fg_h, fg = _read_map(spec, "fgmap")
    bg_w, bg_h, bg = _read_map(spec, "bgmap")

    bg_scroll = (1, 8, 1, 8)
    e = spec.find("bg_scroll_rate")
    if e is not None:
        r = spec.reader(e)
        if r.u8() == RC_L:
            bg_scroll = (r.s32(), r.s32(), r.s32(), r.s32())

    areas: list[AreaController] = []
    e = spec.find("area_list.v1")
    if e is not None:
        r = spec.reader(e)
        if r.u8() == RC_L:
            for _ in range(r.s32()):
                areas.append(AreaController(*(r.s32() for _ in range(11))))

    tick_counter = 0
    e = spec.find("tick_counter")
    if e is not None:
        r = spec.reader(e)
        if r.u8() == RC_L:
            tick_counter = r.s32()

    objects = _load_objects(spec)
    _load_links(spec, objects)

    min_light, lights = 0, []
    e = spec.find("lights")
    if e is not None:
        r = spec.reader(e)
        total = r.s32()
        min_light = r.s32()
        for _ in range(total):
            x, y, xs, ys, ir, orad = (r.s32() for _ in range(6))
            ty = r.u8()
            lights.append(Light(ty, x, y, xs, ys, ir, orad))

    return LevelFile(str(path), first_name, fg_w, fg_h, fg, bg_w, bg_h, bg, bg_scroll, areas,
                     tick_counter, objects, min_light, lights)


def _load_objects(spec: SpecFile) -> list[LevelObject]:
    e = spec.find("object_descripitions")  # sic: the original spelling
    if e is None:
        raise ValueError(f"{spec.path}: pre-1995 object format is not supported")
    r = spec.reader(e)
    old_tot = r.u16()
    names_entry = spec.find("describe_names")
    if names_entry is not None:
        r.seek(names_entry.offset)
    type_names = [r.pstring() for _ in range(old_tot)]

    state_names: list[list[str]] = []
    e = spec.find("describe_states")
    r = spec.reader(e)
    for _ in range(old_tot):
        state_names.append([r.pstring() for _ in range(r.u16())])

    lvar_names: list[list[str]] = [[] for _ in range(old_tot)]
    e = spec.find("describe_lvars")
    if e is not None:
        r = spec.reader(e)
        lvar_names = [[r.pstring() for _ in range(r.u16())] for _ in range(old_tot)]

    e = spec.find("object_list")
    if e is None:
        return []
    total = spec.reader(e).u32()

    r = spec.reader(spec.find("type"))
    if r.u8() != RC_S:
        raise ValueError(f"{spec.path}: object type array is not RC_S")
    types = [r.u16() for _ in range(total)]

    states = [0] * total
    e = spec.find("state")
    if e is not None:
        r = spec.reader(e)
        if r.u8() == RC_S:
            states = [r.u16() for _ in range(total)]

    lvars: list[dict[str, int]] = [{} for _ in range(total)]
    e = spec.find("lvars")
    if e is not None:
        r = spec.reader(e)
        for i in range(total):
            count = r.s16()
            names = lvar_names[types[i]] if types[i] < old_tot else []
            for k in range(count):
                if r.u8() != RC_L:
                    raise ValueError(f"{spec.path}: lvar {k} of object {i + 1} is not RC_L")
                v = r.s32()
                if k < len(names):
                    lvars[i][names[k]] = v

    base: list[dict[str, int]] = [{} for _ in range(total)]
    for vname, rc in BASE_VARS:
        e = spec.find(vname)
        if e is None:
            continue
        r = spec.reader(e)
        if r.u8() != rc:
            continue  # "Warning : load level -> var '%s' size changed"
        for i in range(total):
            v = _read_value(r, rc)
            if vname in SIGNED_CHAR_VARS:
                v = _signed(v, 8)
            elif vname in SIGNED_SHORT_VARS:
                v = _signed(v, 16)
            base[i][vname] = v

    objects = []
    for i in range(total):
        t = types[i]
        tname = type_names[t] if t < old_tot else None
        snames = state_names[t] if t < old_tot else []
        sname = snames[states[i]] if states[i] < len(snames) else "stopped"
        objects.append(LevelObject(i + 1, tname, sname, base[i], lvars[i]))
    return objects


def _load_links(spec: SpecFile, objects: list[LevelObject]) -> None:
    e = spec.find("object_links")
    if e is not None:
        r = spec.reader(e)
        if r.u8() == RC_L:
            for _ in range(r.s32()):
                x1 = r.s32()
                x2 = r.s32()
                if not 1 <= x1 <= len(objects):
                    continue  # "bad object link"
                if x2 > 0:
                    objects[x1 - 1].links.append(x2)
                else:
                    objects[x1 - 1].player_links.append(-x2)
    e = spec.find("light_links")
    if e is not None:
        r = spec.reader(e)
        if r.u8() == RC_L:
            for _ in range(r.s32()):
                x1 = r.s32()
                x2 = r.s32()
                if 1 <= x1 <= len(objects):
                    objects[x1 - 1].light_links.append(x2)
