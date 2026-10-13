"""Neon Protocol HUD/menu over a shaded pixel-art world. Reads simulation only."""

from __future__ import annotations

import random

import pygame as pg

from ..engine.neon import LESSONS, WEAPONS
from .neon_art import WORLD_W, RasterArt

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
        self.art = RasterArt()
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
        return (max(-32, min(game.width - WORLD_W + 32, game.player.x - 240)),
                min(235, max(0, game.player.y - 75)))

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
        self.panel((18, 437, 924, 23), (10, 20, 33))
        self.text("A/D MOVE   SPACE JUMP   MOUSE AIM + FIRE   S INTERACT   F DASH   F1 CONTROLS", (28, 443), MUTED,
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
        camera = tuple(old + (new - old) * alpha for old, new in zip(self.prev_cam, self.cam, strict=True))
        self.last_camera = camera
        scene = self.art.render(game, alpha, self.previous, camera, self.effects, self.floaters)
        # Nearest-neighbour preserves authored pixel clusters; HUD stays at native UI resolution.
        pg.transform.scale(scene, (W, H), self.surface)
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
        self.text("NEW CAMPAIGN / FOUR SECURITY CLASSES / THREE ENERGY WEAPONS", (68, 493), MUTED)
        self.text("Pixel art: Luis Zuno / Ansimuz", (680, 493), MUTED, self.label_font)
        return buttons

    def overlay(self, title, lines):
        shade = pg.Surface((W, H), pg.SRCALPHA)
        shade.fill((3, 9, 22, 222))
        self.surface.blit(shade, (0, 0))
        self.panel((160, 142, 640, 270), (8, 20, 35), (45, 86, 103))
        self.text(title, (480, 188), CYAN, self.large, True)
        for i, line in enumerate(lines):
            self.text(line, (480, 246 + i * 29), WHITE if i == 0 else MUTED, self.font, True)
