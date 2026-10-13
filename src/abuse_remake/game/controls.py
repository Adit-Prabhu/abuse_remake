"""Control help shared by the legacy and Neon front ends. No gameplay state."""

import pygame

CONTROLS = (
    ("MOVE", "A / D or Left / Right"),
    ("JUMP", "Space / W / Up"),
    ("AIM", "Move the mouse"),
    ("FIRE", "Left click or J"),
    ("INTERACT", "S / Down near a terminal or exit"),
    ("WEAPON", "Number keys, Q / E, scroll wheel"),
    ("PAUSE / HELP", "Esc / F1"),
)


def draw_controls(screen, mode="neon"):
    w, h = screen.get_size()
    factor = min(w / 960, h / 540)
    font = pygame.font.Font(None, max(16, int(25 * factor)))
    small = pygame.font.Font(None, max(14, int(21 * factor)))
    title = pygame.font.Font(None, max(25, int(48 * factor)))
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    shade.fill((4, 9, 23, 240))
    screen.blit(shade, (0, 0))
    x = int(w * .13)
    y = int(h * .10)
    screen.blit(title.render("CONTROLS / FIELD MANUAL", True, (100, 235, 250)), (x, y))
    y += int(65 * factor)
    rows = list(CONTROLS)
    if mode != "classic":
        rows.extend([("DASH", "F • Gamepad X"), ("RESTART", "R • Last checkpoint")])
    if mode != "neon":
        rows.append(("SPECIAL", "Right click / Shift • Ghost toggle G in Remastered"))
    for label, detail in rows:
        screen.blit(font.render(label, True, (235, 240, 250)), (x, y))
        screen.blit(small.render(detail, True, (165, 187, 212)), (int(w * .36), y + 2))
        y += int(32 * factor)
    foot = "Esc / F1 / C to return • Neon: T on title opens the playable tutorial"
    screen.blit(small.render(foot, True, (100, 235, 250)), (x, h - int(50 * factor)))
