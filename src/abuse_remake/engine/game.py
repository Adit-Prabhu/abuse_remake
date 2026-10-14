"""Load Level 1, put the player in it, and advance it one 15 Hz frame at a time.

This mirrors the start of play in historicalsource/abuse@01cce80:
- ``create_players DARNEL`` (abuse.lsp) makes the player before the level loads;
- level::load_player_info runs ``set_player_defaults`` (level.c:1814-1830);
- each object's reload function runs, then insert_players puts the player at START, right
  after START in the object list (level.c:1404-1421, 3068-3088);
- each loop reads input, then steps (main loop, game.c:2650-2670).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache

from ..formats.level_file import LevelFile, load_level
from ..formats.tiles import TileSet, load_tiles
from ..paths import data_root, level_path
from ..scope import LEVEL
from .behaviors import registry
from .behaviors.player import set_player_defaults
from .chardefs import FrameStore
from .view import Inputs, View
from .world import DEFAULT_DIFFICULTY, World


@cache
def _tiles() -> TileSet:
    return load_tiles(data_root())


@cache
def _frames() -> FrameStore:
    return FrameStore()


@cache
def _level(name: str) -> LevelFile:
    tiles = _tiles()
    return load_level(level_path(name), set(tiles.fore), set(tiles.back))


@dataclass
class WeaponCommand:
    """Weapon keys, applied like the original's packet: they take effect next frame."""

    select: int | None = None  # number keys 1-7, as index 0-6
    cycle: int = 0  # -1 Ctrl (previous), +1 Insert (next)


class Game:
    def __init__(self, seed: int = 0, difficulty: str = DEFAULT_DIFFICULTY, level: str = LEVEL,
                 strict: bool = True, object_filter=None, remastered: bool = False, horde: bool = False,
                 carry: Game | None = None, arena: str = "prison"):
        """``carry``: the game whose exit led here. Its player and view go on into this level, as
        they do when the original loads the next level (see ``_carry_over``)."""
        if horde:  # Remastered's Horde arena: the map without the level's objects
            from .horde import ARENAS, keep_for_horde

            remastered, object_filter, level = True, keep_for_horde, ARENAS[arena].level
        lf = _level(level)
        if carry is not None and lf.has_player_info:
            # a saved game restores its own views, weapons and rand_on instead (level.c:1695-1813)
            raise ValueError(f"{level} holds saved player info; only a fresh level can be carried into")
        if object_filter is not None:
            lf = _filtered(lf, object_filter)
        self.world = World(lf, _tiles(), registry(), seed=seed, difficulty=difficulty,
                           frames=_frames(), strict=strict)
        w = self.world
        start = w.find_type("START")
        if start is None:
            raise ValueError(f"{level} has no START object")
        player = w.create("DARNEL", start.x, start.y)
        self.view = View(w, player, 0, total_weapons=len(w.weapon_types))
        w.views.append(self.view)
        if carry is not None:
            _carry_over(carry, self.view, w)
        set_player_defaults(player)
        w.add_object_after(player, start)
        self.player = player
        self.level = level
        self.carried = carry is not None
        self.seed = seed
        self.frames = 0
        self.horde_arena = arena if horde else None  # Horde removes the level's objects; no extras either
        self.remastered = None
        if remastered:  # rule changes for --mode remastered only; Classic never builds this
            from .remastered import Remastered

            self.remastered = Remastered(self)
        self.horde = None
        if horde:
            from .horde import Horde

            self.horde = Horde(self, arena)

    def step(self, inputs: Inputs | None = None, weapon: WeaponCommand | None = None) -> None:
        if weapon is not None:
            if weapon.select is not None:
                self.view.select_weapon(weapon.select)
            elif weapon.cycle < 0:
                self.view.last_weapon()
            elif weapon.cycle > 0:
                self.view.next_weapon()
        self.view.set_input(inputs or Inputs(pointer_x=self.player.x + 100, pointer_y=self.player.y - 20))
        if self.remastered is not None:
            self.remastered.before_step()
        self.world.step()
        if self.remastered is not None:
            self.remastered.after_step()
        if self.horde is not None:
            self.horde.after_step()
        self.frames += 1

    # --- save and restore (the human game's restart; see SCOPE.md) ---
    def _shared(self) -> dict:
        """Objects every snapshot shares rather than copies: art, types, tiles, functions."""
        w = self.world
        memo = {id(w.frames): w.frames, id(w.registry): w.registry, id(w.level): w.level,
                id(w.tiles.segments): w.tiles.segments, id(w.types): w.types,
                id(w._types_by_index): w._types_by_index, id(w.weapon_types): w.weapon_types}
        for ct in w.types.values():
            memo[id(ct)] = ct
        for v in w.globals.values():
            if callable(v):  # hooks belong to the front end, not the saved game
                memo[id(v)] = v
        return memo

    def _hooks(self) -> dict:
        return {k: v for k, v in self.world.globals.items() if callable(v)}

    def snapshot(self):
        """A deep copy of the game state. Front-end hooks (callables in ``world.globals``, such
        as the app's ``save_hook``) are left out of the copy, so restoring a snapshot any number
        of times never copies the front end itself."""
        import copy

        hooks = self._hooks()
        for k in hooks:
            del self.world.globals[k]
        try:
            return copy.deepcopy((self.world, self.view, self.player, self.frames), self._shared())
        finally:
            self.world.globals.update(hooks)

    def restore(self, snap) -> None:
        """Replace the state with a copy of ``snap``; the live game's hooks stay bound."""
        import copy

        hooks = self._hooks()
        self.world, self.view, self.player, self.frames = copy.deepcopy(snap, self._shared())
        self.world.globals.update(hooks)

    @property
    def player_dead(self) -> bool:
        return self.player.aistate >= 2 or self.player.state == "dead"

    def state_hash(self) -> str:
        """A digest of every object's simulation state, for determinism tests."""
        h = hashlib.sha256()
        w = self.world
        h.update(f"{w.tick_counter},{w.rng.rand_on}".encode())
        for o in w.objects:
            h.update((f"{o.ctype.name},{o.x},{o.y},{o.xvel},{o.yvel},{o.fxvel},{o.fyvel},{o.xacel},"
                      f"{o.yacel},{o.state},{o.current_frame},{o.hp},{o.aistate},{o.aistate_time},"
                      f"{o.direction},{sorted(o.lvars.items())}").encode())
        v = self.view
        h.update(f"{v.weapons},{v.current_weapon},{v.ambient},{v.pan_x},{v.pan_y}".encode())
        if self.horde is not None:  # Horde's score, cards and timers (Classic never has them)
            h.update(repr(sorted(self.horde.state.items())).encode())
        return h.hexdigest()


