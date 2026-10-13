"""Line-versus-polygon "setback" collision against foreground tiles.

Sources (historicalsource/abuse@01cce80):
- setback_intersect: abuse/src/intsect.c (the live version after the commented-out one)
- level::foreground_intersect: abuse/src/level.c:2587-2665, with the ``remapx``/``remapy``
  macros that push tile-edge points one pixel outward so neighbouring tiles overlap.

A moving point travels from (x1, y1) toward (x2, y2); every boundary segment it would
cross pulls (x2, y2) back to just before the crossing.
"""

from __future__ import annotations

from .cmath import cdiv

FORE_W, FORE_H = 30, 15
BLACK = 0  # game.hpp: tile 0 is never collision-checked


def setback_intersect(x1, y1, x2, y2, xp1, yp1, xp2, yp2, inside):
    """Return ``(hit, x2, y2)``. ``inside`` is 1, -1 or 0 (0 = always set back)."""
    a1 = y2 - y1
    b1 = x1 - x2
    c1 = -x1 * y2 + x2 * y1
    if yp1 < yp2 or (yp1 == yp2 and xp1 > xp2):  # use only increasing functions
        xp1, yp1, xp2, yp2 = xp2, yp2, xp1, yp1
    r1 = xp1 * a1 + yp1 * b1 + c1
    r2 = xp2 * a1 + yp2 * b1 + c1
    if (r1 ^ r2) <= 0 or r1 == 0 or r2 == 0:
        a2 = yp2 - yp1
        b2 = xp1 - xp2
        c2 = -xp1 * yp2 + xp2 * yp1
        r1 = x1 * a2 + y1 * b2 + c2
        r2 = x2 * a2 + y2 * b2 + c2
        if (r1 ^ r2) <= 0 or r1 == 0 or r2 == 0:
            if ((xp1 < xp2 and (r2 ^ inside) > 0) or (xp1 >= xp2 and (r2 ^ inside) < 0)
                    or inside == 0 or r2 == 0):
                ae = a1 * b2
                bd = b1 * a2
                if ae != bd:  # co-linear returns 0
                    x2 = cdiv(b1 * c2 - b2 * c1, ae - bd)
                    y2 = cdiv(a1 * c2 - a2 * c1, bd - ae)
                    if y2 != y1:  # push the intersection back one pixel
                        y2 = y2 - 1 if y2 > y1 else y2 + 1
                    if x2 != x1:
                        x2 = x2 - 1 if x2 > x1 else x2 + 1
                    if inside:  # make sure the end point is on the right side
                        r1 = x1 * a2 + y1 * b2 + c2
                        r2 = x2 * a2 + y2 * b2 + c2
                        if r2 != 0 and (r1 ^ r2) < 0:
                            x2, y2 = x1, y1
                    return True, x2, y2
    return False, x2, y2


def _remap(v: int, size: int) -> int:
    if v == 0:
        return -1
    if v == size - 1:
        return size + 1
    return v


class TileMap:
    """The foreground map plus each tile's collision segments, pre-remapped."""

    def __init__(self, width: int, height: int, cells: list[int], fore_boundaries: dict):
        self.width = width
        self.height = height
        self.cells = cells  # fgvalue() already applied (flags stripped)
        self.segments: dict[int, tuple] = {}
        for num, boundary in fore_boundaries.items():
            pts = boundary.points
            segs = []
            for j in range(len(pts) - 1):
                xa = _remap(pts[j][0], FORE_W)
                ya = _remap(pts[j][1], FORE_H)
                xb = _remap(pts[j + 1][0], FORE_W)
                yb = _remap(pts[j + 1][1], FORE_H)
                ins = 1 if boundary.inside[j] else -1
                segs.append((xa, ya, xb, yb, ins, min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)))
            self.segments[num] = tuple(segs)
        self.last_tile_hit = (0, 0)

    def get(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[x + y * self.width]
        return 0

    def put(self, x: int, y: int, tile: int) -> None:
        self.cells[x + y * self.width] = tile

    def foreground_intersect(self, x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
        """Port of level::foreground_intersect; returns the set-back end point."""
        tl, th = FORE_W, FORE_H
        bx1, bx2 = (x1, x2) if x1 <= x2 else (x2, x1)
        by1, by2 = (y1, y2) if y1 <= y2 else (y2, y1)
        bx1 = cdiv(bx1 - 2, tl) - 1
        bx2 = cdiv(bx2 + tl + 2, tl) + 1
        by1 = cdiv(by1 - 2, th) - 1
        by2 = cdiv(by2 + th + 2, th) + 1
        if bx2 >= self.width:
            x2 = tl * self.width - 1
        if by2 >= self.height:
            y2 = th * self.height - 1
        bx1 = max(bx1, 0)
        by1 = max(by1, 0)
        if bx1 > bx2 or by1 > by2:
            return x2, y2
        cells, width, height, segments = self.cells, self.width, self.height, self.segments
        for bx in range(bx1, bx2 + 1):
            if bx >= width:
                break  # get_fg returns 0 (BLACK) off the map
            xo = bx * tl
            for by in range(by1, by2 + 1):
                if by >= height:
                    break
                block = cells[bx + by * width]
                if block <= BLACK:
                    continue
                segs = segments.get(block)
                if not segs:
                    continue
                yo = by * th
                for (xa, ya, xb, yb, ins, sx0, sx1, sy0, sy1) in segs:
                    # Exact prefilter: setback_intersect only moves (x2, y2) when the two
                    # segments touch, which needs their bounding boxes to overlap.
                    lx0, lx1 = (x1, x2) if x1 <= x2 else (x2, x1)
                    if xo + sx1 < lx0 or xo + sx0 > lx1:
                        continue
                    ly0, ly1 = (y1, y2) if y1 <= y2 else (y2, y1)
                    if yo + sy1 < ly0 or yo + sy0 > ly1:
                        continue
                    ox2, oy2 = x2, y2
                    _, x2, y2 = setback_intersect(x1, y1, x2, y2, xo + xa, yo + ya, xo + xb, yo + yb, ins)
                    if ox2 != x2 or oy2 != y2:
                        self.last_tile_hit = (bx, by)
        return x2, y2

    def foreground_intersect_reference(self, x1, y1, x2, y2):
        """Unfiltered version, kept to test that the prefilter changes nothing."""
        tl, th = FORE_W, FORE_H
        bx1, bx2 = (x1, x2) if x1 <= x2 else (x2, x1)
        by1, by2 = (y1, y2) if y1 <= y2 else (y2, y1)
        bx1 = cdiv(bx1 - 2, tl) - 1
        bx2 = cdiv(bx2 + tl + 2, tl) + 1
        by1 = cdiv(by1 - 2, th) - 1
        by2 = cdiv(by2 + th + 2, th) + 1
        if bx2 >= self.width:
            x2 = tl * self.width - 1
        if by2 >= self.height:
            y2 = th * self.height - 1
        bx1 = max(bx1, 0)
        by1 = max(by1, 0)
        if bx1 > bx2 or by1 > by2:
            return x2, y2
        for bx in range(bx1, bx2 + 1):
            for by in range(by1, by2 + 1):
                block = self.get(bx, by)
                if block <= BLACK:
                    continue
                for (xa, ya, xb, yb, ins, *_rest) in self.segments.get(block, ()):
                    _, x2, y2 = setback_intersect(x1, y1, x2, y2, bx * tl + xa, by * th + ya,
                                                  bx * tl + xb, by * th + yb, ins)
        return x2, y2
