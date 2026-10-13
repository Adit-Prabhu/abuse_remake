"""Heads-up display drawn at window resolution: health, weapons and ammo, messages."""

from __future__ import annotations

import pygame

WEAPON_NAMES = ("LASER", "GRENADE", "ROCKET", "FIREBOMB", "PLASMA", "SABER", "FRISBEE")
WEAPON_COLORS = ((255, 80, 80), (120, 220, 90), (255, 170, 60), (255, 120, 30),
                 (140, 120, 255), (220, 220, 255), (255, 255, 120))


class Hud:
    def __init__(self):
        pygame.font.init()
        self.font = pygame.font.Font(None, 26)
        self.small = pygame.font.Font(None, 20)
        self.big = pygame.font.Font(None, 64)
        self.messages: list[list] = []  # text, frames left

    def say(self, text: str, frames: int = 150) -> None:
        self.messages.append([text, frames])

    def draw(self, screen: pygame.Surface, game, stats: dict) -> None:
        w, h = screen.get_size()
        p, v = game.player, game.view
        # health bar
        hp = max(0, min(100, p.hp))
        bar = pygame.Rect(20, h - 44, 220, 18)
        pygame.draw.rect(screen, (30, 30, 30), bar, border_radius=4)
        col = (90, 220, 110) if hp > 40 else ((240, 200, 60) if hp > 15 else (240, 60, 60))
        pygame.draw.rect(screen, col, (bar.x, bar.y, bar.w * hp // 100, bar.h), border_radius=4)
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
