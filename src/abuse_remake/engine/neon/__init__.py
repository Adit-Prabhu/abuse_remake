"""Neon Protocol: an optional, separate game design built on the Abuse remake.

Never used by Classic, Remastered or any evaluation. Pure Python and deterministic: integer
positions, a local seeded RNG, 30 ticks a second. See docs/neon-protocol.md.
"""

from .enemies import HP as ENEMY_HP
from .game import DIFFICULTIES, SECTORS, TICK_RATE, VARIANTS, NeonGame
from .horde import UPGRADES
from .player import NeonInput, Player
from .tilemap import TILE, load_map, parse_map
from .training import LESSONS
from .weapons import WEAPONS

__all__ = ["DIFFICULTIES", "ENEMY_HP", "LESSONS", "SECTORS", "TICK_RATE", "TILE", "UPGRADES", "VARIANTS",
           "WEAPONS", "NeonGame", "NeonInput", "Player", "load_map", "parse_map"]
