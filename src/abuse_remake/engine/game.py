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
                 strict: bool = True, object_filter=None):
        lf = _level(level)
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
        set_player_defaults(player)
        w.add_object_after(player, start)
        self.player = player
        self.seed = seed
        self.frames = 0

    def step(self, inputs: Inputs | None = None, weapon: WeaponCommand | None = None) -> None:
        if weapon is not None:
            if weapon.select is not None:
                self.view.select_weapon(weapon.select)
            elif weapon.cycle < 0:
                self.view.last_weapon()
            elif weapon.cycle > 0:
                self.view.next_weapon()
        self.view.set_input(inputs or Inputs(pointer_x=self.player.x + 100, pointer_y=self.player.y - 20))
        self.world.step()
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

    def snapshot(self):
        import copy

        return copy.deepcopy((self.world, self.view, self.player, self.frames), self._shared())

    def restore(self, snap) -> None:
        import copy

        self.world, self.view, self.player, self.frames = copy.deepcopy(snap, self._shared())

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
        return h.hexdigest()


def _filtered(lf: LevelFile, keep) -> LevelFile:
    """A copy of the level that keeps only objects for which ``keep(obj)`` is true (tests)."""
    import copy

    out = copy.copy(lf)
    out.objects = [copy.copy(o) for o in lf.objects]
    for o in out.objects:
        if not keep(o):
            o.removed_on_load = True
    return out
