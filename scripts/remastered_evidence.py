"""Screenshots of Remastered's campaign and Horde 2, for the PR and the course record.

    uv run python scripts/remastered_evidence.py            # writes evidence/remastered/*.png

Every shot is deterministic: a fixed seed, and either a saved route (evidence/routes) played to a
given tick, or a scripted Horde run. Nothing here is a human playtest.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from abuse_remake.engine.view import Inputs  # noqa: E402
from abuse_remake.game.app import App, parse_args  # noqa: E402
from abuse_remake.paths import repo_root  # noqa: E402

OUT = Path(repo_root()) / "evidence" / "remastered"


def app(*extra: str) -> App:
    a = App(parse_args(["--frames", "1", "--no-audio", "--scale", "2", *extra]))
    a.state = "play"
    return a


def shot(a: App, name: str) -> None:
    if a.game.view.draw_solid != -1:
        a.renderer.render(1.0)  # a pickup's one-frame flash, still pending because ticks ran undrawn
    a.draw()
    OUT.mkdir(parents=True, exist_ok=True)
    pygame.image.save(a.screen, str(OUT / f"{name}.png"))
    print(f"wrote {OUT / name}.png")


def play_route(level: str, stops: dict[int, str]) -> None:
    route = json.loads((Path(repo_root()) / "evidence" / "routes" / f"{level}.json").read_text())
    a = app("--seed", str(route["seed"]), "--difficulty", route["difficulty"], "--level", level)
    steps = [r[1:] for r in route["inputs"] for _ in range(r[0])]

    def inputs(tick):
        x, y, special, fire, dx, dy = steps[min(tick, len(steps) - 1)]
        p = a.game.player
        return Inputs(x=x, y=y, b1=special, b2=fire, pointer_x=p.x + dx, pointer_y=p.y - 20 + dy)

    a.scripted_inputs = inputs
    for i in range(len(steps)):
        a.tick(i)
        if i + 1 in stops:
            shot(a, stops[i + 1])
        if a.state != "play":
            break
    shot(a, f"{level}-complete")


def horde(arena: str, wave: int, ticks: int, name: str) -> None:
    a = app("--seed", "4", "--horde", "--arena", arena)
    st = a.game.horde.state
    st.update(wave=wave - 1, spawn_in=1)

    def inputs(tick):
        g = a.game
        p = g.player
        foes = [o for o in g.world.objects if o.uid in st["alive"]]
        if not foes:
            return Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20)
        f = min(foes, key=lambda o: abs(o.x - p.x))
        return Inputs(b2=1, y=-1 if abs(f.x - p.x) < 40 else 0, pointer_x=f.x, pointer_y=f.y - 15)

    a.scripted_inputs = inputs
    for i in range(ticks):
        if st["cards"]:
            break
        a.tick(i)
    shot(a, name)


def main() -> int:
    play_route("level00", {150: "level00-lift", 200: "level00-upper-corridor", 446: "level00-speed-power",
                           530: "level00-flight-ledge"})
    if (Path(repo_root()) / "evidence" / "routes" / "level02.json").exists():
        play_route("level02", {200: "level02-robot-fight", 1220: "level02-gate-puzzle", 1700: "level02-long-hall",
                               2300: "level02-console"})
    horde("prison", 3, 260, "horde-prison-wave3")
    horde("rooftop", 5, 200, "horde-rooftop-boss")
    horde("pit", 6, 220, "horde-pit-wave6")
    a = app("--seed", "4", "--horde", "--arena", "rooftop")
    a.game.horde.state["cards"] = ["flight", "medkit", "rockets"]
    shot(a, "horde-cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
