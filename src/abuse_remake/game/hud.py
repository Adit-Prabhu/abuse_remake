"""Heads-up display drawn at window resolution: health, weapons and ammo, messages, the
active power-up and the training level's help text."""

from __future__ import annotations

import pygame

WEAPON_NAMES = ("LASER", "GRENADE", "ROCKET", "FIREBOMB", "PLASMA", "SABER", "FRISBEE")
WEAPON_COLORS = ((255, 80, 80), (120, 220, 90), (255, 170, 60), (255, 120, 30),
                 (140, 120, 255), (220, 220, 255), (255, 255, 120))
# people.lsp:40-43: the power-up images the original puts at the view's top right (cop.c:816-878)
POWER_IMAGES = {1: "fast_image", 2: "fly_image", 3: "sneaky_image", 4: "b_check_image"}
POWER_NAMES = {1: "SPEED", 2: "FLIGHT", 3: "INVISIBILITY", 4: "ULTRA HEALTH"}


class Hud:
    def __init__(self, sprites=None):
        pygame.font.init()
        self.font = pygame.font.Font(None, 26)
        self.small = pygame.font.Font(None, 20)
        self.big = pygame.font.Font(None, 64)
        self.messages: list[list] = []  # text, frames left
        self.sprites = sprites
        self.help_text = ""
        self.help_frames = 0

    def say(self, text: str, frames: int = 150) -> None:
        self.messages.append([text, frames])

    def show_help(self, text: str, frames: int = 30) -> None:
        """The original's help line (game::show_help); a training message re-sends it each tick."""
        self.help_text, self.help_frames = text, frames

    def draw(self, screen: pygame.Surface, game, stats: dict) -> None:
        w, h = screen.get_size()
        p, v = game.player, game.view
        # health bar
        cap = 200 if p.lvars.get("special_power") == 4 else 100  # ultra health doubles the cap
        hp = max(0, min(cap, p.hp))
        bar = pygame.Rect(20, h - 44, 220, 18)
        pygame.draw.rect(screen, (30, 30, 30), bar, border_radius=4)
        col = (90, 220, 110) if hp > 40 else ((240, 200, 60) if hp > 15 else (240, 60, 60))
        pygame.draw.rect(screen, col, (bar.x, bar.y, bar.w * hp // cap, bar.h), border_radius=4)
        pygame.draw.rect(screen, (200, 200, 200), bar, 1, border_radius=4)
        screen.blit(self.font.render(f"{p.hp}", True, (255, 255, 255)), (bar.right + 8, bar.y - 1))
        # weapons
        x = 300
        for i, name in enumerate(WEAPON_NAMES[:4]):
            owned = v.weapons[i] != -1
            if not owned:
                continue
            ammo = v.weapons[i]
            sel = i == v.current_weapon
            label = f"{i + 1} {name} {ammo if i else ('∞' if ammo == 0 else ammo)}"
            surf = self.small.render(label, True, WEAPON_COLORS[i] if sel else (150, 150, 150))
            r = surf.get_rect(topleft=(x, h - 42))
            if sel:
                pygame.draw.rect(screen, (60, 60, 60), r.inflate(10, 8), border_radius=4)
            screen.blit(surf, r)
            x = r.right + 18
        # the active power-up and whether the special key is in use
        power = p.lvars.get("special_power", 0)
        if power in POWER_IMAGES:
            img = self.sprites.image("art/misc.spe", POWER_IMAGES[power]) if self.sprites else None
            x = w - 20
            if img is not None:
                img = pygame.transform.scale(img, (img.get_width() * 3, img.get_height() * 3))
                x -= img.get_width()
                screen.blit(img, (x, 14))
            label = self.small.render(f"{POWER_NAMES[power]}  (hold right mouse or Shift)", True, (200, 230, 255))
            screen.blit(label, (x - label.get_width() - 10, 22))
        # help text
        if self.help_frames > 0 and self.help_text:
            surf = self.font.render(self.help_text, True, (255, 240, 170))
            box = surf.get_rect(midbottom=(w // 2, h - 64)).inflate(24, 12)
            shade = pygame.Surface(box.size, pygame.SRCALPHA)
            shade.fill((0, 0, 0, 170))
            screen.blit(shade, box)
            screen.blit(surf, surf.get_rect(center=box.center))
            self.help_frames -= 1
        # stats
        t = stats.get("ticks", 0) // 15
        info = f"{t // 60}:{t % 60:02d}   kills {stats.get('kills', 0)}   secrets {stats.get('secrets', 0)}"
        screen.blit(self.small.render(info, True, (180, 180, 180)), (w - 300, h - 40))
        # messages
        y = 20
        for m in self.messages:
            surf = self.font.render(m[0], True, (255, 255, 255))
            screen.blit(surf, surf.get_rect(midtop=(w // 2, y)))
            y += 28
            m[1] -= 1
        self.messages = [m for m in self.messages if m[1] > 0]

    def center(self, screen, lines, sub=None) -> None:
        w, h = screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        screen.blit(shade, (0, 0))
        y = h // 3
        for i, line in enumerate(lines):
            f = self.big if i == 0 else self.font
            surf = f.render(line, True, (255, 230, 200) if i == 0 else (230, 230, 230))
            screen.blit(surf, surf.get_rect(midtop=(w // 2, y)))
            y += surf.get_height() + 12
        if sub:
            surf = self.small.render(sub, True, (170, 170, 170))
            screen.blit(surf, surf.get_rect(midtop=(w // 2, y + 20)))
