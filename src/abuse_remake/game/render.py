"""Draw the world as the player sees it. Presentation only: nothing here changes a rule.

Draw order follows the original (abuse/src/game.c ``draw_map``): background tiles with
parallax (``bg_scroll_rate``: offset * xmul / xdiv), then foreground tiles, then objects in
object-list order (``add_front`` objects sit at the end, so they draw last). The original's
second foreground pass, for "above" tiles drawn over objects (game.c:977-1010), is not needed:
Level 1 has none. Each object's draw function decides how it looks (``dev_draw`` objects are
invisible in play). Classic draws only the active objects, as the original draws from
``first_active`` (level.c:792-804); Remastered's wider view also shows the inactive ones near
its edges, standing still.

Interpolation: the camera and the positions of active objects are blended between the last two
15 Hz ticks. The renderer keeps its own camera position per tick (``note_tick``), because the
view's ``last_last`` position is overwritten by the second scroll update every tick. The
original had a similar development switch, ``interpolate_draw``, off by default
(dev.c:26, game.c:1573-1576).
"""

from __future__ import annotations

import math

import numpy as np
import pygame

from ..engine.behaviors.lispfns import activated
from ..engine.view import VIEW_H, VIEW_W
from ..formats.tiles import BACK_H, BACK_W, FORE_H, FORE_W
from .lighting import flash_map, light_levels
from .sprites import SpriteCache

INVISIBLE_DRAW = {"dev_draw", "sensor_draw", "fb_draw"}
TOP_DRAW_STATES = {"stopped", "running", "run_jump", "run_jump_fall", "end_run_jump"}
FAST_POWER, FLY_POWER, SNEAKY_POWER = 1, 2, 3  # people.lsp enum
POWER_STATES = {"stopped", "running", "start_run_jump", "run_jump", "run_jump_fall", "end_run_jump"}


