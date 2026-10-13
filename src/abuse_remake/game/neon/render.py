"""Neon Protocol world renderer. Reads the simulation; never changes it.

Pipeline per frame (640x360 scene):
1. parallax backdrop art per sector theme;
2. cached tile chunks: dark panels with bevels and a back-wall grid;
3. doors, cracked walls, hazards, props, pickups, actors, shots, particles;
4. lighting: an ambient-dark light map with lamps, muzzle flashes, shots and explosions,
   multiplied over the scene (the Abuse dark-corridor mood);
5. emissive layer: neon tile edges, beams, projectiles, eyes and screens, added on top, plus a
   two-level bloom.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pygame as pg

from ...engine.neon.fixed import COS, SIN
from ...engine.neon.objects import hazard_live, hazard_warning
from ...engine.neon.tilemap import BREAK, DOOR, HAZARD, LADDER, ONEWAY, RAIL, SOLID
from .assets import Art

SCENE_W, SCENE_H = 640, 360
CHUNK = 256
THEMES = {
    "transit": {"edge": (70, 235, 245), "edge2": (237, 87, 221), "fill": (16, 22, 38), "panel": (24, 33, 54),
                "wall": (8, 12, 24), "ambient": (78, 86, 118), "lamp": (150, 225, 255)},
    "reactor": {"edge": (255, 170, 70), "edge2": (60, 230, 200), "fill": (24, 20, 26), "panel": (40, 32, 36),
                "wall": (12, 10, 14), "ambient": (90, 76, 70), "lamp": (255, 200, 140)},
    "hive": {"edge": (140, 255, 90), "edge2": (190, 90, 255), "fill": (14, 22, 18), "panel": (22, 36, 28),
             "wall": (6, 12, 10), "ambient": (52, 64, 58), "lamp": (170, 255, 150)},
    "core": {"edge": (255, 70, 100), "edge2": (240, 240, 255), "fill": (24, 14, 22), "panel": (40, 24, 34),
             "wall": (12, 6, 12), "ambient": (90, 66, 80), "lamp": (255, 150, 170)},
    "horde": {"edge": (70, 235, 245), "edge2": (255, 190, 80), "fill": (16, 20, 34), "panel": (26, 32, 52),
              "wall": (8, 10, 22), "ambient": (84, 88, 116), "lamp": (160, 230, 255)},
    "training": {"edge": (70, 235, 245), "edge2": (120, 255, 170), "fill": (16, 24, 36), "panel": (26, 38, 56),
                 "wall": (10, 16, 28), "ambient": (120, 130, 160), "lamp": (170, 235, 255)},
}
PICKUP_COLORS = {"health": (90, 255, 150), "ammo": (255, 205, 110), "shield": (80, 210, 255),
                 "overcharge": (255, 80, 220), "haste": (255, 200, 70), "phase": (170, 120, 255),
                 "boots": (120, 255, 240), "key_red": (255, 70, 70), "key_gold": (255, 205, 60)}
WEAPON_COLORS = ((80, 230, 255), (255, 90, 200), (140, 240, 255), (120, 160, 255), (255, 170, 80))
SHOT_COLORS = {"pulse": (80, 230, 255), "pellet": (255, 90, 200), "mortar": (120, 160, 255),
               "seeker": (255, 170, 80), "acid": (140, 255, 80), "bolt": (255, 140, 60), "plasma": (255, 80, 120),
               "shock": (255, 120, 80)}
DOOR_COLORS = {"red": (255, 60, 70), "gold": (255, 200, 60)}


def _lerp(a, b, t):
    return a + (b - a) * t


def _radial(radius: int, color) -> pg.Surface:
    size = radius * 2
    yy, xx = np.mgrid[-1:1:complex(0, size), -1:1:complex(0, size)]
    fall = np.clip(1 - np.sqrt(xx * xx + yy * yy), 0, 1) ** 1.6
    rgb = (fall[..., None] * np.array(color, dtype=np.float32)).astype(np.uint8)
    return pg.image.frombuffer(np.ascontiguousarray(rgb.transpose(1, 0, 2)).tobytes(), (size, size), "RGB").copy()


class WorldRenderer:
    def __init__(self, art: Art | None = None):
        self.art = art or Art()
        self.scene = pg.Surface((SCENE_W, SCENE_H))
        self.glow = pg.Surface((SCENE_W, SCENE_H))
        self.lightmap = pg.Surface((SCENE_W // 4, SCENE_H // 4))
        self.small = pg.font.Font(None, 14)
        self.map_id = None
        self.chunks: dict[tuple[int, int], tuple[pg.Surface, pg.Surface]] = {}
        self.prev: dict[int, tuple[int, int]] = {}
        self.cur: dict[int, tuple[int, int]] = {}
        self.cam = (0.0, 0.0)
        self.cam_vel = (0.0, 0.0)
        self.last_camera = (0.0, 0.0)
        self.shake = 0.0
        self.time = 0.0
        self.particles: list[list] = []  # [x, y, vx, vy, life, max, color, kind, size]
        self.decals: list[list] = []  # [x, y, w, color, life]
        self.anims: list[list] = []  # [frames, x, y, t, fps, scale, glow]
        self.lights: list[list] = []  # [x, y, radius, color, life, max]
        self.beams: list[list] = []  # [x1, y1, x2, y2, life, color]
        self.muzzle: list = []  # [slot, x, y, angle, life]
        self.trail: list[list] = []  # dash after-images [x, y, img, life]
        self.explored: np.ndarray | None = None
        self.rng = random.Random(7)
        self._light_cache: dict = {}
        self.lighting = True
        self.bloom = True

    # ------------------------------------------------------------ state from the game
    def reset(self, game) -> None:
        if self.map_id != (game.map.name, id(game.map)):
            self.map_id = (game.map.name, id(game.map))
            self.chunks.clear()
            self.theme = THEMES.get(game.map.theme, THEMES["transit"])
            self.dynamic_tiles = [(i % game.map.width, i // game.map.width, c) for i, c in enumerate(game.map.tiles)
                                  if c in (DOOR, BREAK, HAZARD)]
            self.explored = np.zeros((game.map.height, game.map.width), dtype=bool)
            self.backdrop = self.art.backdrops.get(game.map.theme, self.art.backdrops["transit"])
            self.props, self.wall_props = self._decorate(game)
        self.cur = self._positions(game)
        self.prev = dict(self.cur)
        self.cam = self._cam_target(game)
        self.cam_vel = (0.0, 0.0)
        self.particles.clear()
        self.anims.clear()
        self.lights.clear()
        self.beams.clear()
        self.trail.clear()
        self.muzzle = []

    @staticmethod
    def _positions(game) -> dict:
        out = {0: (game.player.x, game.player.y)}
        for e in game.enemies:
            out[e.uid] = (e.x, e.y)
        for i, el in enumerate(game.elevators):
            out[-1 - i] = (el.x, el.y)
        return out

    def _cam_target(self, game) -> tuple[float, float]:
        p = game.player
        sx, sy = p.shoulder()
        ax = max(-90, min(90, (game_aim(game)[0] - sx))) * 0.35
        ay = max(-70, min(70, (game_aim(game)[1] - sy))) * 0.3
        tx = p.cx + ax - SCENE_W / 2
        ty = p.cy - 20 + ay - SCENE_H / 2
        return (max(0.0, min(game.width - SCENE_W, tx)), max(0.0, min(game.height - SCENE_H, ty)))

    def note_tick(self, game) -> None:
        """Call after every simulation tick."""
        self.prev, self.cur = self.cur, self._positions(game)
        p = game.player
        if self.explored is not None:
            tx, ty = p.cx >> 4, p.cy >> 4
            self.explored[max(0, ty - 10):ty + 11, max(0, tx - 16):tx + 17] = True
        for e in game.events:
            self._event(game, e)
        if p.dash_t and game.frames % 2 == 0:
            self.trail.append([p.x, p.y, None, 0.25])

    def _event(self, game, e) -> None:
        k, x, y = e["kind"], e["x"], e["y"]
        r = self.rng
        th = self.theme
        if k == "shot":
            self.muzzle = [e["weapon"], x, y, e["angle"], 0.07]
            self.lights.append([x, y, 70, WEAPON_COLORS[e["weapon"]], 0.08, 0.08])
            if e["weapon"] in (2, 3):
                self.shake = max(self.shake, 2.5)
        elif k == "rail":
            self.beams.append([x, y, e["x2"], e["y2"], 0.22, (150, 245, 255)])
            self.lights.append([(x + e["x2"]) / 2, (y + e["y2"]) / 2, 160, (120, 220, 255), 0.15, 0.15])
            self._sparks(e["x2"], e["y2"], 10, (180, 250, 255))
            self.shake = max(self.shake, 3)
        elif k == "explosion":
            big = e["radius"] >= 40
            frames = self.art.explosion_big if big else self.art.explosion_fire
            self.anims.append([frames, x, y, 0.0, 22, 1 if big else 1, True])
            self.lights.append([x, y, e["radius"] * 4, (255, 170, 90), 0.45, 0.45])
            self.shake = max(self.shake, 7 if big else 4)
            self.decals.append([x, self._floor_below(game, x, y), e["radius"], (12, 10, 12), 12.0])
            for _ in range(18):
                a = r.uniform(0, math.tau)
                s = r.uniform(40, 200)
                self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s - 60, 0.6, 0.6, (255, 190, 90),
                                       "spark", 1])
        elif k == "impact":
            col = SHOT_COLORS.get(e.get("shot"), (255, 255, 255))
            self._sparks(x, y, 5, col)
            if e.get("wall"):
                self.anims.append([self.art.shot_hit, x, y, 0.0, 30, 1, True])
        elif k == "hit":
            col = (150, 255, 90) if e.get("enemy") in ("crawler", "nest", "stinger") else (255, 210, 120)
            self._sparks(x, y, 6, col)
        elif k == "deflect":
            self._sparks(x, y, 8, (180, 230, 255))
            self.lights.append([x, y, 50, (120, 200, 255), 0.1, 0.1])
        elif k == "kill":
            kind = e.get("enemy")
            if kind in ("crawler", "stinger", "nest"):
                self._gibs(x, y, 16 if kind != "nest" else 24)
                self.decals.append([x, self._floor_below(game, x, y), 22, (60, 140, 40), 20.0])
                self.anims.append([self.art.explosion_small, x, y, 0.0, 24, 1, True])
            else:
                big = kind in ("strider", "warden")
                self.anims.append([self.art.explosion_big if big else self.art.explosion_fire, x, y, 0.0, 20,
                                   2 if kind == "warden" else 1, True])
                self.lights.append([x, y, 220 if big else 120, (255, 160, 80), 0.5, 0.5])
                self.shake = max(self.shake, 10 if big else 4)
                for _ in range(14):
                    a = r.uniform(0, math.tau)
                    s = r.uniform(60, 220)
                    self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s - 90, 1.0, 1.0, (90, 90, 100),
                                           "debris", 2])
        elif k == "break":
            for _ in range(10):
                self.particles.append([x + r.uniform(-8, 8), y + r.uniform(-8, 8), r.uniform(-120, 120),
                                       r.uniform(-160, 0), 1.0, 1.0, th["panel"], "debris", 3])
        elif k == "hurt":
            self.shake = max(self.shake, 5)
            self._sparks(x, y, 8, (255, 80, 80))
        elif k == "shield_hit":
            self.lights.append([x, y, 60, (80, 200, 255), 0.15, 0.15])
        elif k == "pickup":
            col = PICKUP_COLORS.get(e["pickup"], (200, 255, 255))
            for i in range(14):
                a = i / 14 * math.tau
                self.particles.append([x, y, math.cos(a) * 90, math.sin(a) * 90, 0.45, 0.45, col, "spark", 1])
            self.lights.append([x, y, 80, col, 0.3, 0.3])
        elif k in ("checkpoint", "sector_start", "teleport", "upgrade", "lesson"):
            col = (120, 255, 200)
            self.lights.append([x, y, 140, col, 0.6, 0.6])
            for i in range(24):
                a = i / 24 * math.tau
                self.particles.append([x, y, math.cos(a) * 140, math.sin(a) * 140, 0.6, 0.6, col, "spark", 1])
            if k == "teleport":
                self.cur[0] = (game.player.x, game.player.y)
                self.prev[0] = self.cur[0]
        elif k == "dash":
            self._sparks(x, y, 6, th["edge"])
        elif k == "land" and e.get("speed", 0) > 1800:
            for d in (-1, 1):
                for _ in range(3):
                    self.particles.append([x, y - 2, d * r.uniform(30, 90), -r.uniform(10, 40), 0.35, 0.35,
                                           (120, 130, 150), "dust", 2])
        elif k in ("stomp",):
            self.shake = max(self.shake, 9 if e.get("big") else 6)
            for d in (-1, 1):
                for _ in range(6):
                    self.particles.append([x, y - 2, d * r.uniform(60, 200), -r.uniform(10, 60), 0.5, 0.5,
                                           (160, 150, 140), "dust", 3])
        elif k in ("alarm", "boss_phase"):
            self.lights.append([x, y, 200, (255, 60, 60), 0.8, 0.8])
            self.shake = max(self.shake, 4 if k == "alarm" else 12)
        elif k == "spit":
            self.lights.append([x, y, 40, (140, 255, 80), 0.2, 0.2])
        elif k == "nest_open" or k == "nest_spawn":
            self._gibs(x, y, 6)
        elif k == "laser_fire":
            self.shake = max(self.shake, 6)
        elif k == "sector_clear":
            self.lights.append([x, y, 300, (200, 255, 255), 1.0, 1.0])

    def _floor_below(self, game, x, y) -> int:
        g = game.grid
        ty = int(y) >> 4
        for k in range(8):
            if g.at(int(x) >> 4, ty + k) in (SOLID, ONEWAY, BREAK, DOOR):
                return (ty + k) * 16
        return int(y)

    def _sparks(self, x, y, n, col) -> None:
        r = self.rng
        for _ in range(n):
            a = r.uniform(0, math.tau)
            s = r.uniform(50, 180)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s - 40, r.uniform(0.15, 0.35), 0.35, col,
                                   "spark", 1])

    def _gibs(self, x, y, n) -> None:
        r = self.rng
        for _ in range(n):
            a = r.uniform(math.pi, math.tau)
            s = r.uniform(60, 220)
            col = r.choice(((110, 200, 60), (70, 140, 40), (160, 240, 90), (90, 70, 30)))
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s, r.uniform(0.6, 1.2), 1.2, col, "gib",
                                   r.choice((2, 2, 3))])

    def update(self, dt: float, game) -> None:
        """Advance presentation-only effects by real time ``dt`` seconds."""
        self.time += dt
        keep = []
        for p in self.particles:
            p[4] -= dt
            if p[4] <= 0:
                continue
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            if p[7] in ("gib", "debris"):
                p[3] += 600 * dt
                if game.grid.at(int(p[0]) >> 4, int(p[1]) >> 4) in (SOLID, ONEWAY, BREAK):
                    p[1] -= p[3] * dt
                    p[3] *= -0.3
                    p[2] *= 0.6
            elif p[7] == "spark":
                p[3] += 260 * dt
            elif p[7] == "dust":
                p[2] *= 0.9
            keep.append(p)
        self.particles = keep[-900:]
        for lst in (self.lights, self.beams, self.trail):
            for item in lst:
                item[4 if lst is not self.trail else 3] -= dt
        self.lights = [x for x in self.lights if x[4] > 0]
        self.beams = [x for x in self.beams if x[4] > 0]
        self.trail = [x for x in self.trail if x[3] > 0]
        for a in self.anims:
            a[3] += dt
        self.anims = [a for a in self.anims if a[3] * a[4] < len(a[0])]
        for d in self.decals:
            d[4] -= dt
        self.decals = [d for d in self.decals if d[4] > 0][-60:]
        if self.muzzle:
            self.muzzle[4] -= dt
            if self.muzzle[4] <= 0:
                self.muzzle = []
        self.shake = max(0.0, self.shake - dt * 30)
        tx, ty = self._cam_target(game)
        cx, cy = self.cam
        k = min(1.0, dt * 9)
        self.cam = (cx + (tx - cx) * k, cy + (ty - cy) * k)
        if abs(tx - cx) > 400 or abs(ty - cy) > 300:
            self.cam = (tx, ty)

    def _decorate(self, game):
        """Background furniture and signs, placed deterministically from the map (render only)."""
        m = game.map
        w, tiles = m.width, m.tiles
        rng = random.Random(sum(map(ord, m.name)) * 7919)
        pool = self.art.floor_props.get(m.theme, self.art.floor_props["transit"])

        def at(tx, ty):
            return tiles[ty * w + tx] if 0 <= tx < w and 0 <= ty < m.height else SOLID

        keep_clear = {(e.tx, e.ty) for e in m.entities if e.kind not in ("lamp", "enemy", "nest", "spawn")}
        props, walls, used = [], [], set()
        for ty in range(2, m.height):
            for tx in range(1, w - 1):
                if at(tx, ty) != SOLID or at(tx, ty - 1) in (SOLID, BREAK, DOOR) or rng.random() > 0.07:
                    continue
                img = rng.choice(pool)
                pw, ph = (img.get_width() + 15) // 16, (img.get_height() + 15) // 16
                cols = range(tx, tx + pw)
                ok = all(at(c, ty) == SOLID for c in cols) and all(
                    at(c, r) == 0 and (c, r) not in keep_clear and (c, r) not in used
                    for c in cols for r in range(ty - ph, ty))
                ok = ok and all((c + d, ty - 1) not in keep_clear for c in cols for d in (-2, -1, 1, 2))
                if not ok:
                    continue
                for c in cols:
                    for r in range(ty - ph, ty):
                        used.add((c, r))
                props.append((img, tx * 16 + pw * 8, ty * 16))
        for ty in range(3, m.height - 6):
            for tx in range(2, w - 2):
                clear = all(at(tx, ty + k) == 0 for k in (-1, 0, 1, 2, 3, 4))
                if clear and at(tx, ty + 5) in (SOLID, ONEWAY) and (tx, ty) not in used and rng.random() < 0.025:
                    kind = rng.choice(("monitor", "monitor", "banner", "banner_big"))
                    walls.append((kind, tx * 16 + 8, ty * 16 + 8, rng.randrange(4)))
                    used.add((tx, ty))
        return props, walls

    def _furniture(self, ox, oy):
        for img, x, bottom in self.props:
            sx, sy = x - img.get_width() // 2 - ox, bottom - img.get_height() - oy
            if -130 < sx < SCENE_W and -130 < sy < SCENE_H:
                self.scene.blit(img, (sx, sy))
        frame = int(self.time * 6)
        for kind, x, y, phase in self.wall_props:
            frames = {"monitor": self.art.monitor, "banner": self.art.banner,
                      "banner_big": self.art.banner_big}[kind]
            img = frames[(frame + phase) % len(frames)]
            r = img.get_rect(center=(x - ox, y - oy))
            if -100 < r.x < SCENE_W and -100 < r.y < SCENE_H:
                self.scene.blit(img, r)
                self.glow.blit(self.art.premul(img, 110), r, special_flags=pg.BLEND_RGB_ADD)

    # ------------------------------------------------------------ tiles
    def _chunk(self, game, cx: int, cy: int):
        got = self.chunks.get((cx, cy))
        if got is not None:
            return got
        th = self.theme
        surf = pg.Surface((CHUNK, CHUNK), pg.SRCALPHA)
        glow = pg.Surface((CHUNK, CHUNK))
        m = game.map
        w = m.width
        base = m.tiles

        def at(tx, ty):
            if 0 <= tx < w and 0 <= ty < m.height:
                return base[ty * w + tx]
            return SOLID

        def solid(c):
            return c in (SOLID, BREAK, DOOR)

        wall = (*th["wall"], 128)
        grid_col = (*th["edge"], 26)
        edge, edge2 = th["edge"], th["edge2"]
        dim_edge = tuple(v // 3 for v in edge)
        n = CHUNK // 16
        for j in range(n):
            for i in range(n):
                tx, ty = cx * n + i, cy * n + j
                if tx >= w or ty >= m.height:
                    continue
                c = at(tx, ty)
                x, y = i * 16, j * 16
                if solid(c):
                    if c != SOLID:
                        surf.fill(wall, (x, y, 16, 16))
                        continue
                    h = (tx * 73856093 ^ ty * 19349663) & 0xFFFF
                    shade = th["fill"] if (tx + ty) % 2 else tuple(min(255, v + 3) for v in th["fill"])
                    surf.fill((*shade, 255), (x, y, 16, 16))
                    # 32 px machined plates: a light top-left bevel and a dark bottom-right one
                    lite = (*tuple(min(255, v + 12) for v in th["fill"]), 255)
                    dark = (*tuple(max(0, v - 8) for v in th["fill"]), 255)
                    if tx % 2 == 0:
                        surf.fill(lite, (x, y, 1, 16))
                    else:
                        surf.fill(dark, (x + 15, y, 1, 16))
                    if ty % 2 == 0:
                        surf.fill(lite, (x, y, 16, 1))
                    else:
                        surf.fill(dark, (x, y + 15, 16, 1))
                    if h % 7 == 0:
                        pg.draw.rect(surf, (*th["panel"], 255), (x + 3, y + 3, 10, 10), 1)
                    elif h % 11 == 0:
                        for k in range(3):
                            pg.draw.line(surf, (*th["panel"], 255), (x + 3, y + 4 + k * 3), (x + 12, y + 4 + k * 3))
                    elif h % 5 == 0:
                        surf.fill((*th["panel"], 255), (x + 7, y + 7, 2, 2))
                    up, down = at(tx, ty - 1), at(tx, ty + 1)
                    left, right = at(tx - 1, ty), at(tx + 1, ty)
                    if not solid(up):
                        surf.fill((*th["panel"], 255), (x, y, 16, 4))
                        surf.fill((*tuple(min(255, v + 30) for v in th["panel"]), 255), (x, y + 1, 16, 1))
                        pg.draw.line(surf, (*edge, 255), (x, y), (x + 15, y))
                        pg.draw.line(glow, edge, (x, y), (x + 15, y))
                    if not solid(down):
                        surf.fill((4, 6, 10, 255), (x, y + 14, 16, 2))
                        pg.draw.line(glow, dim_edge, (x, y + 15), (x + 15, y + 15))
                    if not solid(left):
                        pg.draw.line(surf, (*dim_edge, 255), (x, y), (x, y + 15))
                        pg.draw.line(glow, dim_edge, (x, y), (x, y + 15))
                    if not solid(right):
                        pg.draw.line(surf, (*dim_edge, 255), (x + 15, y), (x + 15, y + 15))
                        pg.draw.line(glow, dim_edge, (x + 15, y), (x + 15, y + 15))
                    continue
                surf.fill(wall, (x, y, 16, 16))
                if tx % 4 == 0:
                    pg.draw.line(surf, grid_col, (x, y), (x, y + 15))
                if ty % 4 == 0:
                    pg.draw.line(surf, grid_col, (x, y), (x + 15, y))
                if c == ONEWAY:
                    surf.fill((*th["panel"], 255), (x, y, 16, 5))
                    for k in range(2, 16, 4):
                        surf.fill((6, 8, 14, 255), (x + k, y + 2, 2, 2))
                    pg.draw.line(surf, (*edge2, 255), (x, y), (x + 15, y))
                    pg.draw.line(glow, edge2, (x, y), (x + 15, y))
                elif c == LADDER:
                    rail = (120, 135, 160, 255)
                    pg.draw.line(surf, rail, (x + 3, y), (x + 3, y + 15), 2)
                    pg.draw.line(surf, rail, (x + 12, y), (x + 12, y + 15), 2)
                    for k in (2, 7, 12):
                        pg.draw.line(surf, (90, 105, 130, 255), (x + 4, y + k), (x + 11, y + k))
                    glow.fill(dim_edge, (x + 3, y + 7, 1, 2))
                    glow.fill(dim_edge, (x + 12, y + 7, 1, 2))
                elif c == RAIL:
                    pg.draw.line(surf, (40, 48, 64, 255), (x + 7, y), (x + 7, y + 15), 3)
                    if ty % 2 == 0:
                        glow.fill(dim_edge, (x + 7, y + 8, 2, 1))
        surf = surf.convert_alpha()
        self.chunks[(cx, cy)] = (surf, glow)
        return surf, glow

    # ------------------------------------------------------------ the frame
    def render(self, game, alpha: float) -> pg.Surface:
        scene, glow = self.scene, self.glow
        cx, cy = self.cam
        if self.shake:
            cx += self.rng.uniform(-self.shake, self.shake) * 0.6
            cy += self.rng.uniform(-self.shake, self.shake) * 0.6
        ox, oy = round(cx), round(cy)
        self.last_camera = (cx, cy)
        scene.fill(self.theme["wall"])
        glow.fill((0, 0, 0))
        self._backdrop(ox, oy)
        for j in range(oy // CHUNK, (oy + SCENE_H) // CHUNK + 1):
            for i in range(ox // CHUNK, (ox + SCENE_W) // CHUNK + 1):
                surf, gl = self._chunk(game, i, j)
                scene.blit(surf, (i * CHUNK - ox, j * CHUNK - oy))
                glow.blit(gl, (i * CHUNK - ox, j * CHUNK - oy), special_flags=pg.BLEND_RGB_ADD)
        self._furniture(ox, oy)
        self._decals(ox, oy)
        self._dynamic_tiles(game, ox, oy)
        self._objects(game, ox, oy)
        self._pickups(game, ox, oy)
        self._enemies(game, alpha, ox, oy)
        self._player(game, alpha, ox, oy)
        self._shots(game, ox, oy)
        self._particles(ox, oy)
        self._anims(ox, oy)
        if self.lighting:
            self._light(game, ox, oy)
        scene.blit(glow, (0, 0), special_flags=pg.BLEND_RGB_ADD)
        if self.bloom:
            soft = pg.transform.smoothscale(pg.transform.smoothscale(glow, (160, 90)), (SCENE_W, SCENE_H))
            wide = pg.transform.smoothscale(pg.transform.smoothscale(glow, (64, 36)), (SCENE_W, SCENE_H))
            scene.blit(soft, (0, 0), special_flags=pg.BLEND_RGB_ADD)
            scene.blit(wide, (0, 0), special_flags=pg.BLEND_RGB_ADD)
        return scene

    def _backdrop(self, ox, oy):
        for img, factor, off in self.backdrop:
            w, h = img.get_size()
            x0 = -int(ox * factor) % w - w
            y = off - int(oy * factor * 0.5) % max(1, h)
            for yy in (y, y + h) if h < SCENE_H + 40 else (y,):
                for x in range(x0, SCENE_W, w):
                    self.scene.blit(img, (x, yy))
        if getattr(self, "_shade", None) is None or self._shade_col != self.theme["wall"]:
            self._shade = pg.Surface((SCENE_W, SCENE_H), pg.SRCALPHA)
            self._shade.fill((*self.theme["wall"], 70))
            self._shade_col = self.theme["wall"]
        self.scene.blit(self._shade, (0, 0))

    def _dynamic_tiles(self, game, ox, oy):
        g = game.grid
        th = self.theme
        live, warn = hazard_live(game), hazard_warning(game)
        t = self.time
        for tx, ty, base in self.dynamic_tiles:
            x, y = tx * 16 - ox, ty * 16 - oy
            if not (-16 < x < SCENE_W and -16 < y < SCENE_H):
                continue
            c = g.at(tx, ty)
            if base == DOOR and c == DOOR:
                group = next((d for d in game.doors if (tx, ty) in d.tiles), None)
                col = DOOR_COLORS.get(group.key if group else "", th["edge2"])
                self.scene.fill((20, 10, 24), (x + 4, y, 8, 16))
                for k in range(3):
                    xx = x + 5 + k * 3
                    bright = 0.6 + 0.4 * math.sin(t * 9 + ty * 0.9 + k)
                    cc = tuple(int(v * bright) for v in col)
                    pg.draw.line(self.scene, cc, (xx, y), (xx, y + 15))
                    pg.draw.line(self.glow, cc, (xx, y), (xx, y + 15))
            elif base == BREAK and c == BREAK:
                self.scene.fill(th["fill"], (x, y, 16, 16))
                pg.draw.lines(self.scene, (60, 60, 70), False, [(x + 2, y + 3), (x + 7, y + 8), (x + 5, y + 13)])
                pg.draw.lines(self.scene, (60, 60, 70), False, [(x + 7, y + 8), (x + 14, y + 6)])
                self.scene.fill((70, 60, 50), (x, y, 16, 1))
            elif base == HAZARD:
                self.scene.fill((40, 30, 40), (x + 1, y + 13, 14, 3))
                if live:
                    for k in range(2):
                        pts = [(x + 2 + k * 6, y + 14)]
                        for s in range(1, 4):
                            pts.append((x + 2 + k * 6 + self.rng.randint(-3, 3), y + 14 - s * 4))
                        pg.draw.lines(self.glow, (255, 120, 200), False, pts)
                        pg.draw.lines(self.scene, (255, 200, 240), False, pts)
                elif warn and int(t * 12) % 2:
                    self.glow.fill((120, 40, 90), (x + 1, y + 13, 14, 2))
                else:
                    self.glow.fill((50, 20, 40), (x + 3, y + 14, 10, 1))

    def _decals(self, ox, oy):
        for x, y, w, col, life in self.decals:
            a = min(1.0, life / 3)
            s = pg.Surface((w * 2, 6), pg.SRCALPHA)
            pg.draw.ellipse(s, (*col, int(170 * a)), s.get_rect())
            self.scene.blit(s, (x - w - ox, y - 3 - oy))

    def _label(self, text, x, y, col):
        img = self.small.render(text, True, col)
        shadow = self.small.render(text, True, (0, 0, 0))
        r = img.get_rect(center=(round(x), round(y)))
        self.scene.blit(shadow, r.move(1, 1))
        self.glow.blit(self.small.render(text, True, tuple(v // 2 for v in col), (0, 0, 0)), r,
                       special_flags=pg.BLEND_RGB_ADD)
        self.scene.blit(img, r)

    def _objects(self, game, ox, oy):
        art, th, t = self.art, self.theme, self.time
        p = game.player
        for lx, ly in game.lamps:
            x, y = lx - ox, ly - oy
            if -40 < x < SCENE_W + 40 and -40 < y < SCENE_H + 40:
                self.scene.fill((50, 55, 70), (x - 9, y - 8, 18, 4))
                self.glow.fill(th["lamp"], (x - 7, y - 4, 14, 2))
        for c in game.consoles:
            x, y = c.x - ox, c.y - oy
            if not (-40 < x < SCENE_W + 40 and -50 < y < SCENE_H + 10):
                continue
            img = art.terminal
            self.scene.blit(img, (x - img.get_width() // 2, y - img.get_height()))
            col = (90, 255, 160) if c.used else (255, 190, 90)
            blink = 0.6 + 0.4 * math.sin(t * 4)
            self.glow.fill(tuple(int(v * blink) for v in col), (x - 6, y - 30, 14, 8))
            if abs(p.cx - c.x) < 60 and abs(p.bottom - c.y) < 40:
                self._label("E  SAVE" if not c.used else "E  SAVED", x, y - 46, col)
        for s in game.switches:
            x, y = s.x - ox, s.y - 16 - oy
            if not (-20 < x < SCENE_W + 20 and -20 < y < SCENE_H + 20):
                continue
            self.scene.fill((40, 44, 58), (x - 6, y - 9, 12, 18))
            col = (90, 255, 160) if s.on else (255, 80, 120)
            self.scene.fill(col, (x - 2, y - 6 if s.on else y + 1, 4, 5))
            self.glow.fill(col, (x - 2, y - 6 if s.on else y + 1, 4, 5))
            if not s.on and abs(p.cx - s.x) < 50 and abs(p.cy - s.y) < 50:
                self._label("E  SWITCH", x, y - 18, col)
        for el in game.elevators:
            x, y = el.x - ox, el.y - oy
            if not (-60 < x < SCENE_W + 10 and -20 < y < SCENE_H + 20):
                continue
            self.scene.fill((70, 80, 100), (x, y, el.w, 6))
            self.scene.fill((30, 34, 48), (x + 2, y + 6, el.w - 4, 4))
            self.glow.fill(th["edge"], (x, y, el.w, 1))
            for k in range(4, el.w, 10):
                self.glow.fill(th["edge2"], (x + k, y + 8, 3, 1))
        for pad in game.pads:
            x, y = pad.x - ox, pad.y - oy
            if not (-30 < x < SCENE_W + 30 and -40 < y < SCENE_H + 10):
                continue
            col = (120, 255, 230) if pad.pair == "1" else (255, 160, 255)
            self.scene.fill((40, 46, 60), (x - 14, y - 4, 28, 4))
            self.glow.fill(col, (x - 12, y - 4, 24, 1))
            for k in range(3):
                yy = y - 4 - ((t * 40 + k * 14) % 40)
                self.glow.fill(tuple(v // 3 for v in col), (x - 10 + k * 8, int(yy), 2, 3))
        if game.variant == "training" and game.lesson < 10:
            from ...engine.neon.training import MARKER_LESSONS

            k = MARKER_LESSONS.get(game.lesson)
            if k is not None and k < len(game.markers):
                mx, my = game.markers[k]
                x, y = mx - ox, my - oy
                h = 40 + 6 * math.sin(t * 5)
                beam = pg.Surface((10, int(h)))
                beam.fill((40, 160, 90))
                self.glow.blit(beam, (x - 5, y - h), special_flags=pg.BLEND_RGB_ADD)
                pg.draw.polygon(self.glow, (120, 255, 170), [(x - 7, y - h - 10), (x + 7, y - h - 10), (x, y - h)])
                self._label("HERE", x, y - h - 18, (120, 255, 170))
        if game.exit:
            ex, ey = game.exit
            x, y = ex - ox, ey - oy
            if -60 < x < SCENE_W + 60 and -80 < y < SCENE_H + 10:
                locked = game.variant == "campaign" and game.sector == 3 and not game.boss_dead
                col = (255, 70, 90) if locked else (90, 255, 170)
                self.scene.fill((14, 18, 28), (x - 18, y - 48, 36, 48))
                pg.draw.rect(self.scene, (60, 70, 90), (x - 20, y - 50, 40, 50), 2)
                for k in range(0, 44, 4):
                    v = 0.4 + 0.6 * ((math.sin(t * 3 + k * 0.4) + 1) / 2)
                    self.glow.fill(tuple(int(c * v * 0.5) for c in col), (x - 16, y - 46 + k, 32, 1))
                self._label("LOCKED" if locked else "EXIT", x, y - 58, col)
                if abs(p.cx - ex) < 60 and abs(p.bottom - ey) < 40 and not locked:
                    self._label("E  EXTRACT", x, y - 70, col)

    def _pickups(self, game, ox, oy):
        t = self.time
        p = game.player
        for item in game.pickups:
            bob = math.sin(t * 3 + item.x * 0.1) * 2
            x, y = item.x - ox, item.y - 10 + bob - oy
            if not (-20 < x < SCENE_W + 20 and -30 < y < SCENE_H + 20):
                continue
            k = item.kind
            col = PICKUP_COLORS.get(k, (230, 230, 255))
            if item.life > 0 and item.life < 150 and int(t * 10) % 2:
                continue
            if k.startswith("weapon"):
                img = self.art.guns[int(k[6:])]
                self.scene.blit(img, (x - img.get_width() // 2, y - img.get_height() // 2))
                col = WEAPON_COLORS[int(k[6:])]
                pg.draw.circle(self.glow, tuple(v // 3 for v in col), (int(x), int(y)), 11, 1)
                if abs(p.cx - item.x) < 90 and abs(p.cy - item.y) < 70:
                    from ...engine.neon.weapons import WEAPONS

                    self._label(WEAPONS[int(k[6:])].name, x, y - 16, col)
                continue
            self._icon(k, x, y, col)
            if k in ("boots", "key_red", "key_gold", "shield", "overcharge", "haste", "phase") and \
                    abs(p.cx - item.x) < 90 and abs(p.cy - item.y) < 70:
                self._label(k.replace("_", " ").upper(), x, y - 16, col)

    def _icon(self, kind, x, y, col):
        """Small readable pickup icons: a dark capsule with a coloured symbol and a soft halo."""
        x, y = round(x), round(y)
        sc, gl = self.scene, self.glow
        pg.draw.circle(gl, tuple(v // 5 for v in col), (x, y), 11)
        pg.draw.rect(sc, (14, 18, 28), (x - 8, y - 8, 16, 16), border_radius=4)
        pg.draw.rect(sc, tuple(v // 2 for v in col), (x - 8, y - 8, 16, 16), 1, border_radius=4)
        if kind == "health":
            sc.fill(col, (x - 1, y - 5, 3, 11))
            sc.fill(col, (x - 5, y - 1, 11, 3))
        elif kind == "ammo":
            for k in (-4, 0, 4):
                sc.fill(col, (x + k - 1, y - 4, 3, 8))
                sc.fill((255, 240, 200), (x + k - 1, y - 5, 3, 2))
        elif kind == "shield":
            pts = [(x + 6 * math.cos(a), y + 6 * math.sin(a)) for a in np.linspace(0, math.tau, 7)[:-1]]
            pg.draw.polygon(sc, col, pts, 2)
        elif kind == "overcharge":
            pg.draw.lines(sc, col, False, [(x + 2, y - 6), (x - 3, y + 1), (x + 2, y + 1), (x - 2, y + 7)], 2)
        elif kind == "haste":
            for k in (-3, 2):
                pg.draw.lines(sc, col, False, [(x + k - 2, y - 4), (x + k + 2, y), (x + k - 2, y + 4)], 2)
        elif kind == "phase":
            pg.draw.polygon(sc, col, [(x, y - 6), (x + 5, y), (x, y + 6), (x - 5, y)], 2)
        elif kind == "boots":
            for k in (-2, 3):
                pg.draw.lines(sc, col, False, [(x - 5, y + k), (x, y + k - 4), (x + 5, y + k)], 2)
        elif kind.startswith("key"):
            sc.fill(col, (x - 6, y - 4, 12, 8))
            sc.fill((14, 18, 28), (x - 4, y - 2, 4, 4))
        gl.fill(tuple(v // 2 for v in col), (x - 1, y - 1, 3, 3))

    # ------------------------------------------------------------ actors
    def _ipos(self, uid, x, y, alpha):
        old = self.prev.get(uid, (x, y))
        return _lerp(old[0], x, alpha), _lerp(old[1], y, alpha)

    def _blit_anchor(self, img, cx, bottom, flash=False, alpha=255):
        if alpha < 255:
            img = img.copy()
            img.set_alpha(alpha)
        pos = (round(cx - img.get_width() / 2), round(bottom - img.get_height()))
        self.scene.blit(self.art.flash(img) if flash else img, pos)

    def _enemies(self, game, alpha, ox, oy):
        art, t = self.art, self.time
        for e in game.enemies:
            x, y = self._ipos(e.uid, e.x, e.y, alpha)
            sx, sy = x - ox, y - oy
            if not (-120 < sx < SCENE_W + 120 and -140 < sy < SCENE_H + 120):
                continue
            cx, bottom = sx + e.w / 2, sy + e.h
            flash = e.flash >= 3  # only the tick a hit lands, so steady fire does not bleach the sprite
            k = e.kind
            if k == "crawler":
                self._crawler(e, cx, sx, sy, bottom, flash)
            elif k == "stinger":
                frame = art.stinger[int(t * 18 + e.uid) % len(art.stinger)]
                img = frame if e.facing < 0 else art.flipped(frame)
                if e.state == "dive":
                    img = pg.transform.rotate(img, 25 if e.vx * e.facing > 0 else -25)
                jitter = self.rng.uniform(-1.5, 1.5) if e.state == "wind" else 0
                self._blit_anchor(img, cx + jitter, bottom + 18, flash)
                eye = (cx - 10 * e.facing, sy + 6)
                pg.draw.circle(self.glow, (255, 60, 40) if e.state in ("wind", "dive") else (160, 60, 20),
                               (int(eye[0]), int(eye[1])), 2)
            elif k == "strider":
                n = len(art.strider)
                frame = art.strider[int(abs(e.x) / 6) % n] if abs(e.vx) > 0 else art.strider[0]
                img = frame if e.facing > 0 else art.flipped(frame)
                self._blit_anchor(img, cx - 6 * e.facing, bottom + 1, flash)
                # the frontal shield
                col = (90, 200, 255)
                pts = [(cx + e.facing * (22 + abs(math.sin(a)) * 4), sy + 4 + i * 6)
                       for i, a in enumerate(np.linspace(0, math.pi, 9))]
                pg.draw.lines(self.glow, tuple(v // 2 for v in col), False, pts, 2)
                if e.state in ("lob_wind", "stomp_wind"):
                    pg.draw.circle(self.glow, (255, 120, 60), (int(cx + e.facing * 14), int(sy + 12)),
                                   3 + int(t * 20) % 3)
                if e.hp < e.max_hp:
                    self.scene.fill((30, 10, 20), (cx - 18, sy - 8, 36, 3))
                    self.scene.fill((255, 90, 120), (cx - 18, sy - 8, 36 * max(0, e.hp) // e.max_hp, 3))
            elif k in ("drone", "target"):
                frame = art.drone[int(t * 10 + e.uid) % len(art.drone)]
                img = frame if e.facing < 0 else art.flipped(frame)
                if k == "target":
                    img = img.copy()
                    img.fill((140, 255, 180, 255), special_flags=pg.BLEND_RGBA_MULT)
                self._blit_anchor(img, cx, bottom + 14, flash)
                if k == "drone" and e.state == "patrol":
                    look = 128 if e.facing > 0 else 384
                    a0, a1 = (look - 100) % 1024, (look + 100) % 1024
                    ex, ey = cx, sy + 8
                    col = (255, 60, 60) if e.spot > 2 else (60, 90, 120)
                    pts = [(ex, ey), (ex + COS[a0] * 200 / 1024, ey + SIN[a0] * 200 / 1024),
                           (ex + COS[a1] * 200 / 1024, ey + SIN[a1] * 200 / 1024)]
                    cone = pg.Surface((SCENE_W, SCENE_H), pg.SRCALPHA)
                    pg.draw.polygon(cone, (*col, 28), pts)
                    self.scene.blit(cone, (0, 0))
                    pg.draw.circle(self.glow, col, (int(ex), int(ey)), 2)
                elif k == "drone":
                    pg.draw.circle(self.glow, (255, 50, 50), (int(cx), int(sy + 8)), 3)
            elif k == "sentry":
                self._sentry(e, cx, sx, sy, flash)
            elif k == "nest":
                self._nest(e, cx, sx, sy, flash)
            elif k == "warden":
                self._warden(game, e, cx, sx, sy, bottom, flash, ox, oy)

    def _crawler(self, e, cx, sx, sy, bottom, flash):
        art, t = self.art, self.time
        moving = abs(e.vx) > 0 or e.state in ("ceil", "climb", "chase", "retreat")
        if e.state in ("crouch", "land", "hang", "spit"):
            frame = art.crawler_idle[int(t * 8 + e.uid) % 4]
        elif e.state in ("pounce", "drop"):
            frame = art.crawler_walk[2]
        elif moving:
            frame = art.crawler_walk[int(t * 14 + e.uid) % 6]
        else:
            frame = art.crawler_idle[int(t * 6 + e.uid) % 4]
        img = frame if e.facing < 0 else art.flipped(frame)
        if flash:
            img = art.flash(img)
        if e.surface == "ceil":
            img = pg.transform.flip(img, False, True)
            self.scene.blit(img, (round(cx - img.get_width() / 2), round(sy - 8)))
            eye_y = sy + 12
        elif e.surface == "wall":
            img = pg.transform.rotate(img, -90 if e.wall_dir > 0 else 90)
            self.scene.blit(img, (round(cx - img.get_width() / 2 + e.wall_dir * 6), round(bottom - img.get_height())))
            eye_y = sy
        else:
            if e.state == "pounce":
                img = pg.transform.rotate(img, max(-30, min(30, -e.vy / 60)) * (-1 if e.facing < 0 else 1))
            squash = e.state == "crouch"
            if squash:
                img = pg.transform.scale(img, (img.get_width() + 4, img.get_height() - 5))
            self.scene.blit(img, (round(cx - img.get_width() / 2), round(bottom + 4 - img.get_height())))
            eye_y = sy + 4
        eye_x = cx - 14 * e.facing
        col = (255, 40, 40) if e.alerted else (150, 50, 30)
        self.glow.fill(col, (round(eye_x), round(eye_y), 2, 2))
        if e.state in ("crouch", "spit"):
            pg.draw.circle(self.glow, (200, 255, 80), (round(eye_x), round(eye_y + 4)), 3, 1)

    def _sentry(self, e, cx, sx, sy, flash):
        art = self.art
        frame = art.turret[min(5, max(0, (8 - e.out) * 6 // 9))]
        mount_rot = {"floor": 0, "ceil": 180, "left": -90, "right": 90}[e.mount]
        cy = sy + e.h / 2
        plate = pg.Surface((26, 6))
        plate.fill((54, 60, 78))
        if e.mount in ("ceil", "floor"):
            py = sy if e.mount == "ceil" else sy + e.h - 6
            self.scene.blit(plate, (cx - 13, py))
        else:
            px = sx if e.mount == "left" else sx + e.w - 6
            self.scene.blit(pg.transform.rotate(plate, 90), (px, cy - 13))
        if e.out == 0:
            self.glow.fill((90, 30, 30), (round(cx - 1), round(cy - 1), 2, 2))
            return
        img = pg.transform.rotate(frame, mount_rot)
        if flash:
            img = art.flash(img)
        k = e.out / 8
        off = {"floor": (0, 6 * (1 - k)), "ceil": (0, -6 * (1 - k)), "left": (-6 * (1 - k), 0),
               "right": (6 * (1 - k), 0)}[e.mount]
        self.scene.blit(img, img.get_rect(center=(cx + off[0], cy + off[1])))
        if e.state in ("aim", "burst", "cool"):
            a = e.aim
            x2, y2 = cx + COS[a] * 260 / 1024, cy + SIN[a] * 260 / 1024
            col = (255, 40, 40) if e.state == "aim" and int(self.time * 16) % 2 else (140, 20, 20)
            pg.draw.line(self.glow, col, (cx, cy), (x2, y2))

    def _nest(self, e, cx, sx, sy, flash):
        t = self.time
        open_ = e.active
        rim = (140, 255, 80) if open_ else (70, 110, 50)
        pulse = 0.5 + 0.5 * math.sin(t * (6 if open_ else 2) + e.uid)
        r = pg.Rect(round(sx), round(sy + 4), e.w, e.h - 4)
        pg.draw.ellipse(self.scene, (12, 18, 10) if not flash else (255, 255, 255), r)
        pg.draw.ellipse(self.scene, (60, 80, 40), r, 2)
        pg.draw.ellipse(self.glow, tuple(int(v * pulse) for v in rim), r.inflate(-6, -6), 1)
        if open_:
            for k in range(3):
                pg.draw.circle(self.glow, (120, 255, 70), (round(cx - 6 + k * 6), round(sy + 12)), 1)

    def _warden(self, game, e, cx, sx, sy, bottom, flash, ox, oy):
        art, t = self.art, self.time
        n = len(art.warden)
        frame = art.warden[int(abs(e.x) / 8) % n] if abs(e.vx) > 0 else art.warden[0]
        img = frame if e.facing < 0 else art.flipped(frame)
        jitter = self.rng.uniform(-3, 3) if e.roar else 0
        lift = -6 if e.stomp_wind else 0  # rears up before a stomp
        self._blit_anchor(img, cx + jitter, bottom + 2 + lift, flash)
        if e.stomp_wind:
            for d in (-1, 1):
                pg.draw.line(self.glow, (255, 140, 60), (cx + d * 30, bottom), (cx + d * 90, bottom), 2)
        core = (round(cx), round(sy + 40))
        if e.laser == "vent":
            pg.draw.circle(self.glow, (255, 240, 120), core, 9 + int(t * 20) % 4)
            self._label("CORE EXPOSED", cx, sy - 14, (255, 240, 120))
        else:
            pg.draw.circle(self.glow, (255, 60, 90), core, 4)
        if e.laser in ("charge", "sweep"):
            top, bot = e.beam()
            y0, y1 = top - oy, bot - oy
            x0, x1 = e.left - 40 - ox, e.right + 40 - ox
            if e.laser == "charge":
                v = int(t * 14) % 2
                pg.draw.line(self.glow, (255, 60, 60) if v else (120, 20, 20), (x0, y0), (x1, y0))
                pg.draw.line(self.glow, (255, 60, 60) if v else (120, 20, 20), (x0, y1), (x1, y1))
                self._label("JUMP!" if not e.laser_high else "CROUCH!", cx, y0 - 10, (255, 120, 120))
            else:
                beam = pg.Surface((x1 - x0, y1 - y0))
                beam.fill((255, 60, 110))
                self.glow.blit(beam, (x0, y0), special_flags=pg.BLEND_RGB_ADD)
                core_line = pg.Surface((x1 - x0, max(2, (y1 - y0) // 3)))
                core_line.fill((255, 240, 250))
                self.scene.blit(core_line, (x0, (y0 + y1) // 2 - core_line.get_height() // 2))

    def _player(self, game, alpha, ox, oy):
        p = game.player
        art, t = self.art, self.time
        x, y = self._ipos(0, p.x, p.y, alpha)
        sx, sy = x - ox, y - oy
        for tx, ty, _img, life in self.trail:
            ghost = art.white(art.hero["run"][2] if p.facing > 0 else art.flipped(art.hero["run"][2]))
            g = ghost.copy()
            g.set_alpha(int(150 * life / 0.25))
            g.fill((90, 230, 255, 255), special_flags=pg.BLEND_RGBA_MULT)
            self.scene.blit(g, (tx - ox + p.w / 2 - 36, ty - oy + p.h - 66))
        anim, frame = self._hero_frame(p, t)
        img = art.hero[anim][frame % len(art.hero[anim])]
        face = p.facing
        if anim == "climb":
            face = 1
        if face < 0:
            img = art.flipped(img)
        if p.dying:
            img = pg.transform.rotate(img, 90 * -face if p.dying > 8 else 30 * -face)
        visible = not (p.iframes and not p.dash_t and int(t * 20) % 2 and not p.dying)
        anchor = 38 if face > 0 else 33
        cx, bottom = sx + p.w / 2, sy + p.h
        if visible:
            if p.dying:
                self.scene.blit(img, img.get_rect(midbottom=(cx, bottom + 2)))
            else:
                self.scene.blit(img, (round(cx - anchor), round(bottom - 66)))
        if p.overcharge:
            pg.draw.circle(self.glow, (120, 30, 110), (round(cx), round(sy + p.h / 2)), 18, 1)
        if p.shield:
            r = 24 + int(math.sin(t * 6) * 1.5)
            pg.draw.circle(self.glow, (40, 120, 170), (round(cx), round(sy + p.h / 2)), r, 1)
            pg.draw.circle(self.glow, (20, 60, 90), (round(cx), round(sy + p.h / 2)), r - 2, 1)
        if p.dying or anim == "climb" and not self.muzzle:
            return
        # the gun follows the mouse independently of the body (Abuse's free aim)
        shx, shy = p.shoulder()
        shx += x - p.x - ox
        shy += y - p.y - oy
        gun = art.gun(game.weapon, p.aim)
        gx = shx + COS[p.aim] * 7 / 1024
        gy = shy + SIN[p.aim] * 7 / 1024
        arm_end = (gx, gy)
        pg.draw.line(self.scene, (40, 60, 90), (shx, shy), arm_end, 3)
        self.scene.blit(gun, gun.get_rect(center=(round(gx), round(gy))))
        tip = (shx + COS[p.aim] * 17 / 1024, shy + SIN[p.aim] * 17 / 1024)
        self.glow.fill(tuple(v // 2 for v in WEAPON_COLORS[game.weapon]), (round(tip[0]), round(tip[1]), 1, 1))
        if self.muzzle:
            slot, mx, my, ang, life = self.muzzle
            mimg = art.muzzle(slot, ang)
            pos = mimg.get_rect(center=(round(mx - ox + COS[ang] * 6 / 1024), round(my - oy + SIN[ang] * 6 / 1024)))
            self.scene.blit(mimg, pos)
            self.glow.blit(self.art.premul(mimg), pos, special_flags=pg.BLEND_RGB_ADD)

    @staticmethod
    def _hero_frame(p, t) -> tuple[str, int]:
        if p.dying or p.stun:
            return "hurt", 0
        if p.climbing:
            return "climb", int(abs(p.y) / 6)
        if p.crouching:
            return "crouch", 0
        if p.dash_t:
            return "run", 3
        if not p.grounded:
            if p.air_jumps == 0 and p.boots and p.vy < 0:
                return "back-jump", int(t * 16)
            return "jump", 0 if p.vy < -600 else (1 if p.vy < 0 else (2 if p.vy < 800 else 3))
        if abs(p.vx) > 64:
            n = int(abs(p.x) / 7)
            backwards = (p.vx > 0) != (p.facing > 0)
            return "run", (-n if backwards else n) % 8
        return "idle", int(t * 6)

    def _shots(self, game, ox, oy):
        art = self.art
        for s in game.shots:
            x, y = s.x - ox, s.y - oy
            if not (-30 < x < SCENE_W + 30 and -30 < y < SCENE_H + 30):
                continue
            col = SHOT_COLORS.get(s.kind, (255, 255, 255))
            if s.kind == "acid":
                img = art.enemy_fx["acid"]
                self.scene.blit(img, img.get_rect(center=(x, y)))
                self.glow.blit(self.art.premul(img), img.get_rect(center=(x, y)), special_flags=pg.BLEND_RGB_ADD)
            elif s.kind == "shock":
                h = 6 + int(self.time * 30) % 4
                pg.draw.line(self.glow, col, (x, y + 4), (x, y + 4 - h), 3)
                pg.draw.line(self.scene, (255, 230, 200), (x, y + 4), (x, y + 4 - h // 2), 1)
            else:
                ang = s.angle
                if s.vx or s.vy:
                    from ...engine.neon.fixed import iatan2

                    ang = iatan2(s.vy, s.vx)
                img = art.projectile_img(s.kind, ang)
                if img is None:
                    pg.draw.circle(self.scene, col, (round(x), round(y)), 2)
                else:
                    r = img.get_rect(center=(round(x), round(y)))
                    self.scene.blit(img, r)
                    self.glow.blit(self.art.premul(img), r, special_flags=pg.BLEND_RGB_ADD)
            pg.draw.circle(self.glow, tuple(v // 3 for v in col), (round(x), round(y)), 4)
        for x1, y1, x2, y2, life, col in self.beams:
            k = life / 0.22
            w = max(1, int(5 * k))
            pg.draw.line(self.glow, tuple(int(v * k) for v in col), (x1 - ox, y1 - oy), (x2 - ox, y2 - oy), w + 2)
            pg.draw.line(self.scene, (255, 255, 255), (x1 - ox, y1 - oy), (x2 - ox, y2 - oy), max(1, w // 2))

    def _particles(self, ox, oy):
        for x, y, vx, vy, life, mx, col, kind, size in self.particles:
            sx, sy = x - ox, y - oy
            if not (0 <= sx < SCENE_W and 0 <= sy < SCENE_H):
                continue
            k = life / mx
            if kind == "spark":
                c = tuple(int(v * k) for v in col)
                pg.draw.line(self.glow, c, (sx, sy), (sx - vx * 0.02, sy - vy * 0.02))
            elif kind == "dust":
                self.scene.fill(tuple(int(v * k) for v in col), (sx, sy, size, size))
            else:
                self.scene.fill(col, (sx, sy, size, size))
                if kind == "gib":
                    self.glow.fill(tuple(v // 4 for v in col), (sx, sy, 1, 1))

    def _anims(self, ox, oy):
        for frames, x, y, t, fps, sc, glows in self.anims:
            img = frames[min(len(frames) - 1, int(t * fps))]
            if sc != 1:
                img = pg.transform.scale(img, (img.get_width() * sc, img.get_height() * sc))
            r = img.get_rect(center=(round(x - ox), round(y - oy)))
            self.scene.blit(img, r)
            if glows:
                self.glow.blit(self.art.premul(img), r, special_flags=pg.BLEND_RGB_ADD)

    # ------------------------------------------------------------ light
    def _light_sprite(self, radius: int, color) -> pg.Surface:
        key = (radius // 4, color)
        got = self._light_cache.get(key)
        if got is None:
            got = self._light_cache[key] = _radial(max(2, radius // 4), color)
        return got

    def _light(self, game, ox, oy):
        lm = self.lightmap
        lm.fill(self.theme["ambient"])
        q = 4

        def add(x, y, radius, color):
            sx, sy = (x - ox) / q, (y - oy) / q
            r = radius / q
            if -r < sx < SCENE_W / q + r and -r < sy < SCENE_H / q + r:
                img = self._light_sprite(int(radius), color)
                lm.blit(img, (sx - img.get_width() / 2, sy - img.get_height() / 2), special_flags=pg.BLEND_RGB_ADD)

        lamp = self.theme["lamp"]
        for lx, ly in game.lamps:
            add(lx, ly + 40, 220, tuple(v * 2 // 3 for v in lamp))
        p = game.player
        add(p.cx, p.cy, 150, (90, 100, 120))
        for c in game.consoles:
            add(c.x, c.y - 20, 90, (60, 120, 90) if c.used else (120, 90, 50))
        for s in game.shots:
            col = SHOT_COLORS.get(s.kind, (200, 200, 200))
            add(s.x, s.y, 70, tuple(v // 2 for v in col))
        for x, y, radius, col, life, mx in self.lights:
            k = life / mx
            add(x, y, radius, tuple(int(v * k) for v in col))
        for pad in game.pads:
            add(pad.x, pad.y - 10, 80, (40, 110, 100))
        if hazard_live(game) and game.hazards:
            for tx, ty, base in self.dynamic_tiles:
                if base == HAZARD:
                    add(tx * 16 + 8, ty * 16 + 12, 60, (120, 40, 90))
        full = pg.transform.smoothscale(lm, (SCENE_W, SCENE_H))
        self.scene.blit(full, (0, 0), special_flags=pg.BLEND_RGB_MULT)


def game_aim(game) -> tuple[int, int]:
    p = game.player
    sx, sy = p.shoulder()
    a = p.aim
    return sx + COS[a] * 120 // 1024, sy + SIN[a] * 120 // 1024
