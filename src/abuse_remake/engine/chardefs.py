"""Character types read from the original ``def_char`` forms.

The original defines every object type in Lisp with ``def_char``. ``character_type::
character_type`` (abuse/src/chars.c) reads these fields: ``abilities``, ``funs``, ``flags``,
``range``, ``draw_range``, ``states``, ``vars``, ``fields`` and ``logo``. We read the same forms
from ``data/original/lisp``, in the load order of ``abuse.lsp``, so every animation, ability,
flag and range comes straight from the source and is cited by file and line.

Six definition-generating helpers (``make_ammo_icon``, ``make_top_char``, ``def_explo``,
``make_hidden_wall_char``, ``make_smart_plat``, ``make_dead_part``) build ``def_char`` forms at
run time. They are expanded here exactly as their Lisp bodies do; each expansion cites the
helper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from ..formats.images import Figure
from ..formats.lisp_reader import Symbol, head, read_forms
from ..formats.spec import SPEC_CHARACTER, SPEC_CHARACTER2, SpecFile
from ..paths import data_root

# abuse/data abuse.lsp load order (data/original/abuse.lsp).
LISP_LOAD_ORDER = (
    "common", "userfuns", "options", "startup", "input", "sfx", "gates", "duong", "ant",
    "people", "weapons", "explo", "platform", "guns", "jugger", "flyer", "teleport", "general",
    "powerup", "doors", "light", "ladder", "switch",
)

# ability.hpp order and ability.c abil_def defaults.
ABILITY_NAMES = ("start_hp", "start_accel", "stop_accel", "jump_xvel", "jump_yvel",
                 "run_top_speed", "jump_top_speed", "tint_color", "push_xrange", "walk_top_speed")
ABILITY_DEFAULTS = dict(zip(ABILITY_NAMES, (6, 3, 4, 2, -16, 10, 6, 0, 0, 6), strict=True))

# chars.hpp cflag_names / ofun_names
CFLAG_NAMES = ("hurt_all", "is_weapon", "stoppable", "can_block", "hurtable", "pushable",
               "unlistable", "add_front", "cached_in", "need_cache_in", "unactive_shield")
OFUN_NAMES = ("ai_fun", "move_fun", "draw_fun", "map_draw_fun", "damage_fun", "next_state_fun",
              "user_fun", "constructor", "reload_fun", "get_cache_list_fun", "type_change_fun")

# chars.hpp enum character_state: the built-in states, in number order.
BUILTIN_STATES = ("dead", "dieing", "stopped", "start_run_jump", "run_jump", "run_jump_fall",
                  "end_run_jump", "flinch_up", "flinch_down", "morph_pose", "running")


class CharDefError(ValueError):
    pass


@dataclass
class CharDef:
    name: str
    index: int
    source: tuple[str, int]
    state_file: str | None = None
    states: dict[str, tuple] = field(default_factory=dict)  # state -> ((file, frame name), ...)
    abilities: dict[str, int] = field(default_factory=lambda: dict(ABILITY_DEFAULTS))
    cflags: frozenset[str] = frozenset()
    funs: dict[str, str] = field(default_factory=dict)
    vars: tuple[str, ...] = ()
    rangex: int = 0
    rangey: int = 0
    draw_rangex: int = 0
    draw_rangey: int = 0


def _num(v, env):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, Symbol) and v in env:
        return env[v]
    raise CharDefError(f"expected a number, got {v!r}")


def _seq(base: str, first: int, last: int) -> list[str]:
    # clisp.c:1014-1040: names are base%04d.pcx, counting from first toward last.
    step = 1 if last >= first else -1
    return [f"{base}{i:04d}.pcx" for i in range(first, last + step, step)]


def _frames(spec, env) -> list:
    """Evaluate a state's picture list the way the Lisp would (seq, rep, app, quote, list)."""
    if isinstance(spec, str) and not isinstance(spec, Symbol):
        return [spec]
    h = head(spec)
    if h == "seq":
        return _seq(_text(spec[1], env), _num(spec[2], env), _num(spec[3], env))
    if h == "rep":
        return _frames(spec[1], env) * _num(spec[2], env)
    if h in ("app", "list"):
        out = []
        for part in spec[1:]:
            out.extend(_frames(part, env))
        return out
    if h == "quote":
        inner = spec[1]
        if isinstance(inner, list):
            return [x for x in inner]
        return [inner]
    if isinstance(spec, Symbol) and spec in env:
        return _frames(env[spec], env)
    raise CharDefError(f"unsupported picture list {spec!r}")


def _text(v, env) -> str:
    if isinstance(v, Symbol):
        if v in env:
            return env[v]
        raise CharDefError(f"unbound symbol {v}")
    return v


