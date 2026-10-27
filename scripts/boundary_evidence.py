"""Render the screenshot behind the hidden-wall paragraph of docs/information-boundary.md.

    uv run python scripts/boundary_evidence.py

Classic mode, Level 1, scale 3: the player stands 60 px left of the first column of
``HIDDEN_WALL`` objects (x 210), which the original draws in play as cracked stone. A
development tool: it places the player directly, which no player can do.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from abuse_remake.engine.view import Inputs  # noqa: E402
from abuse_remake.game.app import App, parse_args  # noqa: E402
from abuse_remake.paths import repo_root  # noqa: E402

OUT = Path(repo_root()) / "evidence" / "boundary" / "hidden-walls-classic.png"


def main() -> int:
    os.environ.setdefault("ABUSE_REMAKE_HOME", str(Path(repo_root()) / "runs" / "boundary-home"))
    a = App(parse_args(["--frames", "1", "--no-audio", "--scale", "3", "--mode", "classic"]))
    a.state = "play"
    g = a.game
    walls = sorted((o for o in g.world.objects if o.ctype.name.startswith("HIDDEN_WALL") and not o.deleted),
                   key=lambda o: (o.x, o.y))
    p = g.player
    p.x, p.y = walls[0].x - 60, walls[0].y
    for _ in range(3):
        g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20))
    a.draw()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(a.screen, str(OUT))
    print(f"wrote {OUT}: {walls[0].ctype.name} at ({walls[0].x}, {walls[0].y})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