def sneaky_alpha(bot) -> int:
    """cop.c:758-765, 868-875: invisible players fade by used_special_power sixteenths
    (draw_trans), and at 15 the original draws a faint distortion (draw_predator)."""
    if bot.lvars.get("special_power") != SNEAKY_POWER:
        return 255
    used = bot.lvars.get("used_special_power", 0)
    if used == 0:
        return 255
    if used < 15:
        return 255 * (16 - used) // 16
    return 28


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class Renderer:
    def __init__(self, game, sprites: SpriteCache | None = None, width: int = VIEW_W, height: int = VIEW_H):
        self.game = game
        self.sprites = sprites or SpriteCache()
        self.w, self.h = width, height
        self.surface = pygame.Surface((width, height))
        self.flashes: list[list] = []  # dynamic lights: [x, y, radius, strength, ttl]
        self.lighting = True
        self.modern = True
        self.cam_prev: tuple[float, float] | None = None
        self.cam_cur: tuple[float, float] | None = None
        self.last_cam: tuple[float, float] = (0.0, 0.0)

    @property
    def world(self):
        return self.game.world

    def camera_target(self) -> tuple[float, float]:
        """Where the view is after the latest tick (view.c xoff/yoff), centring a wider modern
        view on the same point the classic view centres on."""
        v = self.game.view
        return (max(0.0, v.xoff() - (self.w - VIEW_W) / 2), max(0.0, v.yoff() - (self.h - VIEW_H) / 2))

    def note_tick(self) -> None:
        """Call after every game tick."""
        cur = self.camera_target()
        prev = self.cam_cur if self.cam_cur is not None else cur
        if abs(cur[0] - prev[0]) > 160 or abs(cur[1] - prev[1]) > 160:
            prev = cur  # a teleport or restart: cut, do not sweep
        self.cam_prev, self.cam_cur = prev, cur

    def reset_camera(self) -> None:
        """Call after the game is replaced (new game, restore)."""
        self.cam_prev = self.cam_cur = self.camera_target()

    def camera(self, alpha: float) -> tuple[float, float]:
        if self.cam_cur is None:
            self.reset_camera()
        (px, py), (cx, cy) = self.cam_prev, self.cam_cur
        return _lerp(px, cx, alpha), _lerp(py, cy, alpha)

    def note_events(self, events) -> None:
        for e in events:
            if e.kind == "explosion":
                self.flashes.append([e.data["x"], e.data["y"], e.data["radius"] * 2.5, 1.0, 6])
            elif e.kind == "sound" and e.data["name"] == "ZAP_SND":
                self.flashes.append([e.data["x"], e.data["y"], 40, 0.7, 2])

    def render(self, alpha: float = 1.0) -> pygame.Surface:
        surf = self.surface
        w = self.world
        xoff, yoff = self.camera(alpha)
        self.last_cam = (xoff, yoff)
        surf.fill((0, 0, 0))
        self._draw_background(surf, xoff, yoff)
        self._draw_foreground(surf, xoff, yoff)
        active = {id(o) for o in w.active}
        for o in w.objects:
            if id(o) in active:
                self._draw_object(surf, o, xoff, yoff, alpha)
            elif self.modern:
                self._draw_object(surf, o, xoff, yoff, 1.0)  # inactive: it stands still
        if self.lighting:
            self._apply_lighting(surf, xoff, yoff)
        v = self.game.view
        if v.draw_solid != -1:  # game.c:724-729: fill the view with one colour for a frame
            c = v.draw_solid
            surf.fill(((c >> 16) & 255, (c >> 8) & 255, c & 255))
            v.draw_solid = -1
        return surf

    # --- map ---
    def _draw_background(self, surf, xoff, yoff):
        xmul, xdiv, ymul, ydiv = self.world.bg_scroll
        bx = xoff * xmul / max(1, xdiv)
        by = yoff * ymul / max(1, ydiv)
        lv = self.world.level
        tx0, ty0 = int(bx // BACK_W), int(by // BACK_H)
        for ty in range(ty0, ty0 + self.h // BACK_H + 2):
            for tx in range(tx0, tx0 + self.w // BACK_W + 2):
                if 0 <= tx < lv.bg_width and 0 <= ty < lv.bg_height:
                    t = self.sprites.back_tile(self.world_tiles, self.world.bg_map[tx + ty * lv.bg_width])
                    if t is not None:
                        surf.blit(t, (round(tx * BACK_W - bx), round(ty * BACK_H - by)))

    @property
    def world_tiles(self):
        from ..engine.game import _tiles

        return _tiles()

    def _draw_foreground(self, surf, xoff, yoff):
        tm = self.world.tiles
        tiles = self.world_tiles
        tx0, ty0 = int(xoff // FORE_W), int(yoff // FORE_H)
        for ty in range(ty0, ty0 + self.h // FORE_H + 2):
            for tx in range(tx0, tx0 + self.w // FORE_W + 2):
                n = tm.get(tx, ty)
                if n:
                    t = self.sprites.fore_tile(tiles, n)
                    if t is not None:
                        surf.blit(t, (round(tx * FORE_W - xoff), round(ty * FORE_H - yoff)))

    # --- objects ---
    def _pos(self, o, alpha):
        return _lerp(o.last_x, o.x, alpha), _lerp(o.last_y, o.y, alpha)

    def _blit_figure(self, surf, o, x, y, xoff, yoff, fig=None, direction=None, alpha_mul=1.0, dy=0):
        fig = fig or o.figure()
        d = o.direction if direction is None else direction
        fwd, back = self.sprites.figure(fig)
        img = fwd if d > 0 else back
        left = x - fig.xcfg if d > 0 else x - (fig.width - fig.xcfg - 1)
        top = y - fig.height + 1 + dy
        sx, sy = round(left - xoff), round(top - yoff)
        if sx > self.w or sy > self.h or sx + fig.width < 0 or sy + fig.height < 0:
            return
        if o.fade_count or alpha_mul < 1.0:
            a = max(0, 255 - o.fade_count * 255 // max(1, o.fade_max))
            img = img.copy()
            img.set_alpha(int(a * alpha_mul))
        surf.blit(img, (sx, sy))

    def _player_figure(self, o):
        """cop.c:816-866: with the speed or flight power the player is drawn from its fast_* or
        fly_* sequence of the same state and frame."""
        sp = o.lvars.get("special_power")
        if sp in (FAST_POWER, FLY_POWER) and o.state in POWER_STATES:
            seq = o.ctype.sequences.get(("fast_" if sp == FAST_POWER else "fly_") + o.state)
            if seq:
                return seq[min(o.current_frame, len(seq) - 1)]
        return o.figure()

    def _draw_object(self, surf, o, xoff, yoff, alpha):
        if o.deleted:
            return
        draw = o.ctype.fun_names.get("draw_fun")
        if draw in INVISIBLE_DRAW:
            return
        x, y = self._pos(o, alpha)
        rx = max(o.ctype.draw_rangex, 64)
        if x + rx < xoff or x - rx > xoff + self.w or y - 2 * rx > yoff + self.h or y + rx < yoff:
            return
        if draw == "top_draw":
            if not o.objs:
                return
            bot = o.objs[0]
            if bot.state not in TOP_DRAW_STATES:
                return
            bx, by = self._pos(bot, alpha)
            tx = bx + (4 if bot.direction < 0 else 0)
            ty = by + 29 - bot.picture_height()
            self._blit_figure(surf, o, tx, ty, xoff, yoff, alpha_mul=sneaky_alpha(bot) / 255)
            return
        if draw == "frabs_bottom_draw":  # the player
            fig = self._player_figure(o)
            if self.modern and o.lvars.get("special_power") == FAST_POWER and o.lvars.get("used_special_power"):
                # an afterimage while running fast (draw_fast, people.lsp:390-422); drawn from
                # the last tick's position, because cop.c:479 stores y into last2_x
                self._blit_figure(surf, o, o.last_x, o.last_y, xoff, yoff, fig=fig, alpha_mul=0.35)
            self._blit_figure(surf, o, x, y, xoff, yoff, fig=fig, alpha_mul=sneaky_alpha(o) / 255)
            return
        if draw == "sgun_draw":
            self._draw_bolt(surf, o, xoff, yoff)
            return
        if draw == "exp_draw":
            if o.aitype == 0:  # middle_draw: drawn half its height lower
                self._blit_figure(surf, o, x, y, xoff, yoff, dy=o.picture_height() // 2)
            return
        if draw == "on_draw":
            if activated(o):
                self._blit_figure(surf, o, x, y, xoff, yoff)
            return
        if draw == "ff_draw":
            if activated(o):
                self._draw_force_field(surf, o, xoff, yoff)
            return
        self._blit_figure(surf, o, x, y, xoff, yoff)

    def _draw_bolt(self, surf, o, xoff, yoff):
        bright = o.lvars.get("sgb_bright_color", 0xFFFFFF)
        medium = o.lvars.get("sgb_medium_color", 0x808080)
        bc = ((bright >> 16) & 255, (bright >> 8) & 255, bright & 255)
        mc = ((medium >> 16) & 255, (medium >> 8) & 255, medium & 255)
        x1, y1 = o.lvars["sgb_lastx"] - xoff, o.lvars["sgb_lasty"] - yoff
        x2, y2 = o.x - xoff, o.y - yoff
        pygame.draw.line(surf, mc, (x1, y1 - 1), (x2, y2 - 1))
        pygame.draw.line(surf, mc, (x1, y1 + 1), (x2, y2 + 1))
        pygame.draw.line(surf, bc, (x1, y1), (x2, y2))

    def _draw_force_field(self, surf, o, xoff, yoff):
        end_y = o.lvars.get("end_y", o.y)
        tick = self.world.tick_counter
        for i, col in enumerate(((151, 139, 151), (139, 147, 191), (39, 55, 71))):
            pts = []
            for yy in range(int(o.y), int(end_y) + 1, 4):
                jitter = math.sin((yy + tick * 7 + i * 13) * 0.7) * (2 + i)
                pts.append((o.x - xoff + jitter, yy - yoff))
            if len(pts) > 1:
                pygame.draw.lines(surf, col, False, pts)

    # --- light ---
    def _apply_lighting(self, surf, xoff, yoff):
        v = self.game.view
        lv = light_levels(self.world.lights, v.ambient, xoff, yoff, self.w, self.h)
        if self.modern:
            extra = [(f[0], f[1], f[2], f[3]) for f in self.flashes]
            factor = np.sqrt(lv.astype(np.float32) / 63.0)  # a gentler, modern curve
            if extra:
                np.maximum(factor, flash_map(extra, xoff, yoff, self.w, self.h), out=factor)
            if factor.min() < 0.999:
                rgb = pygame.surfarray.pixels3d(surf)
                rgb[...] = (rgb * factor.T[..., None]).astype(np.uint8)
                del rgb
        elif lv.min() < 63:
            # Classic: white_light takes 63 - level off each 8-bit channel (light.c:230-245)
            rgb = pygame.surfarray.pixels3d(surf)
            dark = (63 - lv).T[..., None]
            rgb[...] = np.clip(rgb.astype(np.int16) - dark, 0, 255).astype(np.uint8)
            del rgb
        self._age_flashes()

    def _age_flashes(self):
        for f in self.flashes:
            f[4] -= 1
            f[3] *= 0.6
        self.flashes = [f for f in self.flashes if f[4] > 0]
