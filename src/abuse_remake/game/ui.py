"""The look of Remastered's screens, made from the original game's own interface art.

- Text: the original 8x8 font (``letters``) for headings and labels, and its 5x7 ``small_font``
  for longer lines (``art/fonts.spe``). Both are one colour on a clear background, so any colour
  can be drawn from them.
- Panels: the original window texture (``window_texture``, ``art/frame.spe``) with bevels in the
  original window colours (``window_colors``: grey, rust and a deep shade), and bolts at the
  corners.
- Icons: the game's own sprites (power-ups, pickups, weapons from ``art/statbar.spe``).

Everything is measured in game pixels (``unit`` screen pixels each), so the interface keeps the
pixel size of the world it sits on. Presentation only: nothing here changes a rule.
"""

from __future__ import annotations

import numpy as np
import pygame

from ..formats.images import Image
from ..formats.spec import SPEC_IMAGE, SpecFile
from ..paths import data_root

# window_colors (art/frame.spe), row by row: grey, rust and deep shades, light to dark
GREY = ((103, 103, 103), (67, 67, 67), (43, 43, 43))
RUST = ((95, 79, 67), (83, 67, 51), (63, 51, 35))
DEEP = ((23, 15, 23), (19, 11, 19), (15, 11, 15))
TEXT = (222, 214, 198)
DIM = (150, 142, 128)
AMBER = (255, 188, 84)
ORANGE = (255, 138, 40)
RED = (232, 70, 52)
GREEN = (120, 210, 92)
CYAN = (130, 214, 240)
SHADOW = (8, 6, 8)
# characters the original font has, at their code page 437 places
CP437 = {"\u2191": 24, "\u2193": 25, "\u2192": 26, "\u2190": 27, "\u221e": 236, "\u2665": 3, "\u00b7": 250,
         "\u2022": 7, "\u25c4": 17, "\u25ba": 16}


def _indices(file: str, name: str) -> np.ndarray:
    spec = SpecFile.open(data_root() / file)
    entry = spec.find(name, SPEC_IMAGE)
    im = Image.read(spec.reader(entry))
    return np.frombuffer(im.pixels, dtype=np.uint8).reshape(im.height, im.width)


# The 5x7 font has nothing in its first row (code page 437's arrows and card suits). These are
# drawn for it here, in its own weight, for the keys and prompts that need them.
SMALL_EXTRAS = {
    16: ("#....", "##...", "###..", "####.", "###..", "##...", "#...."),
    17: ("...#.", "..##.", ".###.", "####.", ".###.", "..##.", "...#."),
    24: ("..#..", ".###.", "#.#.#", "..#..", "..#..", "..#..", "....."),
    25: ("..#..", "..#..", "..#..", "#.#.#", ".###.", "..#..", "....."),
    26: (".....", "..#..", "...#.", "#####", "...#.", "..#..", "....."),
    27: (".....", "..#..", ".#...", "#####", ".#...", "..#..", "....."),
    3: (".#.#.", "#####", "#####", ".###.", "..#..", ".....", "....."),
}


class PixelFont:
    """A 32x8 grid of glyphs in code page 437 order, drawn in any colour at a whole scale."""

    def __init__(self, name: str, cell_w: int, cell_h: int, extras: dict | None = None):
        self.ink = _indices("art/fonts.spe", name) != 0
        self.w, self.h = cell_w, cell_h
        for code, rows in (extras or {}).items():
            row, col = divmod(code, 32)
            self.ink[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w] = \
                np.array([[ch == "#" for ch in r] for r in rows], dtype=bool)
        self.cache: dict = {}

    def size(self, text: str, scale: int = 1) -> tuple[int, int]:
        return len(text) * self.w * scale, self.h * scale

    def render(self, text: str, color, scale: int = 1) -> pygame.Surface:
        key = (text, tuple(color), scale)
        got = self.cache.get(key)
        if got is not None:
            return got
        ink = np.zeros((self.h, max(1, len(text)) * self.w), dtype=bool)
        for i, ch in enumerate(text):
            c = CP437.get(ch, ord(ch) if ord(ch) < 256 else ord("?"))
            row, col = divmod(c, 32)
            ink[:, i * self.w:(i + 1) * self.w] = self.ink[row * self.h:(row + 1) * self.h,
                                                           col * self.w:(col + 1) * self.w]
        if scale > 1:
            ink = ink.repeat(scale, axis=0).repeat(scale, axis=1)
        rgba = np.zeros((*ink.shape, 4), dtype=np.uint8)
        rgba[ink] = (*color[:3], 255)
        surf = pygame.image.frombuffer(rgba.tobytes(), (ink.shape[1], ink.shape[0]), "RGBA").copy()
        if len(self.cache) > 600:
            self.cache.clear()
        self.cache[key] = surf
        return surf


