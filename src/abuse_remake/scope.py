"""The agreed scope, as data, so tests can hold SCOPE.md and the level file to it."""

LEVEL = "level01"

# Every object type saved in levels/level01.spe. tests/test_scope.py checks this against the
# file and against SCOPE.md, so a type cannot silently fall out of scope.
LEVEL01_TYPES = frozenset({
    # player start and progress
    "START", "RESTART_POSITION", "NEXT_LEVEL", "NEXT_LEVEL_TOP",
    # enemies and hazards
    "ANT_ROOF", "HIDDEN_ANT", "ANT_CRACK", "SPRAY_GUN", "BOLDER",
    # pickups
    "HEALTH", "MBULLET_ICON5", "MBULLET_ICON20", "GRENADE_ICON2", "GRENADE_ICON10",
    "FBOMB_ICON1", "ROCKET_ICON2",
    # logic network
    "SENSOR", "DEATH_SENSOR", "GATE_AND", "GATE_XOR", "GATE_NOT", "GATE_DELAY", "GATE_PULSE",
    "SWITCH", "SWITCH_ONCE", "SWITCH_MOVER", "SWITCH_DIMMER",
    # world objects
    "SWITCH_DOOR", "FORCE_FIELD", "TRAP_DOOR2", "TRAP_DOOR3", "SMART_PLAT_SMALL",
    "TP_DOOR", "TELE2", "TELE_BEAM",
    "HIDDEN_WALL1", "HIDDEN_WALL2", "HIDDEN_WALL3", "HIDDEN_WALL4", "HIDDEN_WALL5",
    "HIDDEN_WALL_2x2", "HIDDEN_WALL_3WAL", "HIDDEN_WALL_3FLR",
    # sound emitters (they draw from the shared random table, so they matter to fidelity)
    "AMBIENT_SOUND",
})

TICKS_PER_SECOND = 15
FULL_LEVEL_TICK_LIMIT = 9000  # 10 minutes of game time; a course choice
SEGMENT_TICK_LIMIT = 2700  # 3 minutes from a restart console; a course choice
