"""Neon Protocol art: loads the vendored sprite sheets once and prepares every variant.

Sources and licences: assets/neon/PROVENANCE.md (Ansimuz, Reactorcore). Transforms happen in
memory at load time: slicing sheets, flips, rotations for wall and ceiling poses, the runner's
yellow suit recoloured to cyan for the neon look, white silhouettes for hit flashes. The
files on disk are never modified. Every frame keeps its per-pixel alpha (no black boxes).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pygame as pg

from ...paths import assets_root

ROOT = assets_root() / "neon"


def _key(p: Path):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)]


def load(rel: str) -> pg.Surface:
    return pg.image.load(str(ROOT / rel)).convert_alpha()


def folder(rel: str) -> list[pg.Surface]:
    files = sorted((ROOT / rel).glob("*.png"), key=_key)
    if not files:
        raise FileNotFoundError(f"no frames in assets/neon/{rel}")
    return [pg.image.load(str(f)).convert_alpha() for f in files]


def strip(rel: str, n: int) -> list[pg.Surface]:
    sheet = load(rel)
    w = sheet.get_width() // n
    return [sheet.subsurface((i * w, 0, w, sheet.get_height())).copy() for i in range(n)]


def neon_suit(img: pg.Surface) -> pg.Surface:
    """Recolour strongly yellow/orange pixels (the runner's jacket) to cyan; keep skin and hair."""
    out = img.copy()
    rgb = pg.surfarray.pixels3d(out)
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    mask = (g - b > 70) & (r - b > 90)
    nr = (b * 6 // 10 + 20).clip(0, 255)
    ng = (g * 9 // 10 + 25).clip(0, 255)
    nb = (r * 95 // 100 + 10).clip(0, 255)
    rgb[..., 0] = np.where(mask, nr, r)
    rgb[..., 1] = np.where(mask, ng, g)
    rgb[..., 2] = np.where(mask, nb, b)
    del rgb
    return out


def silhouette(img: pg.Surface, color=(255, 255, 255)) -> pg.Surface:
    out = img.copy()
    rgb = pg.surfarray.pixels3d(out)
    rgb[...] = color
    del rgb
    return out


def flip(img: pg.Surface) -> pg.Surface:
    return pg.transform.flip(img, True, False)


def scale(img: pg.Surface, k: int) -> pg.Surface:
    return pg.transform.scale(img, (img.get_width() * k, img.get_height() * k))


HERO_ANIMS = ("idle", "run", "run-shoot", "jump", "back-jump", "climb", "crouch", "hurt", "shoot")
# tiny weapon art per slot (Eradication Wars micro weapons), projectile and muzzle picks
GUNS = (8, 29, 34, 11, 24)
PROJECTILES = {"pulse": 26, "pellet": 13, "mortar": 21, "seeker": 29, "bolt": 16, "rail": 4, "plasma": 12}
MUZZLES = (14, 17, 31, 4, 11)
ENEMY_MUZZLES = {"acid": 18, "acid2": 42, "plasma": 47, "spark": 36}


class Art:
    def __init__(self):
        self.hero: dict[str, list[pg.Surface]] = {}
        for anim in HERO_ANIMS:
            frames = folder(f"city/SPRITES/player/{anim}")
            self.hero[anim] = [neon_suit(f) for f in frames]
        self.crawler_idle = strip("sideview/Sprites/alien-walking-enemy/PNG/alien-enemy-idle.png", 4)
        self.crawler_walk = strip("sideview/Sprites/alien-walking-enemy/PNG/alien-enemy-walk.png", 6)
        self.stinger = folder("sideview/Sprites/alien-flying-enemy/sprites")
        self.strider = folder("sideview/Sprites/bipedal-Unit/PNG/sprites")
        self.warden = [scale(f, 2) for f in folder("sideview/Sprites/mech-unit/sprites")]
        self.turret = folder("city/SPRITES/misc/turret")
        self.drone = folder("city/SPRITES/misc/drone")
        self.explosion_big = folder("sideview/Sprites/Explosion/sprites")
        self.explosion_small = folder("city/SPRITES/misc/enemy-explosion")
        self.explosion_fire = folder("city2/Sprites/explosion-a")
        self.shot_hit = folder("city/SPRITES/misc/shot-hit")
        self.enemy_burst = folder("city2/Sprites/enemy-shoot")
        self.wall_blast = load("sideview/Sprites/space-marine/PNG/wall-impact-blast.png")
        w = "weapons/Tiny Bonus"
        self.guns = [load(f"{w}/tiny weapons/micro weapon ({n}).png") for n in GUNS]
        self.projectile = {k: load(f"{w}/tiny projectiles/micro projectile ({n}).png") for k, n in PROJECTILES.items()}
        self.muzzles = [load(f"{w}/tiny muzzles/micro muzzle ({n}).png") for n in MUZZLES]
        self.enemy_fx = {k: load(f"{w}/tiny muzzles/micro muzzle ({n}).png") for k, n in ENEMY_MUZZLES.items()}
        props = "sideview/Environments/cyberpunk-detective-prop-files/PNG"
        self.terminal = load(f"{props}/small-terminal.png")
        self.big_computer = load(f"{props}/big-computer.png")
        self.cryo_pod = load(f"{props}/cryo-pod.png")
        self.hanging_terminal = load(f"{props}/hanging-terminal.png")
        self.servers = load(f"{props}/server-gabinetes.png")
        self.lab_props = [load(f"lab/layers/Props/tank-{i}.png") for i in (1, 2, 3)]
        self.monitor = folder("city/ENVIRONMENT/props/monitorface")
        self.banner = folder("city/ENVIRONMENT/props/banner-neon")
        self.banner_big = folder("city/ENVIRONMENT/props/banner-big")
        boxes = [load(f"city/ENVIRONMENT/props/control-box-{i}.png") for i in (1, 2, 3)]
        dim = (150, 155, 175, 255)
        def dimmed(img):
            out = img.copy()
            out.fill(dim, special_flags=pg.BLEND_RGBA_MULT)
            return out
        office = [self.terminal, self.servers, boxes[0], boxes[2], self.big_computer]
        lab = [*self.lab_props, self.servers, boxes[2], self.cryo_pod]
        self.floor_props = {
            "transit": [dimmed(i) for i in office],
            "training": [dimmed(i) for i in office[:4]],
            "horde": [dimmed(i) for i in (self.servers, boxes[0], boxes[2])],
            "reactor": [dimmed(i) for i in lab],
            "hive": [dimmed(i) for i in (self.cryo_pod, *self.lab_props, boxes[1])],
            "core": [dimmed(i) for i in (self.big_computer, self.servers, self.cryo_pod, boxes[2])],
        }
        self.lights = folder("city2/Environment/props/lights")
        self.backdrops = {name: self._backdrop(name) for name in
                          ("transit", "reactor", "hive", "core", "horde", "training")}
        self._white: dict[int, pg.Surface] = {}
        self._flip: dict[int, pg.Surface] = {}
        self._rot: dict[tuple, pg.Surface] = {}
        self._premul: dict[tuple, pg.Surface] = {}

    def _backdrop(self, theme: str) -> list[tuple[pg.Surface, float, int]]:
        """Parallax layers: (image, scroll factor, vertical offset from the view top)."""
        sv = "sideview/Environments"
        if theme == "transit" or theme == "training":
            return [(scale(load("city/ENVIRONMENT/background/skyline-a.png"), 2), 0.08, -40),
                    (scale(load(f"{sv}/cyberpunk-corridor-files/PNG/layers/back.png"), 2), 0.25, 8),
                    (scale(load(f"{sv}/cyberpunk-corridor-files/PNG/layers/cyberpunk-corridor.png"), 1), 0.45, 0)]
        if theme == "reactor":
            return [(scale(load("lab/layers/back.png"), 2), 0.15, -30),
                    (scale(load("lab/layers/middle.png"), 2), 0.35, 30)]
        if theme == "hive":
            return [(scale(load(f"{sv}/alien-environment/PNG/layers/background.png"), 2), 0.12, -10),
                    (scale(load(f"{sv}/alien-environment/PNG/layers/back-structures.png"), 2), 0.3, 20)]
        if theme == "core":
            return [(scale(load(f"{sv}/sci-fi-environment-background-files/PNG/sky.png"), 2), 0.1, -20),
                    (scale(load(f"{sv}/bulkhead-walls/PNG/bg-wall-with-supports.png"), 2), 0.35, 0)]
        return [(scale(load(f"{sv}/sci-fi-environment-background-files/PNG/back.png"), 2), 0.15, 0),
                (scale(load("city2/Environment/background/middle.png"), 2), 0.3, 40)]

    # --- variants ---
    def flipped(self, img: pg.Surface) -> pg.Surface:
        got = self._flip.get(id(img))
        if got is None:
            got = self._flip[id(img)] = flip(img)
        return got

    def premul(self, img: pg.Surface, alpha: int = 255, cache: bool = True) -> pg.Surface:
        """``img`` composited onto black: safe to add to the glow layer (transparent stays black).
        Pass ``cache=False`` for temporary surfaces (ids of temporaries are reused)."""
        key = (id(img), alpha)
        got = self._premul.get(key) if cache else None
        if got is None:
            got = pg.Surface(img.get_size())
            got.fill((0, 0, 0))
            src = img
            if alpha < 255:
                src = img.copy()
                src.fill((255, 255, 255, alpha), special_flags=pg.BLEND_RGBA_MULT)
            got.blit(src, (0, 0))
            if cache:
                if len(self._premul) > 3000:
                    self._premul.clear()
                self._premul[key] = got
        return got

    def flash(self, img: pg.Surface, amount: int = 160) -> pg.Surface:
        """A copy of ``img`` brightened toward white (hit flash); not cached."""
        out = img.copy()
        out.blit(self.premul(silhouette(img), amount, cache=False), (0, 0), special_flags=pg.BLEND_RGB_ADD)
        return out

    def white(self, img: pg.Surface) -> pg.Surface:
        got = self._white.get(id(img))
        if got is None:
            got = self._white[id(img)] = silhouette(img)
        return got

    def rot(self, img: pg.Surface, angle: int, flip_v: bool = False) -> pg.Surface:
        """``img`` (pointing right) turned to ``angle`` on the 1024 circle, in 32 cached steps."""
        step = round(angle * 32 / 1024) % 32
        key = (id(img), step, flip_v)
        got = self._rot.get(key)
        if got is None:
            src = pg.transform.flip(img, False, True) if flip_v else img
            got = self._rot[key] = pg.transform.rotate(src, -step * 360 / 32)
        return got

    def gun(self, slot: int, aim: int) -> pg.Surface:
        """The held gun turned to the aim; mirrored when aiming left so it is never upside down."""
        step = round(aim * 32 / 1024) % 32
        return self.rot(self.guns[slot], aim, flip_v=8 < step < 24)

    def projectile_img(self, kind: str, angle: int) -> pg.Surface | None:
        img = self.projectile.get(kind)
        return None if img is None else self.rot(img, angle)

    def muzzle(self, slot: int, angle: int) -> pg.Surface:
        return self.rot(self.muzzles[slot], angle)
