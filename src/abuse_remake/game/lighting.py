"""Light levels for the visible area, following the original's light model.

historicalsource/abuse@01cce80 abuse/src/light.c:
- the level starts at ``min_light_level``: the ambient level clamped to 0..63; 63 means no
  darkening (``light_screen``: ``if (ambient==63) return``), light.c:835-842;
- each light covers a box from ``calc_range``: type 0 is a full ellipse, 1-8 are halves and
  quadrants, 9 is a rectangle;
- ``calc_light_value`` (light.c:695-740): for each light, ``dx`` and ``dy`` are shifted left by
  ``xshift``/``yshift``, the distance is the octagonal ``dx + dy - min(dx, dy) / 2``, and a light
  closer than ``outer_radius`` adds ``(outer - r2) * mul_div >> 16`` with
  ``mul_div = (1 << 16) / (outer - inner) * 64`` (light.c:134). The sum is capped at 63. A type-9
  rectangle returns its ``inner_radius`` as the level;
- the level darkens each pixel through the ``white_light`` table (light.c:230-245): each of the
  palette's 8-bit channels loses ``63 - level``, then the nearest palette colour is used.

``light_levels`` computes the same integer levels per pixel (the original works in 4x4-pixel
patches). Classic darkens each channel by ``63 - level`` without snapping back to the palette;
Remastered uses a smoother curve and adds muzzle-flash and explosion light. Lighting never
affects rules.
"""

from __future__ import annotations

import numpy as np


def _box(light):
    x, y, r, xs, ys = light.x, light.y, light.outer_radius, light.xshift, light.yshift
    rx, ry = r >> xs if xs >= 0 else r, r >> ys if ys >= 0 else r
    t = light.type
    if t == 0:
        return x - rx, y - ry, x + rx, y + ry
    if t == 1:
        return x - rx, y - ry, x + rx, y
    if t == 2:
        return x - rx, y, x + rx, y + ry
    if t == 3:
        return x, y - ry, x + rx, y + ry
    if t == 4:
        return x - rx, y - ry, x, y + ry
    if t == 5:
        return x, y - ry, x + rx, y
    if t == 6:
        return x - rx, y - ry, x, y
    if t == 7:
        return x - rx, y, x, y + ry
    if t == 8:
        return x, y, x + rx, y + ry
    return x, y, x + light.xshift, y + light.yshift  # type 9: rectangle


def mul_div(light) -> int:
    span = light.outer_radius - light.inner_radius
    return ((1 << 16) // span) * 64 if span > 0 else 1 << 22  # light.c:134 (C integer division)


def light_levels(lights, ambient: int, xoff: float, yoff: float, w: int, h: int) -> np.ndarray:
    """An (h, w) int32 array of light levels 0..63 for the screen area at (xoff, yoff)."""
    base = max(0, min(63, int(ambient)))
    lv = np.full((h, w), base, dtype=np.int32)
    if base >= 63:
        return lv
    ys, xs = np.mgrid[0:h, 0:w]
    gx = xs + int(round(xoff))
    gy = ys + int(round(yoff))
    solid = np.full((h, w), -1, dtype=np.int32)
    for light in lights:
        x1, y1, x2, y2 = _box(light)
        if x2 < xoff or x1 > xoff + w or y2 < yoff or y1 > yoff + h:
            continue
        sx1, sy1 = max(0, int(x1 - xoff)), max(0, int(y1 - yoff))
        sx2, sy2 = min(w, int(x2 - xoff) + 1), min(h, int(y2 - yoff) + 1)
        if sx1 >= sx2 or sy1 >= sy2:
            continue
        if light.type == 9:
            region = solid[sy1:sy2, sx1:sx2]
            region[region < 0] = light.inner_radius  # the first rectangle in the list wins
            continue
        dx = np.abs(gx[sy1:sy2, sx1:sx2] - light.x) << max(0, light.xshift)
        dy = np.abs(gy[sy1:sy2, sx1:sx2] - light.y) << max(0, light.yshift)
        r2 = dx + dy - (np.minimum(dx, dy) >> 1)  # the octagonal distance
        add = np.where(r2 < light.outer_radius, ((light.outer_radius - r2) * mul_div(light)) >> 16, 0)
        lv[sy1:sy2, sx1:sx2] += add
    np.minimum(lv, 63, out=lv)
    return np.where(solid >= 0, np.minimum(solid, 63), lv)


def flash_map(flashes, xoff: float, yoff: float, w: int, h: int) -> np.ndarray:
    """Remastered only: (x, y, radius, strength) dynamic lights as brightness 0..1."""
    out = np.zeros((h, w), dtype=np.float32)
    if not flashes:
        return out
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    for (x, y, r, strength) in flashes:
        d = np.sqrt((xs - (x - xoff)) ** 2 + (ys - (y - yoff)) ** 2)
        np.maximum(out, np.clip(1.0 - d / max(1.0, r), 0.0, 1.0) * strength, out=out)
    return out


def light_map(lights, ambient: int, xoff: float, yoff: float, w: int, h: int, extra=()) -> np.ndarray:
    """Brightness 0..1 (the level / 63, raised by any Remastered flashes)."""
    lm = light_levels(lights, ambient, xoff, yoff, w, h).astype(np.float32) / 63.0
    if extra:
        np.maximum(lm, flash_map(extra, xoff, yoff, w, h), out=lm)
    return lm