class Theme:
    def __init__(self, sprites, unit: int):
        self.sprites = sprites
        self.u = max(1, int(unit))
        self.big = PixelFont("letters", 8, 8)
        self.small = PixelFont("small_font", 5, 7, SMALL_EXTRAS)
        tex = _indices("art/frame.spe", "window_texture")
        self._texture = self._gray_surface(tex)
        self._tex_scaled: pygame.Surface | None = None
        self._icons: dict = {}

    @staticmethod
    def _gray_surface(idx: np.ndarray) -> pygame.Surface:
        from ..formats.tiles import load_palette

        pal = np.array(load_palette(data_root()).colors, dtype=np.uint8)
        rgb = pal[idx]
        return pygame.image.frombuffer(np.ascontiguousarray(rgb).tobytes(), (idx.shape[1], idx.shape[0]),
                                       "RGB").copy()

    # --- text ------------------------------------------------------------------------------------
    def font(self, size: str) -> PixelFont:
        return self.big if size == "big" else self.small

    def measure(self, text: str, size: str = "small", scale: int = 1) -> tuple[int, int]:
        w, h = self.font(size).size(text, scale * self.u)
        return w, h

    def text(self, surf, text: str, pos, color=TEXT, size: str = "small", scale: int = 1,
             align: str = "left", shadow: bool = True) -> pygame.Rect:
        """Draw ``text`` with its top at ``pos``; ``align`` places ``pos`` at its left, centre or
        right. Returns the rectangle drawn."""
        font = self.font(size)
        s = scale * self.u
        img = font.render(text, color, s)
        x, y = pos
        if align == "center":
            x -= img.get_width() // 2
        elif align == "right":
            x -= img.get_width()
        if shadow:
            surf.blit(font.render(text, SHADOW, s), (x + s, y + s))
        surf.blit(img, (x, y))
        return pygame.Rect(x, y, img.get_width(), img.get_height())

    def wrap(self, text: str, width: int, size: str = "small", scale: int = 1) -> list[str]:
        """Split ``text`` into lines no wider than ``width`` screen pixels."""
        per = max(1, width // (self.font(size).w * scale * self.u))
        lines, line = [], ""
        for word in text.split():
            if line and len(line) + 1 + len(word) > per:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}" if line else word
        if line:
            lines.append(line)
        return lines

    # --- panels ----------------------------------------------------------------------------------
    def texture(self) -> pygame.Surface:
        if self._tex_scaled is None:
            t = self._texture
            self._tex_scaled = pygame.transform.scale(t, (t.get_width() * self.u, t.get_height() * self.u))
        return self._tex_scaled

    def panel(self, surf, rect: pygame.Rect, accent=None, bolts: bool = True) -> None:
        """A window in the original's style: its texture, a deep outline, a grey bevel lit from the
        top left, a rust inner line (or ``accent``), and bolts in the corners."""
        u = self.u
        r = pygame.Rect(rect)
        clip = surf.get_clip()
        surf.set_clip(r.clip(clip) if clip else r)
        tex = self.texture()
        tw, th = tex.get_size()
        for y in range(r.top, r.bottom, th):
            for x in range(r.left, r.right, tw):
                surf.blit(tex, (x, y))
        surf.set_clip(clip)
        pygame.draw.rect(surf, DEEP[2], r, u)
        inner = r.inflate(-2 * u, -2 * u)
        pygame.draw.rect(surf, GREY[0], (inner.left, inner.top, inner.width, u))
        pygame.draw.rect(surf, GREY[0], (inner.left, inner.top, u, inner.height))
        pygame.draw.rect(surf, GREY[2], (inner.left, inner.bottom - u, inner.width, u))
        pygame.draw.rect(surf, GREY[2], (inner.right - u, inner.top, u, inner.height))
        line = inner.inflate(-2 * u, -2 * u)
        pygame.draw.rect(surf, accent or RUST[1], line, u)
        if accent:
            pygame.draw.rect(surf, accent, r.inflate(2 * u, 2 * u), u)
        if bolts and r.width > 16 * u and r.height > 16 * u:
            for bx, by in ((line.left + 2 * u, line.top + 2 * u), (line.right - 4 * u, line.top + 2 * u),
                           (line.left + 2 * u, line.bottom - 4 * u), (line.right - 4 * u, line.bottom - 4 * u)):
                pygame.draw.rect(surf, GREY[1], (bx, by, 2 * u, 2 * u))
                pygame.draw.rect(surf, GREY[0], (bx, by, u, u))

    def plate(self, surf, rect: pygame.Rect, alpha: int = 200) -> None:
        """A see-through dark strip with a thin rust edge, for text over the game."""
        r = pygame.Rect(rect)
        shade = pygame.Surface(r.size, pygame.SRCALPHA)
        shade.fill((*DEEP[2], alpha))
        surf.blit(shade, r.topleft)
        pygame.draw.rect(surf, RUST[2], r, max(1, self.u // 2 or 1))

    def dim(self, surf, alpha: int = 170) -> None:
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((*DEEP[2], alpha))
        surf.blit(shade, (0, 0))

    def bar(self, surf, rect: pygame.Rect, frac: float, color, back=DEEP[0]) -> None:
        """A meter: a deep well with a grey rim, filled to ``frac`` with a lit top edge."""
        u = self.u
        r = pygame.Rect(rect)
        pygame.draw.rect(surf, GREY[2], r)
        well = r.inflate(-2 * u, -2 * u)
        pygame.draw.rect(surf, back, well)
        w = int(well.width * max(0.0, min(1.0, frac)))
        if w > 0:
            pygame.draw.rect(surf, color, (well.left, well.top, w, well.height))
            lit = tuple(min(255, c + 60) for c in color)
            pygame.draw.rect(surf, lit, (well.left, well.top, w, u))

    def key(self, surf, label: str, pos, color=TEXT) -> pygame.Rect:
        """A keyboard key with ``label`` on it, top left at ``pos``."""
        u = self.u
        tw, th = self.measure(label)
        r = pygame.Rect(pos[0], pos[1], tw + 6 * u, th + 5 * u)
        pygame.draw.rect(surf, DEEP[2], r)
        pygame.draw.rect(surf, GREY[1], r.inflate(-2 * u, -2 * u))
        pygame.draw.rect(surf, GREY[0], (r.left + u, r.top + u, r.width - 2 * u, u))
        pygame.draw.rect(surf, GREY[2], (r.left + u, r.bottom - 2 * u, r.width - 2 * u, u))
        self.text(surf, label, (r.left + 3 * u, r.top + 2 * u), color, shadow=False)
        return r

    def keys_line(self, surf, parts, pos, align: str = "left") -> pygame.Rect:
        """A line of text with keys in it: ``parts`` alternate plain text and ``("key", label)``."""
        u = self.u
        widths = []
        for p in parts:
            if isinstance(p, tuple):
                widths.append(self.measure(p[1])[0] + 6 * u + 2 * u)
            else:
                widths.append(self.measure(p)[0] + 2 * u)
        total = sum(widths)
        x, y = pos
        if align == "center":
            x -= total // 2
        elif align == "right":
            x -= total
        start = x
        for p, w in zip(parts, widths, strict=True):
            if isinstance(p, tuple):
                self.key(surf, p[1], (x, y - 2 * u))
            else:
                self.text(surf, p, (x, y))
            x += w
        return pygame.Rect(start, y - 2 * u, total, self.measure("X")[1] + 5 * u)

    # --- icons -----------------------------------------------------------------------------------
    def icon(self, file: str, name: str, scale: int = 1) -> pygame.Surface | None:
        key = ("img", file, name, scale)
        if key not in self._icons:
            img = self.sprites.image(file, name) if self.sprites else None
            if img is not None:
                s = scale * self.u
                img = pygame.transform.scale(img, (img.get_width() * s, img.get_height() * s))
            self._icons[key] = img
        return self._icons[key]

    def figure(self, world, type_name: str, state: str = "stopped", scale: int = 1) -> pygame.Surface | None:
        key = ("fig", type_name, state, scale)
        if key not in self._icons:
            img = None
            ct = world.types.get(type_name)
            seq = ct.sequences.get(state) if ct is not None else None
            if seq and self.sprites:
                img, _ = self.sprites.figure(seq[0])
                s = scale * self.u
                img = pygame.transform.scale(img, (img.get_width() * s, img.get_height() * s))
            self._icons[key] = img
        return self._icons[key]
