"""Turn the original palette-indexed art into pygame surfaces, cached.

Index 0 is transparent in sprites (``trans_image``); tiles draw opaque except foreground tiles,
which are also transparent images in the original (``foretile`` is a ``trans_image``).
"""

from __future__ import annotations

import numpy as np
import pygame

from ..formats.images import Figure, Image
from ..formats.spec import SPEC_IMAGE, SpecFile
from ..formats.tiles import load_palette
from ..paths import data_root


class SpriteCache:
    def __init__(self):
        pal = load_palette(data_root())
        self.palette = np.array(pal.colors, dtype=np.uint8)
        self._figs: dict[int, tuple[pygame.Surface, pygame.Surface]] = {}
        self._tiles: dict[tuple[str, int], pygame.Surface] = {}
        self._images: dict[tuple[str, str], pygame.Surface] = {}
        self._specs: dict[str, SpecFile] = {}

    def _surface(self, im: Image, transparent: bool) -> pygame.Surface:
        idx = np.frombuffer(im.pixels, dtype=np.uint8).reshape(im.height, im.width)
        rgba = np.empty((im.height, im.width, 4), dtype=np.uint8)
        rgba[..., :3] = self.palette[idx]
        rgba[..., 3] = np.where(idx == 0, 0, 255) if transparent else 255
        surf = pygame.image.frombuffer(rgba.tobytes(), (im.width, im.height), "RGBA").copy()
        if pygame.display.get_init() and pygame.display.get_surface() is not None:
            surf = surf.convert_alpha()
        return surf

    def figure(self, fig: Figure) -> tuple[pygame.Surface, pygame.Surface]:
        key = id(fig)
        got = self._figs.get(key)
        if got is None:
            fwd = self._surface(fig.image, True)
            got = (fwd, pygame.transform.flip(fwd, True, False))
            self._figs[key] = got
        return got

    def fore_tile(self, tiles, num: int) -> pygame.Surface | None:
        key = ("f", num)
        got = self._tiles.get(key)
        if got is None:
            t = tiles.fore.get(num)
            if t is None:
                return None
            got = self._tiles[key] = self._surface(t.image, True)
        return got

    def back_tile(self, tiles, num: int) -> pygame.Surface | None:
        key = ("b", num)
        got = self._tiles.get(key)
        if got is None:
            t = tiles.back.get(num)
            if t is None:
                return None
            got = self._tiles[key] = self._surface(t.image, False)
        return got

    def image(self, file: str, name: str) -> pygame.Surface | None:
        key = (file, name)
        got = self._images.get(key)
        if got is None:
            spec = self._specs.get(file)
            if spec is None:
                spec = self._specs[file] = SpecFile.open(data_root() / file)
            e = spec.find(name, SPEC_IMAGE)
            if e is None:
                return None
            got = self._images[key] = self._surface(Image.read(spec.reader(e)), True)
        return got
