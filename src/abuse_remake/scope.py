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

# Remastered mode's campaign (added 2026-10-14): the shareware v1.01 training level and Level 2.
# They are outside the fidelity scope above; Classic mode and the agent evaluations never load
# them. tests/test_campaign.py checks each list against its level file.
_SHARED_WITH_LEVEL01 = frozenset({
    "START", "RESTART_POSITION", "NEXT_LEVEL", "NEXT_LEVEL_TOP", "HEALTH", "MBULLET_ICON20",
    "GRENADE_ICON10", "ROCKET_ICON2", "SENSOR", "DEATH_SENSOR", "GATE_AND", "GATE_XOR", "SWITCH",
    "SWITCH_DIMMER", "SWITCH_DOOR", "SMART_PLAT_SMALL", "TP_DOOR", "TELE2", "TELE_BEAM",
    "TRAP_DOOR2", "AMBIENT_SOUND",
})
LEVEL00_TYPES = _SHARED_WITH_LEVEL01 | frozenset({
    "FORCE_FIELD", "SWITCH_MOVER", "HIDDEN_WALL1", "HIDDEN_WALL2", "HIDDEN_WALL3", "HIDDEN_WALL4",
    "HIDDEN_WALL5", "HIDDEN_WALL_2x2", "HIDDEN_WALL_3WAL",
    # not in Level 1
    "GATE_OR", "LADDER", "LAVA", "POINTER", "POWER_FAST", "SPRING", "SWITCH_BALL", "TRAIN_MSG", "WHO",
})
LEVEL02_TYPES = _SHARED_WITH_LEVEL01 | frozenset({
    "ANT_ROOF", "HIDDEN_ANT", "BOLDER", "SPRAY_GUN", "GATE_DELAY", "GATE_NOT", "GRENADE_ICON2",
    "MBULLET_ICON5", "SWITCH_ONCE",
    # not in Level 1
    "BLOCK", "GATE_OR", "INDICATOR", "JUGGER", "LADDER", "LAVA", "MARKER", "POWER_FAST", "PUSHER",
    "ROB1", "SPRING", "STEP", "TRACK_GUN",
})
LEVEL_TYPES = {"level00": LEVEL00_TYPES, "level01": LEVEL01_TYPES, "level02": LEVEL02_TYPES}

TICKS_PER_SECOND = 15
FULL_LEVEL_TICK_LIMIT = 9000  # 10 minutes of game time; a course choice
SEGMENT_TICK_LIMIT = 2700  # 3 minutes from a restart console; a course choice