def build_chardef(name: str, fields: list, index: int, source: tuple[str, int], env=None) -> CharDef:
    env = env or {}
    cd = CharDef(name, index, source)
    flags = set()
    for f in fields:
        key = head(f)
        if key == "abilities":
            for pair in f[1:]:
                if str(pair[0]) in ABILITY_DEFAULTS:  # unknown names (e.g. hamper_xrange) are ignored
                    cd.abilities[str(pair[0])] = _num(pair[1], env)
        elif key == "funs":
            for pair in f[1:]:
                if str(pair[0]) in OFUN_NAMES and len(pair) > 1 and pair[1] is not None:
                    cd.funs[str(pair[0])] = str(_text(pair[1], env) if isinstance(pair[1], Symbol)
                                                and pair[1] in env else pair[1])
        elif key == "flags":
            for pair in f[1:]:
                if str(pair[0]) in CFLAG_NAMES and pair[1] not in (None, 0):
                    flags.add(str(pair[0]))
        elif key == "range":
            cd.rangex, cd.rangey = _num(f[1], env), _num(f[2], env)
        elif key == "draw_range":
            cd.draw_rangex, cd.draw_rangey = _num(f[1], env), _num(f[2], env)
        elif key == "vars":
            cd.vars = tuple(str(v) for v in f[1:])
        elif key == "states":
            cd.state_file = _text(f[1], env)
            for st in f[2:]:
                frames = _frames(st[1], env)
                cd.states[str(st[0])] = tuple(
                    (fr[0], fr[1]) if isinstance(fr, list) else (cd.state_file, fr) for fr in frames)
        elif key in ("fields", "logo"):
            pass  # editor names and the status-bar logo do not affect play
        else:
            raise CharDefError(f"{name}: unknown def_char field {f!r}")
    cd.cflags = frozenset(flags)
    if "stopped" not in cd.states:
        raise CharDefError(f"{name}: no stopped state (chars.c requires one)")
    return cd


def _expand_macro(form, env) -> tuple[str, list, dict] | None:
    """Expand the definition helpers; returns (name, def_char fields, env)."""
    h = head(form)

    def sym(v):
        return str(v[1]) if isinstance(v, list) and head(v) == "quote" else str(v)

    if h == "make_ammo_icon":  # weapons.lsp:268-276
        name, icon, inc = sym(form[1]), form[2], form[3]
        return name, [
            [Symbol("funs"), [Symbol("ai_fun"), Symbol("weapon_icon_ai")],
             [Symbol("get_cache_list_fun"), Symbol("ammo_cache")], [Symbol("draw_fun"), Symbol("on_draw")]],
            [Symbol("range"), 5, 5],
            [Symbol("flags"), [Symbol("add_front"), True]],
            [Symbol("abilities"), [Symbol("start_hp"), inc]],
            [Symbol("states"), "art/chars/ammo.spe", [Symbol("stopped"), icon]],
        ], env
    if h == "make_top_char":  # people.lsp:850-862
        name, base, ufun, dfun = sym(form[1]), form[2], sym(form[3]), sym(form[4])
        return name, [
            [Symbol("funs"), [Symbol("ai_fun"), Symbol("top_ai")],
             [Symbol("get_cache_list_fun"), Symbol("top_cache")],
             [Symbol("draw_fun"), Symbol(dfun)], [Symbol("user_fun"), Symbol(ufun)]],
            [Symbol("flags"), [Symbol("add_front"), True], [Symbol("is_weapon"), True],
             [Symbol("unlistable"), True]],
            [Symbol("vars"), Symbol("point_angle"), Symbol("fire_delay1"), Symbol("just_fired")],
            [Symbol("states"), "art/coptop.spe", [Symbol("stopped"), [Symbol("seq"), base, 1, 24]]],
        ], env
    if h == "def_explo":  # explo.lsp:70-77
        name, file, seq_name, last = sym(form[1]), form[2], form[3], form[4]
        return name, [
            [Symbol("funs"), [Symbol("ai_fun"), Symbol("exp_ai")], [Symbol("draw_fun"), Symbol("exp_draw")]],
            [Symbol("range"), 10000, 10000],
            [Symbol("flags"), [Symbol("add_front"), True], [Symbol("unlistable"), True]],
            [Symbol("states"), file, [Symbol("stopped"), [Symbol("seq"), seq_name, 1, last]]],
        ], env
    if h == "make_hidden_wall_char":  # doors.lsp:168-180
        name, start, end, ai = sym(form[1]), form[2], form[3], sym(form[4])
        return name, [
            [Symbol("funs"), [Symbol("ai_fun"), Symbol(ai)], [Symbol("reload_fun"), Symbol("hwall_reload")],
             [Symbol("damage_fun"), Symbol("hwall_damage")]],
            [Symbol("abilities"), [Symbol("start_hp"), 25]],
            [Symbol("draw_range"), 80, 80],
            [Symbol("flags"), [Symbol("can_block"), True], [Symbol("unactive_shield"), True],
             [Symbol("hurtable"), True]],
            [Symbol("states"), "art/chars/sect.spe",
             [Symbol("stopped"), [Symbol("seq"), "sect", start, end]]],
        ], env
    if h == "make_smart_plat":  # platform.lsp:6-20
        name, off, on, snap = sym(form[1]), form[2], form[3], form[4]
        return name, [
            [Symbol("flags"), [Symbol("can_block"), True]],
            [Symbol("abilities"), [Symbol("start_accel"), snap]],
            [Symbol("funs"), [Symbol("ai_fun"), Symbol("platform_ai")],
             [Symbol("constructor"), Symbol("platform_cons")]],
            [Symbol("range"), 50, 500],
            [Symbol("draw_range"), 30, 60],
            [Symbol("states"), "art/chars/platform.spe", [Symbol("stopped"), off],
             [Symbol("running"), [Symbol("list"), off, on]]],
        ], env
    return None


