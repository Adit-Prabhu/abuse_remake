"""Render the screenshots behind the hidden-wall paragraph of docs/information-boundary.md.

    uv run python scripts/boundary_evidence.py

Classic mode, Level 1, scale 3. It writes:
- ``hidden-walls-classic.png``: the whole view, with the player 60 px left of the first column
  of ``HIDDEN_WALL`` objects (x 210);
- ``hidden-wall-types.png``: for each hidden-wall type in Level 1, its first instance in place,
  cropped around it, with its picture box outlined in yellow;
- ``hidden-wall-frames.png``: the same instances drawn at frames 0, 1 and 2 (no cracks, then
  more), with the blocking outline in cyan. It is the evidence for
  ``observation.HIDDEN_WALL_LOOK``.

A development tool: it places the player directly, which no player can do.
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
SHEET = OUT.with_name("hidden-wall-types.png")
FRAMES = OUT.with_name("hidden-wall-frames.png")
SCALE = 3


def main() -> int:
    os.environ.setdefault("ABUSE_REMAKE_HOME", str(Path(repo_root()) / "runs" / "boundary-home"))
    a = App(parse_args(["--frames", "1", "--no-audio", "--scale", str(SCALE), "--mode", "classic"]))
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
    contact_sheet()
    frames_sheet()
    return 0


def contact_sheet() -> None:
    """One crop per hidden-wall type: a fresh game each time, the player 60 px to the left."""
    first: dict = {}
    probe = App(parse_args(["--frames", "1", "--no-audio", "--scale", str(SCALE), "--mode", "classic"]))
    for o in sorted(probe.game.world.objects, key=lambda o: (o.x, o.y)):
        if o.ctype.name.startswith("HIDDEN_WALL") and not o.deleted:
            first.setdefault(o.ctype.name, (o.x, o.y))
    font = pygame.font.Font(None, 22)
    crops = []
    for name, (wx, wy) in sorted(first.items()):
        a = App(parse_args(["--frames", "1", "--no-audio", "--scale", str(SCALE), "--mode", "classic"]))
        a.state = "play"
        g = a.game
        wall = next(o for o in g.world.objects if o.ctype.name == name and (o.x, o.y) == (wx, wy))
        p = g.player
        p.x, p.y = wx - 60, wy
        for _ in range(3):
            g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20))
        a.draw()
        xoff, yoff = a.renderer.camera(1.0)
        x1, y1, x2, y2 = wall.picture_space()
        box = pygame.Rect((x1 - xoff) * SCALE, (y1 - yoff) * SCALE, (x2 - x1 + 1) * SCALE, (y2 - y1 + 1) * SCALE)
        area = box.inflate(70 * SCALE, 30 * SCALE).clip(a.screen.get_rect())
        crop = a.screen.subsurface(area).copy()
        pygame.draw.rect(crop, (255, 220, 0), box.move(-area.x, -area.y), 1)
        crops.append((f"{name} at ({wx}, {wy})", crop))
    w = max(c.get_width() for _, c in crops)
    h = sum(c.get_height() + 26 for _, c in crops)
    sheet = pygame.Surface((w, h))
    y = 0
    for label, crop in crops:
        sheet.blit(font.render(label, True, (230, 230, 230)), (4, y + 4))
        sheet.blit(crop, (0, y + 24))
        y += crop.get_height() + 26
    pygame.image.save(sheet, str(SHEET))
    print(f"wrote {SHEET}: {len(crops)} types")



def frames_sheet() -> None:
    """Each type's first instance at frames 0, 1 and 2, with its blocking outline."""
    first: dict = {}
    probe = App(parse_args(["--frames", "1", "--no-audio", "--scale", str(SCALE), "--mode", "classic"]))
    for o in sorted(probe.game.world.objects, key=lambda o: (o.x, o.y)):
        if o.ctype.name.startswith("HIDDEN_WALL") and not o.deleted:
            first.setdefault(o.ctype.name, (o.x, o.y))
    font = pygame.font.Font(None, 22)
    rows = []
    for name, (wx, wy) in sorted(first.items()):
        crops = []
        for frame in range(3):
            a = App(parse_args(["--frames", "1", "--no-audio", "--scale", str(SCALE), "--mode", "classic"]))
            a.state = "play"
            g = a.game
            wall = next(o for o in g.world.objects if o.ctype.name == name and (o.x, o.y) == (wx, wy))
            p = g.player
            p.x, p.y = wx - 60, wy
            for _ in range(3):
                g.step(Inputs(pointer_x=p.x + 100, pointer_y=p.y - 20))
            wall.current_frame = frame
            a.draw()
            xoff, yoff = a.renderer.camera(1.0)
            x1, y1, x2, y2 = wall.picture_space()
            box = pygame.Rect((x1 - xoff) * SCALE, (y1 - yoff) * SCALE, (x2 - x1 + 1) * SCALE, (y2 - y1 + 1) * SCALE)
            area = box.inflate(50 * SCALE, 24 * SCALE).clip(a.screen.get_rect())
            crop = a.screen.subsurface(area).copy()
            fig = wall.figure()
            dmg = fig.f_damage if wall.direction > 0 else fig.b_damage
            pts = [((wall.x + wall.tx(px) - xoff) * SCALE - area.x, (wall.y + wall.ty(py) - yoff) * SCALE - area.y)
                   for px, py in dmg.points]
            if len(pts) >= 2:
                pygame.draw.lines(crop, (0, 255, 255), False, pts, 1)
            crops.append(crop)
        rows.append((f"{name} at ({wx}, {wy}): frames 0, 1, 2 (cyan: blocking outline)", crops))
    w = max(sum(c.get_width() + 8 for c in cs) for _, cs in rows)
    h = sum(max(c.get_height() for c in cs) + 26 for _, cs in rows)
    sheet = pygame.Surface((w, h))
    y = 0
    for label, cs in rows:
        sheet.blit(font.render(label, True, (230, 230, 230)), (4, y + 4))
        x = 0
        for c in cs:
            sheet.blit(c, (x, y + 24))
            x += c.get_width() + 8
        y += max(c.get_height() for c in cs) + 26
    pygame.image.save(sheet, str(FRAMES))
    print(f"wrote {FRAMES}")


if __name__ == "__main__":
    sys.exit(main())
