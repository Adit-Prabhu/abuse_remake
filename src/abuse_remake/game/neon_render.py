"""Neon Protocol's vector art, parallax facility and HUD. Reads simulation only.

All art is repo-authored drawing code. Characters/effects have transparent silhouettes;
there are no external bitmap assets or licensing dependencies.
"""

from __future__ import annotations

import math
import random

import pygame as pg

from ..engine.neon import FLOOR, LESSONS, WEAPONS

W, H = 960, 540
CYAN = (70, 235, 245)
PINK = (237, 87, 221)
GOLD = (255, 192, 100)
WHITE = (225, 241, 252)
MUTED = (130, 155, 184)
INK = (6, 12, 26)
PICKUP_COLORS = {"shield": CYAN, "overcharge": PINK, "speed": GOLD, "health": (94, 242, 168), "ammo": WHITE}


class NeonRenderer:
    def __init__(self, game):
        self.surface = pg.Surface((W, H))
        self.glow = pg.Surface((W, H))
        self.font = pg.font.Font(None, 22)
        self.small = pg.font.Font(None, 17)
        self.label_font = pg.font.Font(None, 15)
        self.large = pg.font.Font(None, 54)
        self.hero_font = pg.font.Font(None, 92)
        self.effects: list[dict] = []
        self.floaters: list[dict] = []
        self.time = 0.0
        self.robot_cache = {}
        rng = random.Random(913)
        self.buildings = [(i * 74, rng.randrange(45, 86), rng.randrange(80, 260)) for i in range(34)]
        self.reset(game)

    def reset(self, game):
        self.current = self._positions(game)
        self.previous = dict(self.current)
        self.cam = self._camera(game)
        self.prev_cam = self.cam
        self.last_camera = self.cam
        self.effects.clear()
        self.floaters.clear()

    @staticmethod
    def _positions(game):
        return {0: (game.player.x, game.player.y), **{e.uid: (e.x, e.y) for e in game.enemies}}

    @staticmethod
    def _camera(game):
        return max(0, min(game.width - W, game.player.x - 340)), 80

    def note_tick(self, game):
        self.previous, self.current = self.current, self._positions(game)
        self.prev_cam, self.cam = self.cam, self._camera(game)
        if abs(self.cam[0] - self.prev_cam[0]) > 150:
            self.prev_cam = self.cam
        rng = random.Random(game.frames * 37)
        for e in game.events:
            kind = e["kind"]
            color = PINK if kind in ("kill", "enemy_shot") else CYAN
            if kind in ("hit", "kill", "pickup", "dash", "impact", "vortex"):
                for _ in range(24 if kind == "kill" else 7):
                    self.effects.append({"x": e["x"], "y": e["y"], "vx": rng.uniform(-85, 85),
                                         "vy": rng.uniform(-100, 20), "life": rng.uniform(.2, .6), "color": color})
            if kind == "hit":
                self.floaters.append({"x": e["x"], "y": e["y"] - 20, "text": str(e["damage"]), "life": .6})

    def update_effects(self, dt):
        self.time += dt
        for e in self.effects:
            e["x"] += e["vx"] * dt
            e["y"] += e["vy"] * dt
            e["life"] -= dt
        self.effects = [e for e in self.effects if e["life"] > 0]
        for e in self.floaters:
            e["y"] -= 30 * dt
            e["life"] -= dt
        self.floaters = [e for e in self.floaters if e["life"] > 0]

    def text(self, text, pos, color=MUTED, font=None, center=False):
        img = (font or self.small).render(text, True, color)
        rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
        self.surface.blit(img, rect)
        return rect

    def line(self, color, start, end, width=1, bloom=True):
        pg.draw.line(self.surface, color, start, end, width)
        if bloom:
            pg.draw.line(self.glow, tuple(c // 3 for c in color), start, end, width + 5)

    def polygon(self, color, points, width=0):
        pg.draw.polygon(self.surface, color, points, width)

    def panel(self, rect, color=(10, 22, 39), outline=(33, 61, 78)):
        pg.draw.rect(self.surface, color, rect, border_radius=8)
        pg.draw.rect(self.surface, outline, rect, 1, border_radius=8)

    def background(self, camera, tick):
        s = self.surface
        s.fill(INK)
        # A luminous horizon and distant skyline scroll independently of the play deck.
        for y in range(0, H, 4):
            brightness = max(0, 1 - abs(y - 215) / 260)
            pg.draw.rect(s, (6 + int(5 * brightness), 12 + int(10 * brightness), 26 + int(20 * brightness)),
                         (0, y, W, 4))
        pg.draw.circle(s, (18, 31, 57), (750 - int(camera[0] * .04), 143), 75)
        pg.draw.circle(s, (32, 54, 83), (750 - int(camera[0] * .04), 143), 75, 1)
        self.line((25, 59, 82), (0, 305), (W, 305))
        for x, bw, bh in self.buildings:
            bx = (x - int(camera[0] * .17)) % 2516 - 90
            if bx > W:
                continue
            pg.draw.rect(s, (10, 18, 35), (bx, 320 - bh, bw, bh))
            pg.draw.rect(s, (23, 40, 61), (bx, 320 - bh, bw, bh), 1)
            for wx in range(8, bw - 5, 14):
                for wy in range(12, bh, 22):
                    if (wx + wy + x) % 4:
                        pg.draw.rect(s, (26, 62, 79), (bx + wx, 320 - bh + wy, 3, 7))
            self.line((26, 79, 100), (bx + 5, 321 - bh), (bx + bw - 5, 321 - bh), bloom=False)
        # Large facility pillars and suspended circuit conduits.
        for x in range(-180, W + 180, 180):
            bx = x - int(camera[0] * .55) % 180
            pg.draw.rect(s, (11, 23, 40), (bx, 18, 28, 422))
            pg.draw.rect(s, (22, 42, 62), (bx, 18, 28, 422), 1)
            self.line((24, 85, 102), (bx + 6, 90), (bx + 6, 285), bloom=False)
            self.line((20, 54, 72), (bx + 28, 92), (bx + 180, 92), bloom=False)
        # Perspective grid beneath the elevated deck.
        for y in (447, 462, 484, 514):
            self.line((22, 48, 69), (0, y), (W, y), bloom=False)
        for x in range(-W, W * 2, 110):
            self.line((19, 43, 63), (480 + (x - 480) * .65, 440), (x, 540), bloom=False)
        for i in range(12):
            x = (i * 137 + tick * .35 - camera[0] * .1) % W
            pg.draw.circle(s, (48, 92, 109), (int(x), 115 + (i * 47) % 220), 1)

    def environment(self, game, camera):
        cx, cy = camera
        for i, (x, y, w, h) in enumerate(game.platforms):
            sx, sy = round(x - cx), round(y - cy)
            if sx > W or sx + w < 0:
                continue
            self.panel((sx, sy, w, max(h, 24)), (16, 30, 49), (37, 60, 78))
            color = CYAN if i % 3 else (96, 146, 182)
            self.line(color, (sx, sy), (sx + w, sy), 2)
            for dx in range(15, w, 38):
                if 0 <= sx + dx <= W:
                    self.line((31, 70, 88), (sx + dx, sy + 5), (sx + dx + 15, sy + 15), bloom=False)
            if i:
                self.line((24, 60, 78), (sx + 15, sy + h), (sx + 35, sy + h + 13), bloom=False)
                self.line((24, 60, 78), (sx + w - 15, sy + h), (sx + w - 35, sy + h + 13), bloom=False)
        for i, (x, _y, w, _h) in enumerate(game.doors):
            sx = int(x - cx)
            if not -50 < sx < W + 50:
                continue
            locked = game.door_locked(i)
            color = PINK if locked else CYAN
            self.line(color, (sx - 5, 90), (sx - 5, FLOOR - cy), 3)
            self.line(color, (sx + w + 5, 90), (sx + w + 5, FLOOR - cy), 3)
            if locked:
                for y in range(90, FLOOR - cy, 10):
                    self.line((130, 42, 127), (sx, y), (sx + w, y + 6), bloom=False)
                self.text("LOCKED", (sx - 10, 72), PINK, self.label_font)
        for r in game.relays:
            sx, sy = int(r.x - cx), int(r.y - cy)
            if not -100 < sx < W + 100:
                continue
            col = CYAN if r.active else PINK
            self.panel((sx - 17, sy - 8, 34, 48), (13, 26, 44), col)
            self.line(col, (sx - 12, sy), (sx + 12, sy), 2)
            self.line(col, (sx - 10, sy + 8), (sx + 5, sy + 8))
            self.line(col, (sx - 10, sy + 14), (sx, sy + 14))
            self.text("ONLINE" if r.active else "RELAY", (sx - 22, sy - 26), col, self.label_font)
            if abs(game.player.x - r.x) < 90 and not r.active:
                text = "S / DOWN: LINK" if game.relay_secure(r) else "CLEAR NEARBY SECURITY"
                self.text(text, (sx, sy - 47), col, self.small, True)
        for x, width in game.hazards:
            sx, sy = x - cx, FLOOR - cy
            active = game.hazard_active()
            col = PINK if active else GOLD if game.frames % 90 >= 45 else (54, 79, 98)
            self.line(col, (sx, sy - 3), (sx + width, sy - 3), 3)
            for dx in range(5, width, 14):
                self.line(col, (sx + dx, sy - 8), (sx + dx + 5, sy - 2), bloom=active)
            if active:
                for dx in range(0, width, 20):
                    self.line(PINK, (sx + dx, sy), (sx + dx + 10, sy - 15), bloom=True)
        if game.variant == "campaign":
            sx = game.exit_x - cx
            self.line(CYAN, (sx - 22, 366), (sx - 22, 440), 3)
            self.line(CYAN, (sx + 22, 366), (sx + 22, 440), 3)
            self.line(CYAN, (sx - 22, 366), (sx + 22, 366), 3)
            self.text("EXTRACTION / S", (sx, 348), CYAN, self.small, True)

    def robot(self, kind, facing, phase):
        key = (kind, facing, phase)
        if key in self.robot_cache:
            return self.robot_cache[key]
        s = pg.Surface((88, 92), pg.SRCALPHA)
        col = PINK if kind in ("drone", "stalker") else GOLD if kind == "titan" else (176, 145, 255)
        dark = (37, 25, 51) if kind != "titan" else (44, 36, 33)

        def poly(points, color=dark, edge=True):
            pg.draw.polygon(s, color, points)
            if edge:
                pg.draw.polygon(s, col, points, 1)

        if kind == "drone":
            poly([(20, 44), (31, 32), (57, 32), (68, 44), (55, 53), (33, 53)])
            poly([(8, 37), (20, 40), (28, 48), (14, 46)])
            poly([(60, 48), (69, 40), (80, 37), (73, 46)])
            pg.draw.circle(s, col, (44, 42), 6)
            pg.draw.circle(s, WHITE, (44, 42), 3)
            pg.draw.line(s, col, (19, 51), (11, 58 + phase), 2)
            pg.draw.line(s, col, (68, 51), (76, 58 + phase), 2)
            anchor = (44, 42)
        elif kind == "stalker":
            poly([(28, 35), (43, 25), (59, 33), (51, 51), (34, 51)])
            poly([(47, 24), (63, 20), (63, 31), (51, 36)])
            pg.draw.line(s, WHITE, (55, 26), (62, 25), 2)
            offset = (phase - 1) * 4
            pg.draw.lines(s, col, False, [(35, 48), (22 - offset, 61), (30 - offset, 77)], 3)
            pg.draw.lines(s, col, False, [(49, 49), (56 + offset, 64), (70 + offset, 77)], 3)
            pg.draw.lines(s, col, False, [(55, 37), (67, 48), (77, 40)], 2)
            anchor = (44, 58)
        elif kind == "titan":
            poly([(18, 23), (30, 18), (63, 18), (72, 28), (63, 62), (26, 62)])
            poly([(35, 10), (57, 10), (61, 22), (32, 22)])
            pg.draw.line(s, WHITE, (38, 17), (55, 17), 3)
            poly([(10, 28), (22, 28), (22, 53), (9, 55)])
            poly([(66, 28), (83, 28), (83, 49), (66, 49)])
            pg.draw.rect(s, WHITE, (76, 31, 8, 4))
            poly([(26, 60), (40, 60), (38, 82), (21, 82)])
            poly([(50, 60), (62, 60), (69, 82), (50, 82)])
            pg.draw.circle(s, col, (46, 38), 8, 2)
            pg.draw.circle(s, WHITE, (46, 38), 3)
            anchor = (44, 55)
        else:
            poly([(29, 30), (56, 30), (65, 47), (53, 68), (29, 68), (22, 47)])
            poly([(30, 19), (54, 19), (58, 29), (29, 29)])
            pg.draw.line(s, WHITE, (36, 25), (53, 25), 3)
            poly([(27, 67), (40, 67), (38, 79), (24, 79)])
            poly([(45, 67), (56, 67), (63, 79), (46, 79)])
            poly([(57, 39), (77, 39), (80, 47), (56, 47)])
            pg.draw.circle(s, col, (40, 48), 11, 2)
            if kind == "dummy":
                pg.draw.circle(s, WHITE, (40, 48), 5, 1)
            anchor = (44, 61)
        if facing < 0:
            s = pg.transform.flip(s, True, False)
            anchor = (88 - anchor[0], anchor[1])
        self.robot_cache[key] = (s, anchor)
        return s, anchor

    def actors(self, game, alpha, camera):
        cx, cy = camera
        for e in game.enemies:
            old = self.previous.get(e.uid, (e.x, e.y))
            x, y = old[0] + (e.x - old[0]) * alpha - cx, old[1] + (e.y - old[1]) * alpha - cy
            if x < -100 or x > W + 100:
                continue
            sprite, anchor = self.robot(e.kind, e.facing, game.frames // 3 % 3)
            self.surface.blit(sprite, (int(x + e.w // 2 - anchor[0]), int(y + e.h // 2 - anchor[1])))
            self.text(e.kind.upper(), (x + e.w // 2, y - 36), MUTED, self.label_font, True)
            if e.windup:
                pg.draw.circle(self.surface, GOLD, (int(x + e.w // 2), int(y - 50)), 4 + e.windup // 3, 1)
            # Visible damage bar makes weapon effectiveness readable.
            from ..engine.neon import ENEMY_HP

            if e.hp < ENEMY_HP[e.kind]:
                pg.draw.rect(self.surface, (41, 36, 58), (x - 5, y - 8, e.w + 10, 3))
                pg.draw.rect(self.surface, PINK, (x - 5, y - 8, (e.w + 10) * max(e.hp, 0) / ENEMY_HP[e.kind], 3))
        p = game.player
        old = self.previous.get(0, (p.x, p.y))
        x = old[0] + (p.x - old[0]) * alpha - cx + p.w // 2
        y = old[1] + (p.y - old[1]) * alpha - cy + p.h
        if p.hp <= 0:
            self.line(CYAN, (x - 15, y - 5), (x + 20, y - 5), 4)
            return
        col = GOLD if p.overcharge else CYAN
        if p.iframes and game.frames % 2:
            col = WHITE
        # Articulated courier: boots/legs, segmented chest plate, helmet/visor, free aim arm.
        stride = math.sin(game.frames * .9) * 7 if p.vx and p.grounded else 0
        for side in (-1, 1):
            foot = x + side * 8 + stride * side
            self.line((56, 89, 112), (x + side * 5, y - 21), (foot, y - 5), 5, False)
            self.line(col, (x + side * 5, y - 21), (foot, y - 5), 1)
            self.line(WHITE, (foot - 4, y - 2), (foot + 5, y - 2), 3, False)
        points = [(x - 11, y - 34), (x - 5, y - 38), (x + 9, y - 34), (x + 7, y - 20), (x - 7, y - 20)]
        self.polygon((20, 43, 61), points)
        self.polygon(col, points, 1)
        self.line(col, (x - 6, y - 30), (x + 6, y - 30), 2)
        self.line(col, (x - 4, y - 24), (x + 4, y - 24))
        self.polygon((34, 60, 76), [(x - 7, y - 47), (x + 5, y - 47), (x + 10, y - 41), (x + 5, y - 36),
                                   (x - 7, y - 37), (x - 10, y - 42)])
        self.line(WHITE, (x - 6, y - 42), (x + 8, y - 42), 2)
        ax, ay = game.aim[0] - (x + cx), game.aim[1] - (y + cy - 27)
        angle = math.atan2(ay, ax)
        tip = (x + math.cos(angle) * 30, y - 27 + math.sin(angle) * 30)
        self.line((53, 75, 97), (x, y - 27), tip, 7, False)
        self.line((CYAN, GOLD, PINK)[game.weapon], (x + math.cos(angle) * 11, y - 27 + math.sin(angle) * 11), tip, 2)
        if p.shield:
            pg.draw.ellipse(self.surface, CYAN, (x - 27, y - 58, 54, 65), 1)
            pg.draw.ellipse(self.glow, (16, 52, 60), (x - 29, y - 60, 58, 69), 5)

    def combat(self, game, camera):
        cx, cy = camera
        for s in game.shots:
            x, y = s.x - cx, s.y - cy
            color = PINK if s.hostile else (CYAN, GOLD, PINK)[s.weapon]
            self.line(color, (x - s.vx * .6, y - s.vy * .6), (x, y), 2 if s.weapon != 1 else 3)
            pg.draw.circle(self.surface, WHITE, (int(x), int(y)), 2)
        for f in game.fields:
            x, y = int(f["x"] - cx), int(f["y"] - cy)
            pg.draw.circle(self.surface, (82, 32, 101), (x, y), 93, 1)
            for i in range(3):
                radius = 15 + (game.frames * 3 + i * 24) % 80
                pg.draw.circle(self.surface, PINK, (x, y), radius, 1)
                pg.draw.circle(self.glow, (40, 14, 40), (x, y), radius, 4)
        for item in game.pickups:
            x, y = int(item.x - cx), int(item.y - cy + math.sin(self.time * 3 + item.x) * 3)
            color = PICKUP_COLORS[item.kind]
            self.polygon((12, 32, 49), [(x, y - 14), (x + 14, y), (x, y + 14), (x - 14, y)])
            self.polygon(color, [(x, y - 14), (x + 14, y), (x, y + 14), (x - 14, y)], 1)
            mark = {"health": "+", "shield": "S", "overcharge": "O", "speed": ">", "ammo": "II"}[item.kind]
            self.text(mark, (x, y), color, self.font, True)
            self.text(item.kind.upper(), (x, y + 24), color, self.label_font, True)
        for e in self.effects:
            x, y = int(e["x"] - cx), int(e["y"] - cy)
            self.line(e["color"], (x, y), (x - e["vx"] * .025, y - e["vy"] * .025))
        for e in self.floaters:
            self.text(e["text"], (e["x"] - cx, e["y"] - cy), GOLD, self.small, True)

    def hud(self, game, message=""):
        p = game.player
        self.panel((18, 16, 249, 59))
        self.text("NEON / PROTOCOL", (31, 27), CYAN, self.font)
        self.text(f"{game.variant.upper()}  /  {game.difficulty.upper()}", (31, 52), MUTED)
        self.panel((645, 16, 297, 59))
        if game.variant == "horde":
            objective = f"WAVE {game.wave:02}  /  {len(game.enemies):02} HOSTILES"
            detail = f"NEXT WAVE IN {game.break_ticks / 15:.1f}s" if game.break_ticks else "SURVIVE THE SECURITY SWARM"
        elif game.variant == "tutorial":
            objective = LESSONS[min(game.lesson, 6)][0]
            detail = "TRAINING / SAFE SIMULATION"
        else:
            count = sum(r.active for r in game.relays)
            objective = f"RELAYS {count} / 3  •  " + ("EXTRACT" if count == 3 else "BREACH SECURITY")
            detail = ("INGRESS", "REACTOR", "CORE", "EXTRACTION")[count] + " SECTOR"
        self.text(objective, (660, 27), WHITE, self.font)
        self.text(detail, (660, 52), CYAN)
        # Bottom combat deck, with all three weapons always shown.
        self.panel((18, 466, 245, 58))
        self.text("INTEGRITY", (30, 476), MUTED, self.label_font)
        self.text(f"{p.hp:03}", (214, 474), WHITE, self.font)
        pg.draw.rect(self.surface, (33, 50, 65), (30, 500, 218, 6), border_radius=2)
        pg.draw.rect(self.surface, CYAN if p.hp > 25 else PINK, (30, 500, 218 * p.hp // 100, 6), border_radius=2)
        for slot, name in enumerate(WEAPONS):
            x = 280 + slot * 177
            color = (CYAN, GOLD, PINK)[slot]
            self.panel((x, 466, 165, 58), (15, 31, 48) if game.weapon == slot else (9, 18, 33),
                       color if game.weapon == slot else (29, 47, 66))
            self.text(f"0{slot + 1} / {name}", (x + 10, 478), color if game.weapon == slot else MUTED, self.small)
            self.text("UNLIMITED" if slot == 0 else f"{game.ammo[slot]:02} CHARGES", (x + 10, 501), MUTED,
                      self.label_font)
        self.panel((823, 466, 119, 58))
        self.text("F / PHASE DASH", (833, 478), CYAN, self.label_font)
        dash = "READY" if not p.dash_cooldown else f"{p.dash_cooldown / 15:.1f}s"
        self.text(dash, (833, 500), WHITE)
        self.text("A/D MOVE   SPACE JUMP   MOUSE AIM + FIRE   S INTERACT   F DASH   F1 CONTROLS", (24, 449), MUTED,
                  self.label_font)
        timers = [("SHIELD", p.shield_time, CYAN), ("OVERCHARGE", p.overcharge, PINK), ("SPEED", p.speed, GOLD)]
        for i, (name, ticks, color) in enumerate(t for t in timers if t[1]):
            self.text(f"{name}  {ticks / 15:.1f}s", (30, 88 + i * 20), color)
        if game.variant == "tutorial":
            self.panel((145, 91, 670, 51), (12, 27, 44), (46, 94, 114))
            self.text(LESSONS[min(game.lesson, 6)][1], (480, 116), WHITE, self.font, True)
        elif message:
            self.panel((245, 91, 470, 38), (12, 27, 44), (46, 94, 114))
            self.text(message, (480, 110), WHITE, self.font, True)
        # Objective path, not a hidden enemy map.
        if game.variant == "campaign":
            for i, r in enumerate(game.relays):
                color = CYAN if r.active else (69, 77, 99)
                pg.draw.circle(self.surface, color, (330 + i * 43, 40), 5)
                if i < 2:
                    self.line(color, (337 + i * 43, 40), (365 + i * 43, 40), bloom=False)
        self.text(f"{game.frames // 900:02}:{game.frames // 15 % 60:02}   {game.kills:02} KILLS", (466, 28), MUTED)

    def render(self, game, alpha=1.0, message="", hud=True):
        camera = (self.prev_cam[0] + (self.cam[0] - self.prev_cam[0]) * alpha, self.cam[1])
        self.last_camera = camera
        self.glow.fill((0, 0, 0))
        self.background(camera, game.frames)
        self.environment(game, camera)
        self.actors(game, alpha, camera)
        self.combat(game, camera)
        blur = pg.transform.smoothscale(self.glow, (240, 135))
        blur = pg.transform.smoothscale(blur, (W, H))
        self.surface.blit(blur, (0, 0), special_flags=pg.BLEND_RGB_ADD)
        if hud:
            self.hud(game, message)
        return self.surface

    def menu(self, game, mouse, selection=0, difficulty=None):
        self.render(game, 1, hud=False)
        shade = pg.Surface((W, H), pg.SRCALPHA)
        shade.fill((4, 9, 23, 155))
        self.surface.blit(shade, (0, 0))
        self.text("AN OPTIONAL ABUSE EXPANSION", (66, 61), CYAN, self.small)
        self.text("NEON", (60, 93), WHITE, self.hero_font)
        self.text("PROTOCOL", (63, 170), CYAN, self.hero_font)
        self.text("BREACH THE GRID. TAKE BACK THE CORE.", (68, 258), MUTED, self.font)
        buttons = []
        entries = [("campaign", "01 / CAMPAIGN", "Three sectors. One extraction."),
                   ("horde", "02 / HORDE", "Escalating waves. No way out."),
                   ("tutorial", "03 / TRAINING", "Learn every control by playing."),
                   ("controls", "04 / FIELD MANUAL", "Controls, weapons and power-ups.")]
        for i, (action, name, desc) in enumerate(entries):
            rect = pg.Rect(615, 105 + i * 78, 286, 66)
            hot = rect.collidepoint(mouse) or selection == i
            self.panel(rect, (16, 37, 54) if hot else (8, 19, 35), CYAN if hot else (32, 51, 71))
            self.text(name, (rect.x + 19, rect.y + 14), WHITE if hot else MUTED, self.font)
            self.text(desc, (rect.x + 19, rect.y + 39), MUTED, self.small)
            if hot:
                self.line(CYAN, (rect.x + 4, rect.y + 15), (rect.x + 4, rect.bottom - 15), 2, False)
            buttons.append((action, rect))
        self.text("C campaign   H horde   T training   F1 controls", (68, 320), WHITE)
        self.text("Up / Down + Enter or click a card", (68, 345), MUTED)
        self.text(f"D / DIFFICULTY: {(difficulty or game.difficulty).upper()}", (68, 396), GOLD)
        self.text("M / Classic & Remastered    Esc / Quit", (68, 423), MUTED)
        self.line((30, 74, 91), (66, 475), (900, 475), bloom=False)
        self.text("NEW CAMPAIGN  /  FOUR SECURITY CLASSES  /  THREE ENERGY WEAPONS", (68, 493), MUTED)
        return buttons

    def overlay(self, title, lines):
        shade = pg.Surface((W, H), pg.SRCALPHA)
        shade.fill((3, 9, 22, 222))
        self.surface.blit(shade, (0, 0))
        self.panel((160, 142, 640, 270), (8, 20, 35), (45, 86, 103))
        self.text(title, (480, 188), CYAN, self.large, True)
        for i, line in enumerate(lines):
            self.text(line, (480, 246 + i * 29), WHITE if i == 0 else MUTED, self.font, True)
