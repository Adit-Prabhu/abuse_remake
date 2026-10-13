"""Shaded pixel-art scene using Ansimuz's licensed, vendored raster assets.

Source/licence/checksum record: assets/neon/PROVENANCE.md. All transforms are presentation
only. Art is decoded once, frames keep their source canvas alignment and transparent alpha.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pygame as pg

from ..engine.neon import ENEMY_HP, FLOOR
from ..paths import assets_root

WORLD_W, WORLD_H = 640, 360
ACCENT = (91, 220, 233)
POWER_COLORS = {"shield": (98, 207, 236), "overcharge": (214, 122, 211), "speed": (226, 180, 99),
                "health": (115, 223, 153), "ammo": (197, 210, 230)}


def _order(path: Path):
    import re

    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path.name)]


class RasterArt:
    def __init__(self):
        self.root = assets_root() / "neon"
        self.images = {}
        self.animations = {}
        self.frame_cache = {}
        self.scene = pg.Surface((WORLD_W, WORLD_H))
        self.small = pg.font.Font(None, 12)
        yy, xx = np.mgrid[-1:1:96j, -1:1:96j]
        falloff = np.maximum(0, 1 - np.sqrt(xx * xx + yy * yy)) ** 2
        rgb = (falloff[..., None] * np.array([28, 57, 68])).astype(np.uint8)
        halo = pg.image.frombuffer(rgb.tobytes(), (96, 96), "RGB").copy()
        self.light_pool = pg.transform.smoothscale(halo, (160, 230))
        self.muzzle_pool = pg.transform.smoothscale(halo, (90, 90))
        groups = {
            "courier_idle": "city2/Sprites/cop/idle",
            "courier_run": "city2/Sprites/cop/run",
            "courier_jump": "city2/Sprites/cop/run",
            "drone": "city/SPRITES/misc/drone",
            "stalker_idle": "city2/Sprites/cop/idle",
            "stalker_run": "city2/Sprites/cop/run",
            "sentry": "city/SPRITES/misc/turret",
            "titan_idle": "city2/Sprites/egg turret/Idle",
            "titan_shoot": "city2/Sprites/egg turret/Shoot",
            "explosion": "city2/Sprites/explosion-a",
        }
        for name, folder in groups.items():
            self.animations[name] = [self.load(p.relative_to(self.root).as_posix())
                                     for p in sorted((self.root / folder).glob("*.png"), key=_order)]
            if not self.animations[name]:
                raise ValueError(f"missing Neon animation: {folder}")
        self.city_layers = [self.scaled(f"city2/Environment/background/{name}.png", 2)
                            for name in ("back", "middle", "front")]
        self.industrial_city = [self.scaled("city/ENVIRONMENT/background/buildings-bg.png", 2),
                                self.scaled("city/ENVIRONMENT/background/near-buildings-bg.png", 1.5)]
        self.lab_layers = [self.scaled(f"lab/layers/{name}.png", 1.5) for name in ("back", "middle", "front")]
        self.tanks = [self.scaled(f"lab/layers/Props/tank-{i}.png", 1) for i in (1, 2, 3)]
        self.city_tiles = self.load("city2/Environment/tileset.png")
        self.tech_tiles = self.load("city/ENVIRONMENT/tileset.png")
        self.top_tile = self.city_tiles.subsurface((16, 16, 16, 16)).copy()
        self.face_tile = self.city_tiles.subsurface((16, 32, 16, 16)).copy()
        self.bottom_tile = self.city_tiles.subsurface((16, 48, 16, 16)).copy()
        self.tech_top = self.tech_tiles.subsurface((112, 176, 16, 16)).copy()
        self.tech_face = self.tech_tiles.subsurface((176, 144, 16, 16)).copy()
        self.vent_tile = self.tech_tiles.subsurface((176, 144, 32, 32)).copy()
        self.door_tile = self.tech_tiles.subsurface((144, 16, 32, 64)).copy()
        self.portal = self.tech_tiles.subsurface((224, 176, 48, 64)).copy()
        self.portal = pg.transform.scale(self.portal, (54, 76))
        self.relay_image = self.load("city/ENVIRONMENT/props/control-box-1.png")
        self.banner = [self.load(f"city/ENVIRONMENT/props/banner-neon/banner-neon-{i}.png") for i in range(1, 5)]
        self.lights = [self.load(f"city2/Environment/props/lights/lights{i}.png") for i in range(1, 5)]

    def load(self, relative):
        if relative not in self.images:
            self.images[relative] = pg.image.load(self.root / relative).convert_alpha()
        return self.images[relative]

    def scaled(self, relative, scale):
        key = (relative, scale)
        if key not in self.frame_cache:
            source = self.load(relative)
            self.frame_cache[key] = pg.transform.scale(source, (round(source.get_width() * scale),
                                                                round(source.get_height() * scale)))
        return self.frame_cache[key]

    def frame(self, group, tick, facing=1, scale=1):
        frames = self.animations[group]
        index = tick % len(frames)
        key = (group, index, facing < 0, scale)
        if key not in self.frame_cache:
            image = frames[index]
            native_left = group.startswith(("courier", "stalker"))
            if group.startswith("courier"):
                image = image.copy()
                # Free mouse aim replaces the run frame's horizontal gun. Feet/body shading stay intact.
                if group != "courier_idle":
                    image.fill((0, 0, 0, 0), (0, 26, 29, 11))
                image.fill((190, 220, 255, 255), special_flags=pg.BLEND_RGBA_MULT)
            elif group.startswith("stalker"):
                image = image.copy()
                image.fill((255, 130, 150, 255), special_flags=pg.BLEND_RGBA_MULT)
            if (facing < 0) != native_left:
                image = pg.transform.flip(image, True, False)
            if scale != 1:
                image = pg.transform.scale(image, (round(image.get_width() * scale),
                                                   round(image.get_height() * scale)))
            self.frame_cache[key] = image
        return self.frame_cache[key]

    def tile_layer(self, image, scroll, y, shade=None):
        if shade:
            image = image.copy()
            image.fill(shade, special_flags=pg.BLEND_RGBA_MULT)
        width = image.get_width()
        start = -int(scroll) % width - width
        for x in range(start, WORLD_W, width):
            self.scene.blit(image, (x, y))

    def background(self, game, camera):
        x, y = camera
        city = game.variant == "campaign" and game.player.x < 1400
        self.scene.fill((15, 16, 30) if city else (8, 18, 25))
        layers = self.industrial_city if city else self.lab_layers
        base_y = -35 - int((y - 235) * .12) if city else -25 - int((y - 235) * .15)
        for i, layer in enumerate(layers):
            shade = ((155, 175, 205, 255), (175, 185, 205, 255), (170, 190, 210, 255))[i] if city \
                else ((155, 180, 185, 255), (170, 190, 195, 255), (155, 190, 200, 255))[i]
            self.tile_layer(layer, x * (.12 + i * .13), base_y, shade)
        if city:
            for world_x in range(120, game.width, 420):
                sx = int(world_x - x * .78)
                self.scene.blit(self.banner[game.frames // 5 % 4], (sx, 78))
        else:
            for world_x in range(260, game.width + 300, 390):
                sx = int(world_x - x * .83)
                image = self.tanks[(world_x // 390) % 3]
                self.scene.blit(image, (sx, int(290 - image.get_height() - (y - 235) * .3)))
        # Overhead light fixtures and rear structural columns anchor the foreground deck.
        for world_x in range(80, game.width, 320):
            sx = int(world_x - x)
            if -60 < sx < WORLD_W + 60:
                self.scene.blit(self.lights[game.frames // 5 % 4], (sx, 25))

    def _tile_rect(self, image, rect):
        old_clip = self.scene.get_clip()
        self.scene.set_clip(rect.clip(old_clip))
        for y in range(rect.y, rect.bottom, image.get_height()):
            for x in range(rect.x, rect.right, image.get_width()):
                self.scene.blit(image, (x, y))
        self.scene.set_clip(old_clip)

    def environment(self, game, camera):
        cx, cy = camera
        top_tile, face_tile = self.tech_top, self.tech_face
        for index, (x, y, w, _h) in enumerate(game.platforms):
            sx, sy = round(x - cx), round(y - cy)
            if sx > WORLD_W or sx + w < 0:
                continue
            # Material, bevel, lit top plane, dark front and cast shadow give each deck volume.
            shadow = pg.Surface((min(w, WORLD_W) + 15, 42), pg.SRCALPHA)
            shadow.fill((2, 6, 15, 100))
            self.scene.blit(shadow, (max(-15, sx) + 7, sy + 9))
            left, right = max(-16, sx), min(WORLD_W + 16, sx + w)
            self._tile_rect(top_tile, pg.Rect(left, sy, right - left, 16))
            self._tile_rect(face_tile, pg.Rect(left, sy + 16, right - left, 16))
            self._tile_rect(face_tile, pg.Rect(left, sy + 32, right - left, 9))
            pg.draw.line(self.scene, (104, 151, 165), (sx, sy), (sx + w, sy))
            if index == 0:
                self._tile_rect(self.vent_tile, pg.Rect(0, sy + 42, WORLD_W, WORLD_H - sy - 42))
            else:
                for support_x in (sx + 18, sx + w - 24):
                    pg.draw.polygon(self.scene, (14, 38, 50), [(support_x, sy + 38), (support_x + 8, sy + 38),
                                                             (support_x + 22, sy + 54), (support_x + 16, sy + 54)])
                    pg.draw.line(self.scene, (49, 83, 96), (support_x + 2, sy + 40), (support_x + 20, sy + 53))
        for i, (x, _y, w, _h) in enumerate(game.doors):
            sx, bottom = int(x - cx), int(FLOOR - cy)
            if not -60 < sx < WORLD_W + 60:
                continue
            image = pg.transform.scale(self.door_tile, (w + 10, 64))
            if game.door_locked(i):
                for sy in range(-30, bottom, 64):
                    self.scene.blit(image, (sx - 5, sy))
                beam = pg.Surface((w, max(1, bottom)), pg.SRCALPHA)
                beam.fill((160, 45, 91, 85))
                self.scene.blit(beam, (sx, 0))
                pg.draw.line(self.scene, (216, 110, 157), (sx + w // 2, 0), (sx + w // 2, bottom), 2)
            else:
                # Open doorway is visibly empty, with the frame retained on either side.
                pg.draw.line(self.scene, (83, 176, 177), (sx - 6, 0), (sx - 6, bottom))
                pg.draw.line(self.scene, (44, 77, 91), (sx + w + 6, 0), (sx + w + 6, bottom), 3)
        for r in game.relays:
            sx, sy = int(r.x - cx), int(FLOOR - cy)
            image = pg.transform.scale(self.relay_image, (28, 40))
            self.scene.blit(image, (sx - 14, sy - 40))
            color = ACCENT if r.active else (224, 164, 104)
            pg.draw.rect(self.scene, color, (sx - 5, sy - 29, 11, 6))
            if abs(game.player.x - r.x) < 80 and not r.active:
                prompt = "S / DOWN : LINK" if game.relay_secure(r) else "CLEAR SECURITY"
                self.label(prompt, (sx, sy - 53), color)
        for x, width in game.hazards:
            sx, sy = int(x - cx), int(FLOOR - cy)
            color = (227, 95, 146) if game.hazard_active() else (157, 131, 92)
            for dx in range(0, width, 10):
                pg.draw.line(self.scene, color, (sx + dx, sy + 2), (sx + dx + 7, sy + 6), 2)
                if game.hazard_active():
                    top = sy - 7 - (dx + game.frames) % 9
                    pg.draw.lines(self.scene, (227, 155, 196), False,
                                  [(sx + dx, sy), (sx + dx + 3, top), (sx + dx + 6, sy - 3)])
        if game.variant == "campaign":
            x = int(game.exit_x - cx)
            self.scene.blit(self.portal, (x - 27, int(FLOOR - cy) - 76))
            self.label("EXTRACTION / S", (x, FLOOR - cy - 87), ACCENT)

    def lighting(self, game, camera):
        for world_x in range(80, game.width, 320):
            x = int(world_x - camera[0])
            if -100 < x < WORLD_W + 100:
                self.scene.blit(self.light_pool, (x - 80, 5), special_flags=pg.BLEND_RGB_ADD)
        for event in game.events:
            if event["kind"] == "shot":
                x, y = int(event["x"] - camera[0]), int(event["y"] - camera[1])
                self.scene.blit(self.muzzle_pool, (x - 45, y - 45), special_flags=pg.BLEND_RGB_ADD)

    def label(self, text, pos, color):
        image = self.small.render(text, True, color)
        shadow = self.small.render(text, True, (4, 9, 19))
        rect = image.get_rect(center=(round(pos[0]), round(pos[1])))
        self.scene.blit(shadow, rect.move(1, 1))
        self.scene.blit(image, rect)

    def _actor(self, image, body, pos, camera, player=False):
        x, y = pos[0] - camera[0], pos[1] - camera[1]
        center = x + body.w // 2
        feet = y + body.h
        shadow = pg.Surface((body.w + 18, 9), pg.SRCALPHA)
        pg.draw.ellipse(shadow, (2, 7, 15, 125), shadow.get_rect())
        if (player and body.grounded) or (not player and body.kind != "drone"):
            self.scene.blit(shadow, (int(center - shadow.get_width() // 2), int(feet - 4)))
        # Frames use a fixed source canvas, so animation keeps the feet anchored.
        self.scene.blit(image, (round(center - image.get_width() // 2), round(feet - image.get_height())))

    def actors(self, game, alpha, previous, camera):
        for e in game.enemies:
            old = previous.get(e.uid, (e.x, e.y))
            pos = (old[0] + (e.x - old[0]) * alpha, old[1] + (e.y - old[1]) * alpha)
            if not -100 < pos[0] - camera[0] < WORLD_W + 100:
                continue
            if e.kind == "stalker":
                group, scale = "stalker_run" if old[0] != e.x else "stalker_idle", .85
            elif e.kind in ("titan", "dummy"):
                group, scale = "titan_shoot" if e.windup else "titan_idle", 1.1 if e.kind == "titan" else .7
            else:
                group, scale = e.kind, .8 if e.kind == "drone" else 1.35
            self._actor(self.frame(group, game.frames // 3, e.facing, scale), e, pos, camera)
            sx, sy = pos[0] - camera[0] + e.w // 2, pos[1] - camera[1]
            if e.hp < ENEMY_HP[e.kind]:
                pg.draw.rect(self.scene, (19, 19, 33), (sx - 17, sy - 8, 34, 3))
                pg.draw.rect(self.scene, (201, 116, 139), (sx - 17, sy - 8, 34 * max(e.hp, 0) / ENEMY_HP[e.kind], 3))
            if e.windup:
                pg.draw.circle(self.scene, (236, 176, 111), (round(sx), round(sy - 15)), 3, 1)
        p = game.player
        old = previous.get(0, (p.x, p.y))
        pos = (old[0] + (p.x - old[0]) * alpha, old[1] + (p.y - old[1]) * alpha)
        facing = 1 if game.aim[0] >= p.x + p.w // 2 else -1
        group = "courier_jump" if not p.grounded else "courier_run" if p.vx else "courier_idle"
        phase = (0 if p.vy < 0 else 5) if group == "courier_jump" else game.frames // 3
        image = self.frame(group, phase, facing)
        if p.hp <= 0:
            image = pg.transform.rotate(image, 90)
        self._actor(image, p, pos, camera, player=True)
        x, y = pos[0] - camera[0] + p.w // 2, pos[1] - camera[1] + 15
        if p.hp > 0:
            # Shaded stock/barrel follows mouse aim independently of the body animation.
            angle = math.atan2(game.aim[1] - (pos[1] + 15), game.aim[0] - (pos[0] + p.w // 2))
            tip = (x + math.cos(angle) * 24, y + math.sin(angle) * 24)
            pg.draw.line(self.scene, (11, 17, 26), (x, y + 1), tip, 5)
            pg.draw.line(self.scene, (110, 130, 145), (x, y), tip, 3)
            pg.draw.line(self.scene, (210, 219, 228), (x, y - 1), (tip[0], tip[1] - 1))
            pg.draw.circle(self.scene, ((110, 220, 233), (231, 182, 116), (211, 137, 226))[game.weapon],
                           (round(tip[0]), round(tip[1])), 2)
        if p.shield:
            halo = pg.Surface((64, 68), pg.SRCALPHA)
            pg.draw.ellipse(halo, (103, 202, 228, 85), (5, 4, 54, 61), 2)
            self.scene.blit(halo, (int(x - 32), int(y - 33)))

    def effects(self, game, camera, particles, floaters):
        cx, cy = camera
        for s in game.shots:
            x, y = s.x - cx, s.y - cy
            color = (224, 107, 147) if s.hostile else ((92, 206, 223), (231, 183, 113), (199, 125, 227))[s.weapon]
            pg.draw.line(self.scene, (44, 53, 77), (x - s.vx * .3, y - s.vy * .3), (x, y), 4)
            pg.draw.line(self.scene, color, (x - s.vx * .3, y - s.vy * .3), (x, y), 2)
            pg.draw.circle(self.scene, (239, 238, 240), (round(x), round(y)), 1)
        for f in game.fields:
            x, y = round(f["x"] - cx), round(f["y"] - cy)
            halo = pg.Surface((190, 190), pg.SRCALPHA)
            for r in range(85, 10, -12):
                pg.draw.circle(halo, (109, 57, 165, 9 + (85 - r) // 4), (95, 95), r)
            self.scene.blit(halo, (x - 95, y - 95))
        for item in game.pickups:
            x, y = round(item.x - cx), round(item.y - cy)
            color = POWER_COLORS[item.kind]
            pg.draw.ellipse(self.scene, (9, 17, 26), (x - 9, y + 8, 18, 6))
            pg.draw.rect(self.scene, (29, 39, 52), (x - 7, y - 11, 14, 19), border_radius=3)
            pg.draw.rect(self.scene, (105, 121, 133), (x - 6, y - 11, 12, 3))
            pg.draw.rect(self.scene, color, (x - 4, y - 6, 8, 10), border_radius=2)
            pg.draw.line(self.scene, (215, 229, 230), (x - 2, y - 5), (x - 2, y + 2))
            if abs(game.player.x - item.x) < 100:
                self.label(item.kind.upper(), (x, y - 21), color)
        for e in particles:
            x, y = e["x"] - cx, e["y"] - cy
            pg.draw.line(self.scene, e["color"], (x, y), (x - e["vx"] * .015, y - e["vy"] * .015))
        for e in floaters:
            self.label(e["text"], (e["x"] - cx, e["y"] - cy), (228, 181, 113))

    def render(self, game, alpha, previous, camera, particles, floaters):
        self.background(game, camera)
        self.environment(game, camera)
        self.lighting(game, camera)
        self.actors(game, alpha, previous, camera)
        self.effects(game, camera, particles, floaters)
        return self.scene
