"""Remastered mode's campaign: the levels in this build and how their exits join them.

The original loads the next level from the exit's ``aistate`` (people.lsp:915-923,
``next_level_ai``: ``(request_level_load (concatenate 'string "levels/level" (digstr (aistate) 2)
".spe"))``), and ends the game at ``end_level`` (22, people.lsp:978). The shareware training
level (``level00``) ends in a room of four exits to Levels 1 to 4. Level 1's exit leads to Level 2
and Level 2's to Level 3.

This build has the training level, Level 1 and Level 2. A level is playable once every object
type in it has its behaviours ported (it must load in strict mode). What an exit does in
Remastered mode (``Remastered._follow_exits``, ``exit_result``):
- to a playable level: the level ends and the next one follows;
- to a level that cannot be played, from a level that has another exit to a playable level (the
  training level's portals to Levels 3 and 4): the exit stays shut;
- otherwise: the level ends and so does the campaign (Level 2's exit to Level 3).
Whether a level is playable depends only on the code and the vendored data, never on the run.
Classic mode is Level 1 only and never reads this module.
"""

from __future__ import annotations

from functools import cache

from ..paths import level_path
from ..scope import LEVEL_TYPES

LEVELS = ("level00", "level01", "level02")  # campaign order
TITLES = {"level00": "Training", "level01": "Level 1", "level02": "Level 2"}
END_LEVEL = 22  # people.lsp:978: an exit with this number ends the game (request_end_game)


# Remastered design: flight, invisibility and ultra health were registered-version content in
# 1995, so no shareware level has them (only speed). Remastered places them by hand in the
# campaign levels after loading. Level 1 gets none, so its object list stays the original's and
# Remastered Level 1 still plays exactly like Classic. Each spot is on or beside a saved route
# (evidence/routes), so it can be reached.
EXTRA_OBJECTS: dict[str, tuple[tuple[str, int, int], ...]] = {
    # the training level: on the saved route, which picks each one up (tests/test_campaign_routes.py);
    # a new power replaces the last
    "level00": (("POWER_SNEAKY", 1061, 196), ("POWER_FLY", 1885, 421), ("POWER_HEALTH", 1771, 931)),
    # Level 2: ultra health just after the first cleaner-robot fight, flight in the long hall, and
    # invisibility on the way to the far-right ladders; all on the saved route
    "level02": (("POWER_HEALTH", 364, 571), ("POWER_FLY", 2402, 631), ("POWER_SNEAKY", 2817, 1396)),
}


def title(name: str | None) -> str:
    if name is None:
        return "the end"
    return TITLES.get(name) or f"Level {int(name[5:])}"


def exit_level(n: int) -> str | None:
    """The level an exit with ``aistate`` n loads (people.lsp:917-921), or None for the end."""
    return None if n == END_LEVEL else f"level{n:02d}"


def in_build(name: str | None) -> bool:
    return name in LEVELS


@cache
def unported(name: str) -> dict[str, list[str]]:
    """Each of the level's object types that names a behaviour no Python port provides yet."""
    from .behaviors import registry
    from .chardefs import load_chardefs
    from .world import missing_behaviours

    if name not in LEVEL_TYPES:
        return {"*": ["not in this build"]}
    defs, reg = load_chardefs(), registry()
    missing = {t: missing_behaviours(defs[t].funs, reg) if t in defs else ["undefined type"]
               for t in sorted(LEVEL_TYPES[name])}
    return {t: m for t, m in missing.items() if m}


def playable(name: str | None) -> bool:
    return in_build(name) and not unported(name)


def playable_levels() -> list[str]:
    return [n for n in LEVELS if playable(n)]


@cache
def exits(name: str) -> tuple[int, ...]:
    """The ``aistate`` of each exit (NEXT_LEVEL) in a level of this build."""
    from ..formats.level_file import load_level

    return tuple(sorted({o.vars.get("aistate", 0) for o in load_level(level_path(name)).objects_of("NEXT_LEVEL")}))


def exit_result(level: str, n: int) -> str:
    """"open", "locked" or "end" for an exit with ``aistate`` n in ``level`` (see the module)."""
    if n == END_LEVEL:
        return "end"  # request_end_game (people.lsp:917-918), whatever other exits there are
    if playable(exit_level(n)):
        return "open"
    if level in LEVELS and any(playable(exit_level(m)) for m in exits(level)):
        return "locked"
    return "end"


def restart_health(game) -> None:
    """A restart with no console save reloads the level with full health
    (``restart_player``, people.lsp:515-520). Level 1 starts at full health anyway; a level
    entered from the one before starts with whatever health was carried in."""
    game.player.set_hp(100)
