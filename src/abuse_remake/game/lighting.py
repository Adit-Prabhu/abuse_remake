"""Light map for the visible area, following the original's light model.

historicalsource/abuse@01cce80 abuse/src/light.c:
- ambient runs 0..63; 63 means no darkening (``light_screen``: ``if (ambient==63) return``);
- each light covers a box from ``calc_range``: type 0 is a full ellipse, 1-8 are halves and
  quadrants, 9 is a rectangle; ``xshift``/``yshift`` squash the radius;
- brightness is full inside ``inner_radius`` and falls linearly to the ambient level at
  ``outer_radius`` (``mul_div=(1<<16)/(outer-inner)*64``).

We compute the same map with numpy at the view's size, but smooth instead of the original's
palette-step look. The renderer can add modern glow on top. Lighting never affects rules.
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


def light_map(lights, ambient: int, xoff: float, yoff: float, w: int, h: int,
              extra=()) -> np.ndarray:
    """Return an (h, w) float32 array of brightness 0..1 for the screen area at (xoff, yoff).

    ``extra`` holds (x, y, radius, strength) dynamic lights such as muzzle flashes."""
    amb = max(0, min(63, ambient))
    lm = np.full((h, w), amb / 63.0, dtype=np.float32)
    if amb >= 63 and not extra:
        return lm
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    gx = xs + xoff
    gy = ys + yoff
    for light in lights:
        x1, y1, x2, y2 = _box(light)
        if x2 < xoff or x1 > xoff + w or y2 < yoff or y1 > yoff + h:
            continue
        sx1, sy1 = max(0, int(x1 - xoff)), max(0, int(y1 - yoff))
        sx2, sy2 = min(w, int(x2 - xoff) + 1), min(h, int(y2 - yoff) + 1)
        if sx1 >= sx2 or sy1 >= sy2:
            continue
        sub_x = gx[sy1:sy2, sx1:sx2] - light.x
        sub_y = gy[sy1:sy2, sx1:sx2] - light.y
        if light.type == 9:
            b = np.ones_like(sub_x)
        else:
            dx = sub_x * float(1 << max(0, light.xshift))
            dy = sub_y * float(1 << max(0, light.yshift))
            d = np.sqrt(dx * dx + dy * dy)
            inner, outer = light.inner_radius, max(light.outer_radius, light.inner_radius + 1)
            b = np.clip((outer - d) / float(outer - inner), 0.0, 1.0)
        region = lm[sy1:sy2, sx1:sx2]
        np.maximum(region, b, out=region)
    for (x, y, r, strength) in extra:
        cx, cy = x - xoff, y - yoff
        d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
        b = np.clip(1.0 - d / max(1.0, r), 0.0, 1.0) * strength
        np.maximum(lm, b, out=lm)
    return lm
