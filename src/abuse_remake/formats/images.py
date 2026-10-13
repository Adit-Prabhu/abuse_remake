"""Images, point lists, collision boundaries and character frames.

Sources (historicalsource/abuse@01cce80):
- image layout: imlib/image.c:132 (u16 width, u16 height, width*height palette indices)
- point list:   abuse/src/points.c:17 (u8 count, then count (x, y) byte pairs)
- boundary:     abuse/src/items.c:8 (from file) and :100 (the copy used for the flipped frame);
                they differ only for vertical segments (items.c:42 checks left, :125 checks right)
- figure:       abuse/src/items.c:270 (image, hit_damage, xcfg, advance, damage boundary, hit list)
"""

from __future__ import annotations

from dataclasses import dataclass

from .spec import SPEC_CHARACTER, Reader

TRANSPARENT = 0  # trans_image treats palette index 0 as see-through


@dataclass(frozen=True)
class Image:
    width: int
    height: int
    pixels: bytes  # row-major palette indices

    @classmethod
    def read(cls, r: Reader) -> Image:
        w = r.u16()
        h = r.u16()
        return cls(w, h, r.bytes(w * h))

    def flipped(self) -> Image:
        rows = [self.pixels[y * self.width:(y + 1) * self.width][::-1] for y in range(self.height)]
        return Image(self.width, self.height, b"".join(rows))


@dataclass(frozen=True)
class PointList:
    points: tuple[tuple[int, int], ...]

    @classmethod
    def read(cls, r: Reader) -> PointList:
        tot = r.u8()
        raw = r.bytes(tot * 2)
        return cls(tuple((raw[i], raw[i + 1]) for i in range(0, len(raw), 2)))

    @property
    def tot(self) -> int:
        return len(self.points)


def _inside_flags(points: tuple[tuple[int, int], ...], flipped: bool) -> tuple[int, ...]:
    """Port of boundary::boundary. ``flipped`` selects the copy constructor,
    which differs in one branch: a vertical segment checks right, not left."""
    tot = len(points)
    flags = []
    for i in range(tot - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        checkx = (x1 + x2) // 2
        checky = (y1 + y2) // 2
        segs_left = segs_right = segs_down = 0
        check_left = check_right = check_down = 0
        if y1 == y2:
            check_down = 1
        elif x1 == x2:
            if flipped:
                check_right = 1
            else:
                check_left = 1
        else:
            check_down = 1
            if x1 < x2:
                if y1 < y2:
                    check_left = 1
                else:
                    check_right = 1
            elif y1 < y2:
                check_right = 1
            else:
                check_left = 1
        maxx, minx, miny = max(x1, x2), min(x1, x2), min(y1, y2)
        skip_next = 0
        for j in range(tot - 1):
            if skip_next:
                skip_next = 0
                continue
            if j == i:
                continue
            xp1, yp1 = points[j]
            xp2, yp2 = points[j + 1]
            if (xp1 <= checkx <= xp2) or (xp2 <= checkx <= xp1):
                if check_down and yp1 > miny and yp2 > miny:
                    segs_down = (segs_down + 1) & 0xFF
                if checkx == xp2:
                    skip_next = 1
            elif (yp1 <= checky <= yp2) or (yp2 <= checky <= yp1):
                if check_left and xp1 < maxx and xp2 < maxx:
                    segs_left = (segs_left + 1) & 0xFF
                if check_right and xp1 > minx and xp2 > minx:
                    segs_right = (segs_right + 1) & 0xFF
                if checky == yp2:
                    skip_next = 1
        if not check_down:
            segs_down = 1
        if not check_right:
            segs_right = 1
        if not check_left:
            segs_left = 1
        flags.append(0 if ((segs_left & 1) and (segs_right & 1) and (segs_down & 1)) else 1)
    return tuple(flags)


@dataclass(frozen=True)
class Boundary:
    """A closed polygon whose first and last points coincide."""

    points: tuple[tuple[int, int], ...]
    inside: tuple[int, ...]

    @classmethod
    def from_points(cls, pl: PointList, flipped: bool = False, name: str = "boundary") -> Boundary:
        pts = pl.points
        if pts and pts[0] != pts[-1]:
            raise ValueError(f"{name}: endpoints do not match start points")
        return cls(pts, _inside_flags(pts, flipped))

    @classmethod
    def read(cls, r: Reader, name: str = "boundary") -> Boundary:
        return cls.from_points(PointList.read(r), False, name)

    @property
    def tot(self) -> int:
        return len(self.points)


@dataclass(frozen=True)
class Figure:
    """One animation frame of a character (``figure`` in the original)."""

    image: Image
    hit_damage: int
    xcfg: int  # x centre of gravity: the object's x sits this many pixels into the image
    advance: int  # pixels moved forward when this frame is shown (frame_advance)
    f_damage: Boundary  # where the frame can be hit / blocks others, facing right
    b_damage: Boundary  # same points with the flipped-copy inside rule, facing left
    hit: PointList  # attack line strip; non-empty frames are attack frames

    @classmethod
    def read(cls, r: Reader, etype: int) -> Figure:
        im = Image.read(r)
        hit_damage = r.u8()
        xcfg = r.u8()
        if etype == SPEC_CHARACTER:
            PointList.read(r)  # obsolete "touch" list
            advance = 0
        else:
            advance = r.s8()
        damage_points = PointList.read(r)
        f_damage = Boundary.from_points(damage_points, False, "fig bound")
        b_damage = Boundary.from_points(damage_points, True, "fig bound")
        hit = PointList.read(r)
        return cls(im, hit_damage, xcfg, advance, f_damage, b_damage, hit)

    @property
    def width(self) -> int:
        return self.image.width

    @property
    def height(self) -> int:
        return self.image.height
