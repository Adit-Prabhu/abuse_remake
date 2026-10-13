"""Abuse (Crack dot Com, 1996) Level 1 reconstruction.

The simulation in ``abuse_remake.engine`` is pure Python with no pygame import,
so it runs headless for tests and agent evaluation. ``abuse_remake.game`` is
the pygame front end and ``abuse_remake.agent`` is the playing-agent interface.
"""

__version__ = "0.1.0"

# Pinned upstream sources cited throughout docs/rule-source-map.md.
ENGINE_SOURCE = "historicalsource/abuse@01cce80eaf2ae82bafb9981162e205e42d0fae2f"
DATA_SOURCE = "Xenoveritas/abuse@9d1f66f57377859bae10e28eabebea0b9c750490"