# The player's fields that a level change keeps. Its position, links, lights and place in the
# object list belong to the level; the rest is the same object (see _carry_over).
_PLAYER_FIELDS = ("direction", "state", "current_frame", "fade_dir", "fade_count", "fade_max", "flags",
                  "grav_on", "targetable_on", "xvel", "yvel", "xacel", "yacel", "fx", "fy", "fxvel",
                  "fyvel", "fxacel", "fyacel", "aitype", "aistate", "aistate_time", "hp", "mp", "fmp",
                  "frame_dir")
_VIEW_SKIP = {"world", "focus"}


def _carry_over(old: Game, view: View, world: World) -> None:
    """Take the old game's player and view into a newly loaded level.

    The original keeps both when an exit loads the next level: ``game::load_level`` deletes only
    the level (game.c:503-537), whose ``load_fail`` first takes each player out of the object
    list (level.c:64-96). Taking it out unlinks its top half and lights (level.c:2521-2525). A
    level with no saved player info (every campaign level; checked when loading) runs
    ``set_player_defaults`` (level.c:1815-1835) and puts the player at its START
    (``insert_players``, level.c:3068-3088). The view keeps its weapons and ammo. ``rand_on`` is
    a global (imlib/jrand.c:6), so the random table carries on where it was.
    """
    src, dst = old.player, view.focus
    for name in _PLAYER_FIELDS:
        setattr(dst, name, getattr(src, name))
    dst.lvars = dict(src.lvars)
    for name, value in vars(old.view).items():
        if name not in _VIEW_SKIP:
            setattr(view, name, list(value) if isinstance(value, list) else value)
    world.rng.rand_on = old.world.rng.rand_on


def _filtered(lf: LevelFile, keep) -> LevelFile:
    """A copy of the level that keeps only objects for which ``keep(obj)`` is true (tests)."""
    import copy

    out = copy.copy(lf)
    out.objects = [copy.copy(o) for o in lf.objects]
    for o in out.objects:
        if not keep(o):
            o.removed_on_load = True
    return out