# make_dead_part (ant.lsp:600-608) is applied by a (do ...) loop to each entry of a parts array:
# ant_dead_parts (ant.lsp:584, loop at :611) and cop_dead_parts (people.lsp:27, loop at :35).
# Each part is (seq base 1 frames) from the loop's file, drawn with the loop's draw function.
def _find(form, pred):
    if pred(form):
        return form
    if isinstance(form, list):
        for sub in form:
            hit = _find(sub, pred)
            if hit is not None:
                return hit
    return None


def _dead_parts(forms) -> list[tuple[str, list, tuple[str, int]]]:
    arrays = {}
    for loc in forms:
        f = loc.form
        if head(f) == "setq" and isinstance(f[1], Symbol) and str(f[1]).endswith("_dead_parts"):
            arrays[str(f[1])] = [(str(p[0]), p[1]) for p in f[2][-1][1]]
    out = []
    for loc in forms:
        call = _find(loc.form, lambda x: head(x) == "make_dead_part") if head(loc.form) == "do" else None
        if call is None:
            continue
        array = str(_find(call[1], lambda x: head(x) == "aref")[1])
        frames, filename, draw = call[3], call[4], str(call[5][1])
        for sym, part_base in arrays[array]:
            out.append((sym, [
                [Symbol("range"), 100, 100],
                [Symbol("funs"), [Symbol("ai_fun"), Symbol("head_ai")], [Symbol("draw_fun"), Symbol(draw)]],
                [Symbol("flags"), [Symbol("unlistable"), True], [Symbol("add_front"), True]],
                [Symbol("states"), filename, [Symbol("stopped"), [Symbol("seq"), part_base, 1, frames]]],
            ], (loc.path, loc.line)))
    return out


@cache
def load_chardefs(root: str | None = None) -> dict[str, CharDef]:
    base = Path(root) if root else data_root()
    defs: dict[str, CharDef] = {}

    def add(name, fields, source, env=None):
        if name in defs:  # a redefinition keeps its new index in the original (chars.c)
            raise CharDefError(f"{name} defined twice ({defs[name].source} and {source})")
        defs[name] = build_chardef(name, fields, len(defs), source, env)

    for stem in LISP_LOAD_ORDER:
        path = base / "lisp" / f"{stem}.lsp"
        rel = f"data/original/lisp/{stem}.lsp"
        forms = read_forms(path.read_text(encoding="latin-1"), rel)
        for loc in forms:
            f = loc.form
            if head(f) == "def_char":
                add(str(f[1]), f[2:], (rel, loc.line))
                continue
            expanded = _expand_macro(f, {})
            if expanded:
                name, fields, env = expanded
                add(name, fields, (rel, loc.line), env)
        for sym, part_fields, source in _dead_parts(forms):
            add(sym, part_fields, source)
    return defs


class FrameStore:
    """Loads and caches the Figure for each (file, frame name)."""

    def __init__(self, root: Path | None = None):
        self.root = root or data_root()
        self._specs: dict[str, SpecFile] = {}
        self._figs: dict[tuple[str, str], Figure] = {}

    def figure(self, file: str, name: str) -> Figure:
        key = (file, name)
        fig = self._figs.get(key)
        if fig is None:
            spec = self._specs.get(file)
            if spec is None:
                spec = self._specs[file] = SpecFile.open(self.root / file)
            e = spec.find(name, SPEC_CHARACTER2) or spec.find(name, SPEC_CHARACTER)
            if e is None:
                raise CharDefError(f"{file}: no frame {name!r}")
            fig = self._figs[key] = Figure.read(spec.reader(e), e.type)
        return fig
