"""Remastered mode's campaign: the levels in this build and how their exits join them.

The original loads the next level from the exit's ``aistate`` (people.lsp:915-923,
``next_level_ai``: ``(request_level_load (concatenate 'string "levels/level" (digstr (aistate) 2)
".spe"))``). The shareware training level (``level00``) ends in a room of four exits to Levels 1
to 4, Level 1's exit leads to Level 2, and Level 2's to Level 3.

This build has the training level, Level 1 and Level 2. An exit to any other level is locked in
Remastered mode (``Remastered.after_step``). So is an exit to a level whose objects are not all
ported yet: the level must load in strict mode before it can be played. Classic mode is Level 1
only and never reads this module.
"""

from __future__ import annotations

from functools import cache

from ..paths import level_path
from ..scope import LEVEL_TYPES

LEVELS = ("level00", "level01", "level02")  # campaign order
TITLES = {"level00": "Training", "level01": "Level 1", "level02": "Level 2"}


def title(name: str) -> str:
    return TITLES.get(name) or f"Level {int(name[5:])}"


def exit_level(n: int) -> str:
    """The level an exit with ``aistate`` n loads (people.lsp:921)."""
    return f"level{n:02d}"


def in_build(name: str) -> bool:
    return name in LEVELS and level_path(name).exists()


@cache
def unported(name: str) -> dict[str, list[str]]:
    """Each of the level's object types that names a behaviour no Python port provides yet."""
    from .behaviors import registry
    from .chardefs import load_chardefs
    from .world import missing_behaviours

    defs, reg = load_chardefs(), registry()
    missing = {t: missing_behaviours(defs[t].funs, reg) for t in sorted(LEVEL_TYPES[name]) if t in defs}
    return {t: m for t, m in missing.items() if m}


def playable(name: str) -> bool:
    return in_build(name) and not unported(name)


def playable_levels() -> list[str]:
    return [n for n in LEVELS if playable(n)]
