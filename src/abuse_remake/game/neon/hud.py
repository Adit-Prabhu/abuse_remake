"""Neon Protocol HUD, menus, field manual and overlays, drawn on the 1280x720 canvas.

Presentation only: reads the game and draws. Fonts are Orbitron and Share Tech Mono
(SIL Open Font License, vendored in assets/neon/fonts).
"""

from __future__ import annotations

import math

import pygame as pg

from ...engine.neon import LESSONS, UPGRADES, WEAPONS
from ...paths import assets_root
from .render import PICKUP_COLORS, WEAPON_COLORS

W, H = 1280, 720
CYAN = (80, 235, 250)
MAGENTA = (255, 80, 220)
AMBER = (255, 190, 90)
WHITE = (230, 240, 255)
MUTED = (120, 140, 170)
RED = (255, 70, 90)
GREEN = (90, 255, 160)
INK = (6, 10, 22)
FALLBACK = {"·": "/", "▸": ">", "◂": "<", "∞": "INF", "←": "<", "→": ">", "↑": "UP", "↓": "DOWN", "−": "-",
            "–": "-", "—": "-", "✓": "+"}

CONTROLS = (
    ("MOVE", "A / D  or  ← →"),
    ("JUMP", "SPACE  or  W   (hold = higher, tap = hop)"),
    ("CLIMB", "W / S on a ladder"),
    ("CROUCH / CRAWL", "hold S"),
    ("DROP THROUGH", "S + SPACE on a thin ledge"),
    ("AIM", "MOUSE — the gun turns all the way around you"),
    ("FIRE", "LEFT CLICK  or  J"),
    ("DASH", "SHIFT / F / RIGHT CLICK  (invulnerable)"),
    ("INTERACT", "E  or  S   (consoles, switches, elevators, exit)"),
    ("WEAPONS", "1–5,  Q,  MOUSE WHEEL"),
    ("MAP", "TAB"),
    ("PAUSE / MANUAL", "ESC  /  F1"),
    ("VOLUME", "−  /  ="),
)
GAMEPAD = "Gamepad: left stick move · right stick aim · A jump · B interact · X dash · RT fire · LB/RB weapons"
MANUAL_PAGES = ("CONTROLS", "WEAPONS", "HOSTILES", "SYSTEMS")
WEAPON_NOTES = (
    "Unlimited. Fast cyan bolts. Your reliable sidearm.",
    "Five-way laser fan. Brutal up close, knocks enemies back.",
    "Instant beam. Pierces every enemy in line and cracks Strider shields.",
    "Arcing plasma that bounces twice, then bursts. Breaks cracked walls.",
    "Three homing micro-missiles that hunt the nearest hostile.",
)
ENEMY_NOTES = (
    ("XENO CRAWLER", "Hangs from ceilings and drops on you. Climbs walls, walks the roof and spits "
                     "acid, leaps gaps and pounces. Its scream wakes the others."),
    ("STINGER", "Circles out of reach, flares red, then dives. Dash through the dive."),
    ("SENTRY", "Hides in walls and ceilings, pops out when it sees you. A red laser sight warns of "
               "the burst. Armoured while hidden."),
    ("STRIDER", "Heavy walker. Its front shield deflects pulse and scatter. Get behind it, or use the "
                "rail, mortar or seekers. Jump its shockwave."),
    ("WATCHER DRONE", "Searchlight patrol. If it spots you, or you shoot it, it sounds an alarm and the "
                      "vent nests open. Kill it fast."),
    ("VENT NEST", "Releases crawlers once disturbed. Destroy it to stop them."),
)
SYSTEM_NOTES = (
    ("SAVE CONSOLES", "Press E: full repair, ammo top-up and a checkpoint. R reloads it."),
    ("POWER-UPS", "Shield absorbs damage · Overcharge doubles damage · Haste · Phase: the dash recharges "
                  "faster and protects you longer."),
    ("VAULT BOOTS", "A double jump, found in the Reactor. Opens new routes."),
    ("KEYCARDS", "A red gate needs the red keycard. Walk into the gate with it."),
    ("SWITCHES", "Open doors. Some doors are timed: run."),
    ("ELEVATORS / PADS", "Stand on an elevator to ride it, or press E at either end to call it. "
                         "Teleport pads link in pairs."),
    ("CRACKED WALLS", "Secrets. Blast them with the plasma mortar."),
    ("ENERGY FLOORS", "Flicker as a warning, then arc. Jump or dash across."),
)


