"""The level: map, object list, active set, collisions and the per-tick loop.

Port of historicalsource/abuse@01cce80:
- level::tick, add_actives, pull_actives, unactivate_all: abuse/src/level.c:162-242, 596-760
- game::step (active area = view +/- a quarter of its size): abuse/src/game.c:1980-2000
- boundary_setback, all_boundary_setback: level.c:461-563
- check_collisions: abuse/src/collide.c
- hurt_radius, find_*, crush, platform_push, push_characters, send_signal: level.c:2742-3020
- object list order (add_front appends): level.c:2385-2418; removal: level.c:2460-2526
- start of play (START, insert_players, reload_fun): level.c:1404-1421, 3068-3088
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..formats.images import Figure
from ..formats.level_file import LevelFile
from ..formats.tiles import TileSet
from .chardefs import CharDef, FrameStore, load_chardefs
from .cmath import JRand, cdiv, lisp_atan2
from .geometry import TileMap, setback_intersect
from .obj import GameObject

MAX_HP = 200  # clisp.c:137-138 (max_hp symbol)
DIFFICULTIES = ("easy", "medium", "hard", "extreme")
DEFAULT_DIFFICULTY = "hard"  # abuse/hardness.lsp; startup.lsp falls back to 'hard as well


@dataclass
class CharType:
    name: str
    index: int
    cflags: frozenset[str]
    abilities: dict[str, int]
    vars: tuple[str, ...]
    rangex: int
    rangey: int
    draw_rangex: int
    draw_rangey: int
    sequences: dict[str, tuple[Figure, ...]]
    frame_names: dict[str, tuple[tuple[str, str], ...]]
    fun_names: dict[str, str]
    source: tuple[str, int]
    ai_fun: Callable | None = None
    move_fun: Callable | None = None
    damage_fun: Callable | None = None
    constructor: Callable | None = None
    user_fun: Callable | None = None
    next_state_fun: Callable | None = None
    reload_fun: Callable | None = None
    type_change_fun: Callable | None = None


@dataclass
class LightSource:
    """light.hpp light_source; rendering reads these, Lisp moves and resizes them."""

    type: int
    x: int
    y: int
    inner_radius: int
    outer_radius: int
    xshift: int
    yshift: int
    known: bool = False


@dataclass
class Event:
    kind: str  # "sound", "panim", "message", "damage", "pickup", "death", "spawn", ...
    data: dict[str, Any] = field(default_factory=dict)


class World:
    def __init__(self, level: LevelFile, tiles: TileSet, registry: dict[str, Callable],
                 seed: int = 0, difficulty: str = DEFAULT_DIFFICULTY, frames: FrameStore | None = None,
                 strict: bool = True):
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
        self.level = level
        self.difficulty = difficulty
        self.registry = registry
        self.rng = JRand(seed)
        self.max_hp = MAX_HP
        self.tick_counter = level.tick_counter
        self._uid = 0
        self.frames = frames or FrameStore()
        self.events: list[Event] = []
        self.globals: dict[str, Any] = {}  # Lisp global variables the behaviours share
        self.types: dict[str, CharType] = {}
        self._types_by_index: list[CharType] = []
        for cd in load_chardefs().values():
            self._add_type(cd, strict=False)
        fore_bounds = {n: t.boundary for n, t in tiles.fore.items()}
        cells = [v & 0x3FFF for v in level.fg]
        self.tiles = TileMap(level.fg_width, level.fg_height, cells, fore_bounds)
        self.bg_map = list(level.bg)
        self.bg_scroll = level.bg_scroll
        self.areas = list(level.areas)
        self.min_light_level = level.min_light_level
        self.lights = [LightSource(lt.type, lt.x, lt.y, lt.inner_radius, lt.outer_radius,
                                   lt.xshift, lt.yshift) for lt in level.lights]
        self.objects: list[GameObject] = []
        self.active: list[GameObject] = []
        self.block_list: list[GameObject] = []
        self.all_block_list: list[GameObject] = []
        self.views: list = []
        self.weapon_types = [t for t in self._types_by_index if "is_weapon" in t.cflags]
        self.strict = strict
        self._load_objects()

    # --- types ---
    def _add_type(self, cd: CharDef, strict: bool) -> None:
        seqs = {st: tuple(self.frames.figure(f, n) for f, n in frames) for st, frames in cd.states.items()}
        ct = CharType(cd.name, cd.index, cd.cflags, dict(cd.abilities), cd.vars, cd.rangex, cd.rangey,
                      cd.draw_rangex, cd.draw_rangey, seqs, dict(cd.states), dict(cd.funs), cd.source)
        for slot in ("ai_fun", "move_fun", "damage_fun", "constructor", "user_fun",
                     "next_state_fun", "reload_fun", "type_change_fun"):
            name = cd.funs.get(slot)
            if name is not None:
                setattr(ct, slot, self.registry.get(name))
        self.types[cd.name] = ct
        self._types_by_index.append(ct)

    def missing_behaviours(self, type_name: str) -> list[str]:
        """Lisp functions a type names that no Python port provides (draw functions excluded)."""
        ct = self.types[type_name]
        return [f"{slot}={name}" for slot, name in ct.fun_names.items()
                if slot not in ("draw_fun", "map_draw_fun", "get_cache_list_fun")
                and name not in self.registry]

    def type_index(self, name: str) -> int:
        return self.types[name].index

    def next_uid(self) -> int:
        self._uid += 1
        return self._uid

    # --- level load (level.c:1005-1240, 1393-1421) ---
    def _load_objects(self) -> None:
        by_number: dict[int, GameObject] = {}
        for lo in self.level.live_objects():
            ct = self.types[lo.type_name]
            o = GameObject(self, ct)
            o.level_index = lo.index
            v = lo.vars
            o.fade_dir = v.get("fade_dir", 0)
            o.frame_dir = v.get("frame_dir", 1)
            o.direction = v.get("direction", 1)
            o.set_gravity(v.get("gravity_on", 1))
            o.set_fade_count(v.get("fade_count", 0))
            o.fade_max = v.get("fade_max", 16)
            o.active = v.get("active", 0)
            o.set_flags(v.get("flags", 0))
            o.set_aitype(v.get("aitype", 0))
            o.xvel, o.yvel = v.get("xvel", 0), v.get("yvel", 0)
            o.xacel, o.yacel = v.get("xacel", 0), v.get("yacel", 0)
            o.set_fxvel(v.get("fxvel", 0))
            o.set_fyvel(v.get("fyvel", 0))
            o.set_fxacel(v.get("fxacel", 0))
            o.set_fyacel(v.get("fyacel", 0))
            o.x, o.y = v.get("x", 0), v.get("y", 0)
            o.last_x, o.last_y = o.x, o.y
            o.set_fx(v.get("fx", 0))
            o.set_fy(v.get("fy", 0))
            o.set_hp(v.get("hp", 0))
            o.mp, o.fmp = v.get("mp", 0), v.get("fmp", 0)
            o.set_aistate(v.get("aistate", 0))
            o.set_aistate_time(v.get("aistate_time", 0))
            o.targetable_on = v.get("targetable", 1)
            # level.c:1157-1159: a state the type no longer has becomes "stopped"
            o.state = lo.state_name if o.has_sequence(lo.state_name) else "stopped"
            frame = v.get("cur_frame", 0)
            # level.c:1228-1232: a frame number past the sequence end is reset
            o.current_frame = frame if 0 <= frame < o.total_frames() else 0
            for name, value in lo.lvars.items():
                if name in o.lvars:
                    o.lvars[name] = value
            self.objects.append(o)
            by_number[lo.index] = o
        for lo in self.level.live_objects():
            o = by_number[lo.index]
            for n in lo.links:
                target = by_number.get(n)
                if target is not None:
                    o.add_object(target)
            for n in lo.light_links:
                if 1 <= n <= len(self.lights):
                    light = self.lights[n - 1]
                    light.known = True
                    if light not in o.lights:
                        o.lights.append(light)
        if self.strict:
            from ..scope import LEVEL01_TYPES
            missing = {t: self.missing_behaviours(t) for t in LEVEL01_TYPES if t in self.types}
            missing = {t: m for t, m in missing.items() if m}
            if missing:
                raise NotImplementedError(f"behaviours not ported yet: {missing}")
        # level.c:1404-1415: every loaded object gets its reload function
        for o in list(self.objects):
            if o.ctype.reload_fun is not None:
                o.ctype.reload_fun(o)

    # --- object list (level.c:2385-2526) ---
    def create(self, type_name: str, x: int, y: int, aitype: int = 0,
               skip_constructor: bool = False) -> GameObject:
        """``create`` (objects.c:1136): a new object with defaults and its constructor."""
        ct = self.types[type_name]
        o = GameObject(self, ct, 0, 0)
        o.defaults()  # game_object::game_object runs defaults() before create() sets x and y
        o.x, o.y, o.last_x, o.last_y = x, y, x, y
        if aitype:
            o.set_aitype(aitype)
        if ct.constructor is not None and not skip_constructor:
            ct.constructor(o)
        return o

    def add_object(self, o: GameObject) -> None:
        if "add_front" in o.ctype.cflags:
            self.objects.append(o)  # "add_front" objects are drawn last, so they go at the end
        else:
            self.objects.insert(0, o)

    def add_object_after(self, o: GameObject, who: GameObject | None) -> None:
        if who is None or who not in self.objects:
            self.add_object(o)
        else:
            self.objects.insert(self.objects.index(who) + 1, o)

    def spawn(self, type_name: str, x: int, y: int, aitype: int = 0) -> GameObject:
        """Lisp ``(add_object TYPE x y [aitype])``."""
        o = self.create(type_name, x, y, aitype)
        self.add_object(o)
        return o

    def spawn_after(self, type_name: str, x: int, y: int, who: GameObject, aitype: int = 0) -> GameObject:
        """Lisp ``(add_object_after TYPE x y [aitype])``."""
        o = self.create(type_name, x, y, aitype)
        self.add_object_after(o, who)
        return o

    def remove_object(self, who: GameObject) -> None:
        if who not in self.objects:
            return
        self.objects.remove(who)
        if who in self.active:
            self.active.remove(who)  # the rest of this tick skips it (level.c:2484-2492)
        if who.flags & 8:  # KNOWN_FLAG: someone links to it
            for o in self.objects:
                while who in o.objs:
                    o.objs.remove(who)
        if who.can_block():
            self._remove_from(self.block_list, who)
            self._remove_from(self.all_block_list, who)
        elif who.hurtable():
            self._remove_from(self.all_block_list, who)
        who.objs.clear()
        who.lights.clear()
        who.deleted = True

    @staticmethod
    def _remove_from(lst: list, who) -> None:
        while who in lst:
            lst.remove(who)

    def delete_object(self, who: GameObject) -> None:
        self.remove_object(who)

    def to_front(self, o: GameObject) -> None:
        if o in self.objects:
            self.objects.remove(o)
            self.objects.append(o)

    def to_back(self, o: GameObject) -> None:
        if o in self.objects:
            self.objects.remove(o)
            self.objects.insert(0, o)

    # --- lights (light.c) ---
    def add_light(self, ltype, x, y, r1, r2, xs, ys) -> LightSource:
        light = LightSource(ltype, x, y, r1, r2, xs, ys)
        self.lights.append(light)
        return light

    def remove_light(self, light: LightSource) -> None:
        if light.known:
            for o in self.objects:
                while light in o.lights:
                    o.lights.remove(light)
        if light in self.lights:
            self.lights.remove(light)

    # --- active set (game.c:1980-2000, level.c:162-242) ---
    def unactivate_all(self) -> None:
        self.active = []
        self.block_list = []
        self.all_block_list = []
        for o in self.objects:
            o.active = 0

    def _note_block(self, o: GameObject) -> None:
        if o.can_block():
            self.block_list.append(o)
            self.all_block_list.append(o)
        elif o.hurtable():
            self.all_block_list.append(o)

    def add_actives(self, x1: int, y1: int, x2: int, y2: int) -> None:
        for o in self.objects:
            if o.active:
                continue
            xr, yr = o.ctype.rangex, o.ctype.rangey
            if o.x + xr >= x1 and o.x - xr <= x2 and o.y + yr >= y1 and o.y - yr <= y2:
                self._note_block(o)
                o.active = 1
                self.active.append(o)
                # pull_actives: linked objects run right after the object that links them.
                # (The original recurses on o rather than on the linked object, so links of
                # linked objects are not pulled in.)
                for other in reversed(o.objs):
                    if not other.active:
                        other.active = 1
                        self._note_block(other)
                        self.active.append(other)

    def activate_for_views(self) -> None:
        self.unactivate_all()
        for v in self.views:
            if v.focus is not None:
                v.update_scroll()
                w = v.cx2 - v.cx1 + 1
                h = v.cy2 - v.cy1 + 1
                xo, yo = v.xoff(), v.yoff()
                self.add_actives(xo - cdiv(w, 4), yo - cdiv(h, 4), xo + w + cdiv(w, 4), yo + h + cdiv(h, 4))

    # --- the tick (level.c:596-760) ---
    def step(self) -> None:
        """game::step for one 15 Hz frame: inputs must already be on the views."""
        self.events = []
        for v in self.views:
            v.apply_pending_weapon_change()
        self.activate_for_views()
        for v in self.views:
            v.update_scroll()
        attack, targets = [], []
        for o in list(self.active):
            if o.deleted or o not in self.active:
                continue
            o.last_x, o.last_y = o.x, o.y
            o.set_flags(o.flags & (0xFF - 1 - 2))  # clear FLAG_JUST_HIT and FLAG_JUST_BLOCKED
            c = o.controller
            keep = True
            if c is not None:
                area = self._smallest_area(o.x, o.y)
                if area is not None:
                    c.configure_for_area(area)
                o.move(c.x_suggestion, c.y_suggestion,
                       c.b1_suggestion | (c.b2_suggestion << 1) | (c.b3_suggestion << 2))
            else:
                keep = o.decide()
            if not keep:
                self.delete_object(o)
                continue
            if o.deleted:
                continue
            if o.figure().hit.tot:
                attack.append(o)
            if o.hurtable():
                targets.append(o)
        self.check_collisions(attack, targets)
        self.tick_counter = (self.tick_counter + 1) & 0xFFFFFFFF

    def _smallest_area(self, x: int, y: int):
        best, best_size = None, 0xFFFFFFF
        for a in self.areas:
            if a.x <= x <= a.x + a.w and a.y <= y <= a.y + a.h:
                size = a.w * a.h
                if size < best_size:
                    best, best_size = a, size
        return best

    # --- collisions (collide.c, level.c:461-563) ---
    def _setback(self, blist, subject, x1, y1, x2, y2):
        hit = None
        for target in blist:
            if target is subject or target.deleted:
                continue
            if target.objs and target.objs[0] is subject:
                continue
            tx1, ty1, tx2, ty2 = target.picture_space()
            if (x2 < tx1 and x1 < tx1) or (x1 > tx2 and x2 > tx2) or (y1 > ty2 and y2 > ty2) \
                    or (y1 < ty1 and y2 < ty1):
                continue
            fig = target.figure()
            dmg = fig.f_damage if target.direction > 0 else fig.b_damage
            pts, ins = dmg.points, dmg.inside
            for i in range(len(pts) - 1):
                xp1 = target.x + target.tx(pts[i][0])
                yp1 = target.y + target.ty(pts[i][1])
                xp2 = target.x + target.tx(pts[i + 1][0])
                yp2 = target.y + target.ty(pts[i + 1][1])
                did, x2, y2 = setback_intersect(x1, y1, x2, y2, xp1, yp1, xp2, yp2, 1 if ins[i] else -1)
                if did:
                    hit = target
        return hit, x2, y2

    def boundary_setback(self, subject, x1, y1, x2, y2):
        return self._setback(self.block_list, subject, x1, y1, x2, y2)

    def all_boundary_setback(self, subject, x1, y1, x2, y2):
        return self._setback(self.all_block_list, subject, x1, y1, x2, y2)

    def check_collisions(self, attack: list[GameObject], targets: list[GameObject]) -> None:
        for subject in attack:
            if subject.deleted:
                continue
            sx1, sy1, sx2, sy2 = subject.picture_space()
            rec = None
            hitx = hity = 0
            for target in targets:
                if rec is not None:
                    break
                if target.deleted:
                    continue
                tx1, ty1, tx2, ty2 = target.picture_space()
                if sx2 < tx1 or sy2 < ty1 or sx1 > tx2 or sy1 > ty2:
                    continue
                self.try_pushback(subject, target)
                if not subject.can_hurt(target):
                    continue
                s_hit = subject.figure().hit.points
                tfig = target.figure()
                t_damage = (tfig.f_damage if target.direction > 0 else tfig.b_damage).points
                i = len(s_hit) - 1
                si = 0
                while i > 0 and rec is None:
                    j = len(t_damage) - 1
                    ti = 0
                    while j > 0 and rec is None:
                        xp1 = target.x + target.tx(t_damage[ti][0])
                        yp1 = target.y + target.ty(t_damage[ti][1])
                        xp2 = target.x + target.tx(t_damage[ti + 1][0])
                        yp2 = target.y + target.ty(t_damage[ti + 1][1])
                        ti += 1
                        x1 = subject.x + subject.tx(s_hit[si][0])
                        y1 = subject.y + subject.ty(s_hit[si][1])
                        x2 = subject.x + subject.tx(s_hit[si + 1][0])
                        y2 = subject.y + subject.ty(s_hit[si + 1][1])
                        _, nx2, ny2 = setback_intersect(x1, y1, x2, y2, xp1, yp1, xp2, yp2, 0)
                        if nx2 != x2 or ny2 != y2:
                            rec = target
                            hitx = cdiv(cdiv(x1 + nx2, 2) + cdiv(xp1 + xp2, 2), 2)
                            hity = cdiv(cdiv(y1 + y1, 2) + cdiv(yp1 + yp2, 2), 2)  # sic: y1+y1
                        j -= 1
                    si += 1
                    i -= 1
            if rec is not None:
                rec.do_damage(subject.figure().hit_damage, subject, hitx, hity, 0, 0)

    def try_pushback(self, subject: GameObject, target: GameObject) -> None:
        if (subject.pushable() and target.pushable()
                and subject.state not in ("dead", "dieing") and target.state not in ("dead", "dieing")):
            b1 = subject.ability("push_xrange")
            b2 = target.ability("push_xrange")
            if abs(subject.x - target.x) < b1 + b2:
                tmove = b1 + b2 - abs(subject.x - target.x)
                xv = cdiv(tmove, 2) if subject.x > target.x else -cdiv(tmove, 2)
                xv2 = -xv
                _, xv, _ = subject.try_move(subject.x, subject.y, xv, 0, 3)
                subject.x += xv
                _, xv2, _ = target.try_move(target.x, target.y, xv2, 0, 3)
                target.x += xv2

    # --- world queries used by Lisp builtins ---
    def attacker(self, who: GameObject) -> GameObject:
        """level::attacker: the nearest player (Manhattan distance)."""
        best, best_d = None, 0x7FFFFFFF
        for v in self.views:
            if v.focus is not None:
                d = abs(v.focus.x - who.x) + abs(v.focus.y - who.y)
                if d < best_d:
                    best, best_d = v.focus, d
        return best

    def bg(self, who: GameObject) -> GameObject:
        """Lisp ``(bg)``: with one player, simply that player (clisp.c case 4)."""
        if len(self.views) > 1:
            return self.attacker(who)
        return self.views[0].focus

    def hurt_radius(self, x, y, r, m, from_obj, exclude, max_push) -> None:
        if r < 1:
            return
        for o in list(self.active):
            if o is exclude or o.deleted or not o.hurtable():
                continue
            y1 = o.y
            y2 = o.y - o.picture_height()
            cx = abs(o.x - x)
            cy1 = abs(y1 - y)
            cy2 = abs(y2 - y)
            d1 = cx + cy1 - (cx >> 1) if cx < cy1 else cx + cy1 - (cy1 >> 1)
            d2 = cx + cy2 - (cx >> 1) if cx < cy2 else cx + cy2 - (cy2 >> 1)
            if d2 < d1:
                d1 = d2
            if d1 < r:
                px = cdiv((r - cx) * max_push, r)
                py = cdiv((r - cy1) * max_push, r)
                if o.x < x:
                    px = -px
                if o.y < y:
                    py = -py
                o.do_damage(cdiv((r - d1) * m, r), from_obj, x, y1, px, py)

    def find_object_in_area(self, x, y, x1, y1, x2, y2, types: set[int], exclude) -> GameObject | None:
        closest, closest_d = None, 0xFFFFFFF
        for o in self.active:
            if o.deleted:
                continue
            xp1, yp1, xp2, yp2 = o.picture_space()
            if not (xp1 > x2 or xp2 < x1 or yp1 > y2 or yp2 < y1) and o is not exclude:
                if o.ctype.index in types:
                    d = (o.x - x) ** 2 + (o.y - y) ** 2
                    if d < closest_d:
                        closest, closest_d = o, d
        return closest

    def find_object_in_angle(self, x, y, start, end, types: set[int], exclude) -> GameObject | None:
        closest, closest_d = None, 0xFFFFFFF
        for o in self.active:
            if o.deleted:
                continue
            angle = lisp_atan2(o.y - y, o.x - x)
            in_arc = (start <= angle <= end) if start <= end else (angle >= start or angle <= end)
            if (in_arc
                    and o is not exclude and o.ctype.index in types):
                d = (o.x - x) ** 2 + (o.y - y) ** 2
                if d < closest_d:
                    closest, closest_d = o, d
        return closest

    def find_closest(self, x, y, type_index, who) -> GameObject | None:
        best, best_d = None, 100000
        for o in self.active:
            if o.ctype.index == type_index and o is not who and not o.deleted:
                d = (x - o.x) ** 2 + (y - o.y) ** 2
                if d < best_d:
                    best, best_d = o, d
        return best

    def find_xclosest(self, x, y, type_index, who) -> GameObject | None:
        find, fx, fy = None, 0xFFFFFF, 100000
        for o in self.active:
            if o.ctype.index == type_index and o is not who and not o.deleted:
                xd = abs(x - o.x)
                if xd < fx:
                    fx, fy, find = xd, abs(y - o.y), o
                elif xd == fx:
                    yd = abs(y - o.y)
                    if yd < fy:
                        fy, find = yd, o
        return find

    def find_xrange(self, x, y, type_index, xd) -> GameObject | None:
        find, fy = None, 100000
        for o in self.active:
            if o.ctype.index == type_index and not o.deleted:
                if abs(x - o.x) < xd and abs(y - o.y) < fy:
                    fy, find = abs(y - o.y), o
        return find

    def find_type(self, type_name: str, skip: int = 0) -> GameObject | None:
        last = None
        for o in self.objects:
            if o.ctype.name == type_name:
                if not skip:
                    return o
                skip -= 1
                last = o
        return last

    def send_signal(self, signal: int) -> None:
        pass  # game_object::recieve_signal is empty in this engine (objects.hpp)

    def crush(self, by_who, xamount, yamount) -> bool:
        crushed = False
        for o in list(self.active):
            if o.hurtable() and o is not by_who and not o.deleted:
                hit, _, _ = o.try_move(o.x, o.y, -xamount, -yamount, 3)
                if hit is by_who:
                    _, xv, yv = o.try_move(o.x, o.y, xamount, yamount, 3)
                    if xv == 0 and yv == 0:
                        if o.state not in ("dead", "dieing"):
                            o.do_damage(by_who.figure().hit_damage, by_who, o.x, o.y, 0, 0)
                        crushed = True
        return crushed

    def platform_push(self, by_who, xamount, yamount) -> bool:
        failed = False
        for o in list(self.active):
            if o.hurtable() and o.state not in ("dieing", "dead") and not o.deleted:  # is_playable()
                if yamount < 0:
                    hit, tvx, tvy = o.try_move(o.x, o.y, -xamount, -yamount, 1)
                    if hit is by_who:
                        o.x += tvx
                        o.y += tvy
                hit, _, _ = o.try_move(o.x, o.y, 0, 2, 1)
                if hit is by_who:  # standing on the platform
                    by_who.x = -by_who.x
                    _, xv, yv = o.try_move(o.x, o.y, xamount, yamount, 3)
                    if xv != xamount or yv != yamount:
                        failed = True
                    o.x += xv
                    o.y += yv
                    by_who.x = -by_who.x
        return not failed

    def push_characters(self, by_who, xamount, yamount) -> bool:
        failed = False
        for o in list(self.active):
            if (o.hurtable() or o.pushable()) and o.state not in ("dieing", "dead") and not o.deleted:
                xv, yv = -xamount, -yamount
                tvx = xv + 1 if xv > 0 else (xv - 1 if xv < 0 else 0)
                if yv > 0:
                    tvy = yv + 1
                elif yv < 0:
                    tvx = yv - 1  # sic: level.c:2850 assigns tvx here, leaving tvy unset
                    tvy = 0
                else:
                    tvy = 0
                hit, tvx, tvy = o.try_move(o.x + xamount, o.y + yamount, tvx, tvy, 3)
                if hit is by_who:
                    xv, yv = xamount - tvx, yamount - tvy
                    _, xv2, yv2 = o.try_move(o.x, o.y, xv, yv, 3)
                    o.x += xv2
                    o.y += yv2
                    if xv2 != xv or yv2 != yv:
                        failed = True
        return not failed

    # --- events for the renderer, audio and observation (no effect on rules) ---
    def emit(self, kind: str, **data) -> None:
        self.events.append(Event(kind, data))

    def player_owned(self, obj) -> bool:
        """The object is a player, or was fired by one (projectiles link their creator first)."""
        if obj is None:
            return False
        owner = obj.objs[0] if obj.objs else None
        return any(obj is v.focus or (owner is not None and owner is v.focus) for v in self.views)

    def note_damage(self, target: GameObject, amount: int, from_obj) -> None:
        # Output only: these fields feed statistics and effects, never a rule.
        self.emit("damage", target=target.uid, type=target.ctype.name, amount=amount,
                  source=from_obj.ctype.name if from_obj is not None else None,
                  source_uid=from_obj.uid if from_obj is not None else None, by_player=self.player_owned(from_obj))