def _font(name: str, size: int) -> pg.font.Font:
    path = assets_root() / "neon" / "fonts" / name
    try:
        return pg.font.Font(str(path), size)
    except (OSError, FileNotFoundError):
        return pg.font.Font(None, int(size * 1.3))


class Hud:
    def __init__(self, art):
        self.art = art
        self.title_font = _font("Orbitron.ttf", 84)
        self.h1 = _font("Orbitron.ttf", 40)
        self.h2 = _font("Orbitron.ttf", 24)
        self.h3 = _font("Orbitron.ttf", 17)
        self.body = _font("ShareTechMono-Regular.ttf", 21)
        self.small = _font("ShareTechMono-Regular.ttf", 17)
        self.tiny = _font("ShareTechMono-Regular.ttf", 14)
        self.messages: list[list] = []  # [text, color, seconds]
        self.time = 0.0

    # ------------------------------------------------------------ primitives
    def clean(self, txt: str, font) -> str:
        """Swap characters the font cannot draw for plain ones (no tofu boxes)."""
        return "".join(ch if ch.isascii() else FALLBACK.get(ch, "?") for ch in txt)

    def text(self, surf, txt, pos, color=WHITE, font=None, anchor="topleft", glow=False):
        font = font or self.body
        txt = self.clean(txt, font)
        img = font.render(txt, True, color)
        r = img.get_rect(**{anchor: (round(pos[0]), round(pos[1]))})
        if glow:
            # rendered on black, so additive blending adds only the letters (no box)
            halo = font.render(txt, True, tuple(v // 3 for v in color), (0, 0, 0))
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                surf.blit(halo, r.move(dx, dy), special_flags=pg.BLEND_RGB_ADD)
        surf.blit(img, r)
        return r

    def panel(self, surf, rect, color=CYAN, fill=(6, 12, 26, 190), corners=True):
        rect = pg.Rect(rect)
        s = pg.Surface(rect.size, pg.SRCALPHA)
        s.fill(fill)
        surf.blit(s, rect)
        pg.draw.rect(surf, tuple(v // 3 for v in color), rect, 1)
        if corners:
            k = 10
            for (x, y), (dx, dy) in (((rect.left, rect.top), (1, 1)), ((rect.right - 1, rect.top), (-1, 1)),
                                     ((rect.left, rect.bottom - 1), (1, -1)),
                                     ((rect.right - 1, rect.bottom - 1), (-1, -1))):
                pg.draw.line(surf, color, (x, y), (x + dx * k, y), 2)
                pg.draw.line(surf, color, (x, y), (x, y + dy * k), 2)

    def bar(self, surf, rect, frac, color, segments=20, back=(20, 28, 44)):
        rect = pg.Rect(rect)
        seg_w = rect.w / segments
        filled = frac * segments
        for i in range(segments):
            r = pg.Rect(rect.x + round(i * seg_w) + 1, rect.y, max(1, round(seg_w) - 2), rect.h)
            pg.draw.rect(surf, color if i < filled else back, r)

    def say(self, text, color=WHITE, seconds=2.5):
        self.messages = [m for m in self.messages if m[0] != text][-3:]
        self.messages.append([text, color, seconds])

    def update(self, dt):
        self.time += dt
        for m in self.messages:
            m[2] -= dt
        self.messages = [m for m in self.messages if m[2] > 0]

    # ------------------------------------------------------------ in-game HUD
    def draw(self, surf, game, hint: str = "", show_hint_strip: bool = True):
        p = game.player
        t = self.time
        # integrity
        self.panel(surf, (20, 18, 330, 92))
        self.text(surf, "INTEGRITY", (36, 28), MUTED, self.h3)
        frac = max(0, p.hp) / p.max_hp
        col = CYAN if frac > 0.5 else AMBER if frac > 0.25 else RED
        if frac <= 0.25 and int(t * 4) % 2:
            col = (255, 140, 150)
        self.bar(surf, (36, 54, 240, 16), frac, col)
        self.text(surf, f"{max(0, p.hp):03d}", (334, 46), WHITE, self.h2, "topright")
        if p.shield:
            self.bar(surf, (36, 76, 240, 6), min(1, p.shield / 50), (90, 200, 255), segments=10)
            self.text(surf, f"SHIELD {p.shield}", (334, 72), (90, 200, 255), self.tiny, "topright")
        x = 36
        for key in p.keys:
            c = PICKUP_COLORS.get("key_" + key, WHITE)
            pg.draw.rect(surf, c, (x, 88, 22, 14), border_radius=3)
            self.text(surf, "KEY", (x + 11, 95), INK, self.tiny, "center")
            x += 28
        if p.boots:
            self.text(surf, "BOOTS", (x + 2, 88), PICKUP_COLORS["boots"], self.tiny)
        timers = [("OVERCHARGE", p.overcharge, 300, MAGENTA), ("HASTE", p.haste, 360, AMBER),
                  ("PHASE", p.phase, 450, (170, 120, 255)), ("SHIELD", p.shield_t, 600, (90, 200, 255))]
        y = 120
        for name, left, full, c in timers:
            if left:
                self.text(surf, name, (24, y), c, self.tiny)
                self.bar(surf, (120, y + 4, 120, 6), left / full, c, segments=12)
                y += 18
        # weapon
        self._weapon_panel(surf, game)
        # dash
        cx, cy = 398, H - 66
        pg.draw.circle(surf, (14, 22, 40), (cx, cy), 28)
        ready = p.dash_cd == 0
        if not ready:
            frac = 1 - p.dash_cd / max(1, 30)
            pg.draw.arc(surf, CYAN, (cx - 26, cy - 26, 52, 52), math.pi / 2, math.pi / 2 + frac * math.tau, 4)
        else:
            pg.draw.circle(surf, CYAN, (cx, cy), 26, 3)
        self.text(surf, "DASH", (cx, cy), CYAN if ready else MUTED, self.h3 if ready else self.small, "center")
        self.text(surf, "SHIFT", (cx, cy + 40), MUTED, self.tiny, "center")
        # objective
        self._objective(surf, game)
        # boss
        boss = next((e for e in game.enemies if e.kind == "warden" and e.alerted), None)
        if boss:
            self.panel(surf, (W // 2 - 250, 18, 500, 56), RED)
            self.text(surf, f"CORE WARDEN  /  PHASE {boss.phase}", (W // 2, 26), RED, self.h3, "midtop")
            self.bar(surf, (W // 2 - 230, 52, 460, 12), max(0, boss.hp) / boss.max_hp, RED, segments=36)
            for frac in (0.66, 0.33):
                x = W // 2 - 230 + int(460 * frac)
                pg.draw.line(surf, WHITE, (x, 48), (x, 68))
        # training lesson
        if game.variant == "training" and game.lesson < len(LESSONS):
            name, how, goal = LESSONS[game.lesson]
            self.panel(surf, (W // 2 - 360, 124, 720, 98), GREEN)
            self.text(surf, f"LESSON {game.lesson + 1:02d} / {len(LESSONS)}   {name}", (W // 2, 134), GREEN, self.h3,
                      "midtop")
            self.text(surf, how, (W // 2, 164), WHITE, self.body, "midtop")
            self.text(surf, "▸ " + goal, (W // 2, 192), MUTED, self.small, "midtop")
        # messages
        y = 236 if game.variant == "training" else 96
        for text, c, life in self.messages:
            img = self.h3.render(self.clean(text, self.h3), True, c)
            img.set_alpha(int(255 * min(1, life / 0.4)))
            surf.blit(img, img.get_rect(midtop=(W // 2, y)))
            y += 30
        if hint and show_hint_strip:
            w = self.small.size(self.clean(hint, self.small))[0] + 40
            self.panel(surf, (W // 2 - w // 2, H - 58, w, 36), AMBER, corners=False)
            self.text(surf, hint, (W // 2, H - 40), AMBER, self.small, "center")

    def _weapon_panel(self, surf, game):
        x0, y0 = 20, H - 104
        self.panel(surf, (x0, y0, 330, 86))
        slot = game.weapon
        col = WEAPON_COLORS[slot]
        gun = self.art.guns[slot]
        big = pg.transform.scale(gun, (gun.get_width() * 3, gun.get_height() * 3))
        surf.blit(big, big.get_rect(center=(x0 + 52, y0 + 34)))
        self.text(surf, WEAPONS[slot].name, (x0 + 104, y0 + 12), col, self.h3)
        ammo = game.ammo[slot]
        ammo_txt = "∞" if slot == 0 else f"{ammo:02d}"
        self.text(surf, ammo_txt, (x0 + 104, y0 + 34), WHITE if ammo != 0 else RED, self.h2)
        if slot:
            self.text(surf, f"/ {game.ammo_cap[slot]}", (x0 + 160, y0 + 42), MUTED, self.small)
        for i in range(5):
            r = pg.Rect(x0 + 104 + i * 42, y0 + 64, 36, 14)
            owned = game.owned[i]
            c = WEAPON_COLORS[i] if owned else (40, 50, 70)
            pg.draw.rect(surf, c if i == slot else (12, 18, 32), r)
            pg.draw.rect(surf, c, r, 1)
            self.text(surf, str(i + 1), r.center, INK if i == slot else c, self.tiny, "center")

    def _objective(self, surf, game):
        r = pg.Rect(W - 376, 18, 356, 92)
        self.panel(surf, r)
        secs = game.frames // 30
        if game.variant == "horde":
            h = game.horde
            title = f"WAVE {h.wave:02d}"
            alive = sum(1 for e in game.enemies if e.kind != "nest")
            if h.offer:
                line = "CHOOSE AN UPGRADE"
            elif h.active:
                line = f"{alive + len(h.queue):02d} HOSTILES"
            else:
                line = f"NEXT WAVE IN {h.break_t / 30:.1f}s"
            self.text(surf, title, (r.x + 16, r.y + 12), AMBER, self.h2)
            self.text(surf, line, (r.x + 16, r.y + 46), WHITE, self.small)
            self.text(surf, f"CLEARED {h.cleared}   KILLS {game.kills}", (r.x + 16, r.y + 68), MUTED, self.small)
            return
        if game.variant == "training":
            self.text(surf, "TRAINING DECK", (r.x + 16, r.y + 12), GREEN, self.h3)
            self.text(surf, "Nothing here can hurt you.", (r.x + 16, r.y + 44), MUTED, self.small)
            return
        names = ("SECTOR 1", "SECTOR 2", "SECTOR 3", "FINAL")
        self.text(surf, f"{names[min(game.sector, 3)]} · {game.map.title}", (r.x + 16, r.y + 12), CYAN, self.h3)
        if game.sector == 3 and not game.boss_dead:
            goal = "Destroy the Core Warden"
        elif game.sector == 3:
            goal = "Reach the exit lift"
        else:
            goal = "Find the exit lift"
        self.text(surf, "▸ " + goal, (r.x + 16, r.y + 42), WHITE, self.small)
        self.text(surf, f"{secs // 60:02d}:{secs % 60:02d}   KILLS {game.kills}   SECRETS {game.secrets}",
                  (r.x + 16, r.y + 66), MUTED, self.small)

    # ------------------------------------------------------------ overlays
    def shade(self, surf, alpha=200):
        s = pg.Surface((W, H), pg.SRCALPHA)
        s.fill((3, 6, 16, alpha))
        surf.blit(s, (0, 0))

    def title(self, surf, selection, difficulty, mouse, records):
        t = self.time
        self.shade(surf, 150)
        y = 70
        self.text(surf, "AN ABUSE REMAKE EXPANSION", (90, y), MUTED, self.small)
        self.text(surf, "NEON", (84, y + 24), WHITE, self.title_font, glow=True)
        self.text(surf, "PROTOCOL", (84, y + 116), CYAN, self.title_font, glow=True)
        pg.draw.line(surf, MAGENTA, (90, y + 216), (90 + 380 + int(math.sin(t * 2) * 40), y + 216), 2)
        self.text(surf, "Breach the facility. Burn the hive. Kill the Warden.", (90, y + 232), WHITE, self.body)
        entries = [("campaign", "CAMPAIGN", "Four sectors · vertical mazes · a boss"),
                   ("horde", "HORDE", "Endless waves · pick an upgrade each wave"),
                   ("training", "TRAINING", "Learn every move by doing it (start here)"),
                   ("manual", "FIELD MANUAL", "Controls, weapons, hostiles, systems"),
                   ("legacy", "CLASSIC / REMASTERED", "The original Abuse Level 1")]
        buttons = []
        for i, (key, name, desc) in enumerate(entries):
            r = pg.Rect(W - 520, 120 + i * 92, 440, 78)
            hot = selection == i or r.collidepoint(mouse)
            self.panel(surf, r, CYAN if hot else (60, 90, 120),
                       fill=(10, 30, 50, 220) if hot else (6, 12, 26, 190))
            self.text(surf, name, (r.x + 22, r.y + 14), WHITE if hot else MUTED, self.h2)
            self.text(surf, desc, (r.x + 22, r.y + 48), CYAN if hot else MUTED, self.small)
            if hot:
                pg.draw.rect(surf, CYAN, (r.x + 6, r.y + 14, 4, r.h - 28))
            buttons.append((key, r))
        self.text(surf, f"DIFFICULTY  ◂ {difficulty.upper()} ▸   (D)", (90, 380), AMBER, self.h3)
        best = records.get("horde")
        if best:
            self.text(surf, f"BEST HORDE  wave {best['cleared']} · {best['kills']} kills", (90, 414), MUTED,
                      self.small)
        if records.get("campaign"):
            secs = records["campaign"]["frames"] // 30
            self.text(surf, f"BEST CAMPAIGN  {secs // 60}:{secs % 60:02d}", (90, 438), MUTED, self.small)
        self.text(surf, "↑ ↓ + ENTER, or click   ·   F1 manual   ·   ESC quit", (90, 478), MUTED, self.small)
        self.text(surf, "Art: Luis Zuno (Ansimuz)  ·  weapon art: Reactorcore, reactorcoregames.com (CC-BY 4.0)  ·  "
                        "sound: Kenney, rubberduck", (W // 2, H - 44), (90, 110, 140), self.tiny, "center")
        self.text(surf, "Music: vitalezzz, cinameng, SRG774, MintoDog  ·  fonts: Orbitron, Share Tech Mono (OFL)  ·  "
                        "Abuse (1996) Crack dot Com", (W // 2, H - 24), (90, 110, 140), self.tiny, "center")
        return buttons

    def center(self, surf, title, lines, color=CYAN):
        self.shade(surf, 190)
        self.panel(surf, (W // 2 - 380, H // 2 - 170, 760, 340), color)
        self.text(surf, title, (W // 2, H // 2 - 130), color, self.h1, "midtop", glow=True)
        for i, line in enumerate(lines):
            c = WHITE if i == 0 else MUTED
            self.text(surf, line, (W // 2, H // 2 - 50 + i * 34), c, self.body, "midtop")

    def upgrade_cards(self, surf, offer, mouse):
        self.shade(surf, 170)
        self.text(surf, "WAVE CLEARED", (W // 2, 140), AMBER, self.h1, "midtop", glow=True)
        self.text(surf, "Choose one upgrade  ·  1 / 2  or click", (W // 2, 200), WHITE, self.body, "midtop")
        buttons = []
        for i, name in enumerate(offer):
            r = pg.Rect(W // 2 - 420 + i * 440, 260, 400, 220)
            hot = r.collidepoint(mouse)
            self.panel(surf, r, AMBER if hot else CYAN, fill=(14, 26, 44, 230))
            title, desc = UPGRADES[name]
            self.text(surf, f"{i + 1}", (r.x + 24, r.y + 20), AMBER, self.h1)
            self.text(surf, title, (r.x + 24, r.y + 84), WHITE, self.h2)
            self._wrap(surf, desc, (r.x + 24, r.y + 124), r.w - 48, MUTED, self.body)
            buttons.append((i, r))
        return buttons

    def _wrap(self, surf, text, pos, width, color, font, line_h=None):
        words = text.split()
        line = ""
        x, y = pos
        line_h = line_h or font.get_linesize()
        for w in words:
            test = (line + " " + w).strip()
            if font.size(test)[0] > width and line:
                self.text(surf, line, (x, y), color, font)
                y += line_h
                line = w
            else:
                line = test
        if line:
            self.text(surf, line, (x, y), color, font)
            y += line_h
        return y

    def manual(self, surf, page):
        self.shade(surf, 235)
        self.text(surf, "FIELD MANUAL", (80, 40), CYAN, self.h1, glow=True)
        for i, name in enumerate(MANUAL_PAGES):
            r = pg.Rect(80 + i * 200, 104, 186, 34)
            self.panel(surf, r, CYAN if i == page else (50, 70, 100), corners=False)
            self.text(surf, f"{i + 1} {name}", r.center, WHITE if i == page else MUTED, self.h3, "center")
        y = 170
        if page == 0:
            for label, keys in CONTROLS:
                self.text(surf, label, (100, y), CYAN, self.h3)
                self.text(surf, keys, (400, y - 2), WHITE, self.body)
                y += 33
            self.text(surf, GAMEPAD, (100, y + 10), MUTED, self.small)
        elif page == 1:
            for i, spec in enumerate(WEAPONS):
                gun = self.art.guns[i]
                big = pg.transform.scale(gun, (gun.get_width() * 3, gun.get_height() * 3))
                surf.blit(big, big.get_rect(center=(160, y + 26)))
                self.text(surf, f"{i + 1}  {spec.name}", (260, y), WEAPON_COLORS[i], self.h3)
                self.text(surf, WEAPON_NOTES[i], (260, y + 28), WHITE, self.body)
                ammo = "unlimited" if spec.ammo_max < 0 else f"holds {spec.ammo_max}"
                self.text(surf, f"damage {spec.damage} · {ammo}", (260, y + 54), MUTED, self.small)
                y += 92
        elif page == 2:
            art = self.art
            icons = [art.crawler_walk[0], art.stinger[0], art.turret[0], art.strider[0], art.drone[0], None]
            for i, (name, note) in enumerate(ENEMY_NOTES):
                col, row = i % 2, i // 2
                x, yy = 90 + col * 580, y + row * 160
                img = icons[i]
                if img is not None:
                    big = pg.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))
                    surf.blit(big, big.get_rect(center=(x + 70, yy + 56)))
                else:
                    pg.draw.ellipse(surf, (90, 160, 60), (x + 30, yy + 36, 80, 40), 3)
                self.text(surf, name, (x + 150, yy + 6), MAGENTA, self.h3)
                self._wrap(surf, note, (x + 150, yy + 34), 400, WHITE, self.small)
        else:
            for name, note in SYSTEM_NOTES:
                self.text(surf, name, (100, y), AMBER, self.h3)
                self._wrap(surf, note, (400, y - 2), 780, WHITE, self.body)
                y += 58
        self.text(surf, "← → or 1-4 change page   ·   ESC / F1 close", (W // 2, H - 40), MUTED, self.small, "center")

    def automap(self, surf, game, explored):
        if explored is None:
            return
        self.shade(surf, 210)
        m = game.map
        scale = max(2, min(1100 // m.width, 560 // m.height))
        ox = (W - m.width * scale) // 2
        oy = (H - m.height * scale) // 2 + 20
        self.text(surf, f"MAP · {m.title}", (W // 2, oy - 44), CYAN, self.h2, "midtop")
        cells = game.grid.cells
        w = m.width
        img = pg.Surface((m.width, m.height))
        img.fill((6, 10, 20))
        px = pg.PixelArray(img)
        for ty in range(m.height):
            row = explored[ty]
            for tx in range(m.width):
                if not row[tx]:
                    continue
                c = cells[ty * w + tx]
                px[tx, ty] = (60, 80, 120) if c in (1, 5, 6) else (0, 200, 220) if c == 2 else \
                    (200, 170, 60) if c == 3 else (16, 26, 44)
        del px
        surf.blit(pg.transform.scale(img, (m.width * scale, m.height * scale)), (ox, oy))
        p = game.player
        blink = int(self.time * 4) % 2
        pg.draw.circle(surf, WHITE if blink else MAGENTA, (ox + p.cx * scale // 16, oy + p.cy * scale // 16), 4)
        for c in game.consoles:
            if explored[c.y // 16 - 1, c.x // 16]:
                pg.draw.rect(surf, GREEN, (ox + c.x * scale // 16 - 3, oy + c.y * scale // 16 - 8, 6, 6))
        if game.exit and explored[game.exit[1] // 16 - 1, game.exit[0] // 16]:
            ex, ey = game.exit
            pg.draw.rect(surf, AMBER, (ox + ex * scale // 16 - 4, oy + ey * scale // 16 - 10, 8, 8), 2)
        self.text(surf, "TAB close  ·  white: you  ·  green: save console  ·  amber: exit", (W // 2, H - 36),
                  MUTED, self.small, "center")
