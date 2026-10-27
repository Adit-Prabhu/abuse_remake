"""Remastered's heads-up display, in the original game's own interface art (``ui.py``).

Every element says what it is:
- bottom left: HEALTH (a heart, a meter and "health/limit"), and the DASH meter with its key;
- bottom centre: the weapons you carry, as the original status bar's icons, each with its key and
  ammunition, the one in your hands lit and framed;
- bottom right: TIME, KILLS and, in the campaign, SECRETS;
- top right: the power you carry, its icon, how to use it and, in Horde, when it ends;
- top left in Horde: WAVE, ENEMIES LEFT or the countdown to the next wave, SCORE and COMBO;
- top centre: messages, the boss's health, and big prompts when you get a power.
Classic mode keeps the original-style HUD in ``hud.py``. Presentation only.
"""

from __future__ import annotations

import math

import pygame

from ..engine.behaviors.player import FAST_POWER, FLY_POWER, HEALTH_POWER, SNEAKY_POWER
from ..engine.remastered import DEV_GUNS
from . import ui
from .ui import AMBER, CYAN, DIM, GREEN, ORANGE, RED, TEXT

POWERS = {
    FAST_POWER: ("SPEED", "fast_image", "TO RUN FAST"),
    FLY_POWER: ("FLIGHT", "fly_image", "TO FLY"),
    SNEAKY_POWER: ("INVISIBILITY", "sneaky_image", "TO VANISH"),
    HEALTH_POWER: ("ULTRA HEALTH", "b_check_image", None),
}
# the upgrade cards: name, icon (a file and image, or a sprite type), what it does, how to use it
CARDS = {
    "speed": ("SPEED", ("art/misc.spe", "fast_image"), "Run and jump at double speed.", True),
    "flight": ("FLIGHT", ("art/misc.spe", "fly_image"), "Rise into the air; steer left and right.", True),
    "ultra_health": ("ULTRA HEALTH", ("art/misc.spe", "b_check_image"),
                     "Health limit 200, and a big heal now.", False),
    "medkit": ("MEDKIT", ("type", "HEALTH"), "Refill your health to full.", False),
    "ammo": ("AMMO CRATE", ("type", "GRENADE_ICON10"), "+10 grenades and +5 firebombs, with the launchers.",
             False),
    "rockets": ("ROCKETS", ("type", "ROCKET_ICON5"), "The rocket launcher and +10 rockets.", False),
    "dash": ("QUICK DASH", ("type", "DARNEL"), "Your dash recharges faster.", False),
}
POWER_CARDS = {"speed", "flight", "ultra_health"}
# pickups by the start of their type name: Horde's drops, and the ammunition ants drop (ant.lsp)
DROP_NAMES = (("HEALTH", "HEALTH"), ("MBULLET_ICON", "LASER AMMO"), ("GRENADE_ICON", "GRENADES"),
              ("ROCKET_ICON", "ROCKETS"), ("FBOMB_ICON", "FIREBOMBS"), ("PLASMA_ICON", "PLASMA"),
              ("LSABER_ICON", "SABER"), ("DFRIS_ICON", "FRISBEES"))


def drop_name(type_name: str) -> str | None:
    return next((label for prefix, label in DROP_NAMES if type_name.startswith(prefix)), None)


def power_keys() -> list:
    return [("key", "SHIFT"), "OR", ("key", "RIGHT MOUSE")]


class ModernHud:
    def __init__(self, sprites, unit: int):
        self.t = ui.Theme(sprites, unit)
        self.u = self.t.u
        self.card_rects: list[pygame.Rect] = []
        self.banner: dict | None = None  # a big prompt: {"power": n, "frames": left}
        self.frame = 0

    # --- the status strip ------------------------------------------------------------------------
    def draw(self, screen, app) -> None:
        self.frame += 1
        game = app.game
        t, u = self.t, self.u
        w, h = screen.get_size()
        p, v = game.player, game.view
        horde = app.horde
        # health
        cap = 200 if p.lvars.get("special_power") == HEALTH_POWER else 100
        hp = max(0, min(cap, p.hp))
        box = pygame.Rect(4 * u, h - 27 * u, 118 * u, 23 * u)
        t.plate(screen, box)
        heart = t.figure(game.world, "HEALTH")
        if heart is not None:
            screen.blit(heart, (box.left + 4 * u, box.top + 6 * u))
        t.text(screen, "HEALTH", (box.left + 23 * u, box.top + 3 * u), DIM)
        # over the limit (ultra health's extra, kept after another power replaced it): the number alone
        t.text(screen, f"{p.hp}/{cap}" if p.hp <= cap else str(p.hp), (box.right - 4 * u, box.top + 3 * u), TEXT,
               align="right")
        color = GREEN if hp > 40 else (AMBER if hp > 15 else RED)
        t.bar(screen, pygame.Rect(box.left + 23 * u, box.top + 12 * u, 91 * u, 7 * u), hp / cap, color)
        x = box.right + 4 * u
        # the dash (Remastered's)
        if game.remastered is not None:
            rs = game.remastered.state
            most = rs.get("cooldown_max", 18)
            ready = rs["cooldown"] == 0
            box = pygame.Rect(x, h - 27 * u, 54 * u, 23 * u)
            t.plate(screen, box)
            t.text(screen, "DASH", (box.left + 4 * u, box.top + 3 * u), DIM)
            t.key(screen, "F", (box.right - 13 * u, box.top + 2 * u))
            t.bar(screen, pygame.Rect(box.left + 4 * u, box.top + 13 * u, 46 * u, 6 * u),
                  1.0 - rs["cooldown"] / max(1, most), CYAN if ready else ui.GREY[0])
            x = box.right + 4 * u
        # weapons (all four endless in dev mode with unlimited ammo)
        dev = game.remastered.dev if game.remastered is not None else None
        x = self._weapons(screen, v, x + 2 * u, h, endless_guns=DEV_GUNS if dev and dev["ammo"] else 0)
        # time and counts
        s = app.stats
        secs = s.get("ticks", 0) // 15
        kills = game.horde.state["kills"] if horde else s.get("kills", 0)
        line = f"KILLS {kills}" if horde else f"KILLS {kills}  SECRETS {s.get('secrets', 0)}"
        bw = max(76 * u, t.measure(line)[0] + 8 * u)
        box = pygame.Rect(w - bw - 4 * u, h - 27 * u, bw, 23 * u)
        t.plate(screen, box)
        t.text(screen, "TIME", (box.left + 4 * u, box.top + 3 * u), DIM)
        t.text(screen, f"{secs // 60}:{secs % 60:02d}", (box.right - 4 * u, box.top + 3 * u), TEXT, align="right")
        t.text(screen, line, (box.left + 4 * u, box.top + 13 * u), TEXT)
        self._power(screen, app)
        if horde:
            self._horde(screen, app)
        if dev is not None:  # above the health panel
            dev_badge(t, screen, (4 * u, h - 39 * u - t.measure("DEV MODE")[1]), hint=True)
        if app.state == "play":  # prompts belong to play, not to the screens drawn over it
            self._messages(screen, app)
            self._help(screen, app)

    def _weapons(self, screen, v, x, h, endless_guns: int = 0) -> int:
        t, u = self.t, self.u
        for i, ammo in enumerate(v.weapons[:7]):  # the status bar has icons for the seven weapons
            if ammo == -1:
                continue
            sel = i == v.current_weapon
            img = t.icon("art/statbar.spe", f"{'b' if sel else 'd'}weap{i + 1:04d}.pcx")
            slot = pygame.Rect(x, h - 27 * u, 46 * u, 23 * u)
            t.plate(screen, slot, alpha=150)
            if img is not None:
                screen.blit(img, (slot.left + 2 * u, slot.top + u))
            if sel:
                pygame.draw.rect(screen, AMBER, slot, u)
            endless = (i == 0 and ammo == 0) or i < endless_guns  # the laser never runs out
            label, size = (chr(236), "big") if endless else (str(ammo), "small")
            t.text(screen, str(i + 1), (slot.left + 3 * u, slot.top + 2 * u), AMBER if sel else DIM)
            aw, ah = t.measure(label, size)
            badge = pygame.Rect(slot.right - aw - 5 * u, slot.bottom - ah - 4 * u, aw + 4 * u, ah + 3 * u)
            pygame.draw.rect(screen, ui.DEEP[2], badge)
            t.text(screen, label, (badge.right - 2 * u, badge.top + 2 * u), TEXT if sel else DIM, size=size,
                   align="right", shadow=False)
            x = slot.right + 2 * u
        return x

    # --- the power slot --------------------------------------------------------------------------
    def _power(self, screen, app) -> None:
        t, u = self.t, self.u
        w, _ = screen.get_size()
        p = app.game.player
        power = p.lvars.get("special_power", 0)
        if power not in POWERS:
            return
        name, image, verb = POWERS[power]
        horde_ends = None
        if app.horde:
            st = app.game.horde.state
            if st.get("card_power") == power:
                horde_ends = st["wave"] + (1 if st["break"] else 0)
        rows = 2 + (verb is not None) + (horde_ends is not None)
        box = pygame.Rect(w - 132 * u, 4 * u, 128 * u, (8 + 10 * rows) * u)
        unused = verb is not None and not app.power_used
        pulse = unused and (self.frame // 20) % 2 == 0
        t.panel(screen, box, accent=AMBER if pulse else None, bolts=False)
        self.socket(screen, t.icon("art/misc.spe", image), (box.left + 5 * u, box.top + 5 * u), 21 * u)
        tx = box.left + 31 * u
        y = box.top + 6 * u
        t.text(screen, "POWER", (tx, y), DIM)
        t.text(screen, name, (tx + 30 * u, y), AMBER)
        y += 11 * u
        if verb is not None:
            t.keys_line(screen, ["HOLD", ("key", "SHIFT"), "/", ("key", "RMB")], (tx, y + u))
            y += 12 * u
        else:
            t.text(screen, "ALWAYS ON", (tx, y), GREEN)
            y += 10 * u
        if horde_ends is not None:
            t.text(screen, f"ENDS WITH WAVE {horde_ends}", (tx, y), DIM)

    # --- Horde -----------------------------------------------------------------------------------
    def _horde(self, screen, app) -> None:
        from ..engine.horde import COMBO_TICKS, MAX_COMBO

        t, u = self.t, self.u
        w, _ = screen.get_size()
        st = app.game.horde.state
        box = pygame.Rect(4 * u, 4 * u, 112 * u, 45 * u)
        t.panel(screen, box, bolts=False)
        x, y = box.left + 6 * u, box.top + 6 * u
        t.text(screen, "WAVE", (x, y + u), DIM)
        t.text(screen, str(max(1, st["wave"] if not st["break"] else st["wave"] + 1)), (x + 26 * u, y),
               AMBER, size="big")
        y += 11 * u
        if st["cards"]:
            t.text(screen, "PICK AN UPGRADE", (x, y), ORANGE)
        elif st["break"]:
            secs = math.ceil(st["spawn_in"] / 15)
            t.text(screen, f"STARTS IN {secs}", (x, y), ORANGE if (self.frame // 15) % 2 else AMBER)
        else:
            left = len(st["alive"]) + len(st["to_spawn"])
            t.text(screen, f"ENEMIES LEFT {left}", (x, y), TEXT)
        y += 10 * u
        t.text(screen, f"SCORE {st['score']}", (x, y), AMBER)
        y += 10 * u
        live = st["combo"] > 1 and st["tick"] - st["last_kill"] <= COMBO_TICKS
        if live:
            t.text(screen, f"COMBO x{st['combo']}", (x, y), ORANGE if st["combo"] >= MAX_COMBO else TEXT)
            left = 1.0 - (st["tick"] - st["last_kill"]) / COMBO_TICKS
            t.bar(screen, pygame.Rect(x + 48 * u, y, 50 * u, 6 * u), left, ORANGE)
        else:
            t.text(screen, "COMBO -", (x, y), DIM)
        # the boss
        health, most = app.game.horde.boss_health()
        if st["boss"] is not None and most:
            from ..engine.horde import BOSS_LIFE

            bw = 180 * u
            box = pygame.Rect((w - bw) // 2, 4 * u, bw, 20 * u)
            t.plate(screen, box, alpha=210)
            lives = st["boss_lives"]
            t.text(screen, "JUGGERNAUT BOSS", (box.left + 4 * u, box.top + 2 * u), RED)
            t.text(screen, f"LIVES {lives + 1}", (box.right - 4 * u, box.top + 2 * u), TEXT, align="right")
            t.bar(screen, pygame.Rect(box.left + 4 * u, box.top + 11 * u, bw - 8 * u, 6 * u),
                  health / most, RED)
            for k in range(1, most // BOSS_LIFE):  # a notch between lives
                nx = box.left + 4 * u + (bw - 8 * u) * k * BOSS_LIFE // most
                pygame.draw.rect(screen, ui.DEEP[2], (nx, box.top + 11 * u, u, 6 * u))

    # --- messages and help -----------------------------------------------------------------------
    def _messages(self, screen, app) -> None:
        t, u = self.t, self.u
        w, _ = screen.get_size()
        hud = app.hud
        boss = app.horde and app.game.horde.state["boss"] is not None
        y = (28 if boss else 4) * u
        if app._cards_up():
            return  # the cards say it all, over a dimmed game
        if app.horde and app.game.horde.state["break"]:
            self._drop_labels(screen, app)
        hud.messages = hud.messages[-3:]  # the newest three; older ones have been read
        room = w - 2 * 140 * u  # between the panels at the top left and right
        for m in hud.messages:
            lines = t.wrap(m[0].upper(), room)
            th = t.measure("X")[1]
            tw = max(t.measure(line)[0] for line in lines)
            box = pygame.Rect(w // 2 - tw // 2 - 6 * u, y, tw + 12 * u, len(lines) * (th + 3 * u) + 3 * u)
            t.plate(screen, box, alpha=190)
            for k, line in enumerate(lines):
                t.text(screen, line, (w // 2, y + 3 * u + k * (th + 3 * u)), AMBER if m[0].isupper() else TEXT,
                       align="center")
            y = box.bottom + 3 * u
            m[1] -= 1
        hud.messages = [m for m in hud.messages if m[1] > 0]
        if self.banner is not None:
            self._banner(screen, app)

    def _drop_labels(self, screen, app) -> None:
        """Between Horde waves, name each pickup lying in the arena."""
        t, u = self.t, self.u
        xoff, yoff = app.renderer.last_cam
        w = screen.get_width()
        shown, boxes = set(), []
        for o in app.game.world.objects:
            name = drop_name(o.ctype.name)
            if name is None or o.deleted or (name, o.x // 30, o.y // 30) in shown:
                continue
            shown.add((name, o.x // 30, o.y // 30))  # one label for a pile of the same thing
            tw, th = t.measure(name)
            sx = int((o.x - xoff) * app.scale)
            if not tw // 2 + 4 * u <= sx <= w - tw // 2 - 4 * u:
                continue  # at or past the screen's edge: a label only ever sits right above its pickup
            sy = int((o.y - yoff) * app.scale) - 26 * u
            box = pygame.Rect(sx - tw // 2 - 3 * u, sy - 2 * u, tw + 6 * u, th + 4 * u)
            while any(box.colliderect(b) for b in boxes):  # neighbours stack instead of overlapping
                box.move_ip(0, -(th + 6 * u))
                sy -= th + 6 * u
            boxes.append(box)
            t.plate(screen, box, alpha=200)
            t.text(screen, name, (sx, sy), GREEN if name == "HEALTH" else TEXT, align="center", shadow=False)

    def _help(self, screen, app) -> None:
        """The training level's help line (game::show_help), above the status strip."""
        hud = app.hud
        if hud.help_frames <= 0 or not hud.help_text:
            return
        t, u = self.t, self.u
        w, h = screen.get_size()
        lines = t.wrap(hud.help_text, w - 60 * u)
        th = t.measure("X")[1]
        box_h = len(lines) * (th + 3 * u) + 8 * u
        box = pygame.Rect(20 * u, h - 33 * u - box_h, w - 40 * u, box_h)
        t.plate(screen, box, alpha=210)
        for i, line in enumerate(lines):
            t.text(screen, line, (w // 2, box.top + 5 * u + i * (th + 3 * u)), (255, 236, 170), align="center")
        hud.help_frames -= 1

    def socket(self, screen, img, pos, size: int) -> None:
        """A sunken square behind an icon, so dark sprites read on dark panels."""
        u = self.u
        r = pygame.Rect(pos[0], pos[1], size, size)
        pygame.draw.rect(screen, ui.GREY[1], r)
        pygame.draw.rect(screen, ui.DEEP[2], (r.left, r.top, r.width, u))
        pygame.draw.rect(screen, ui.DEEP[2], (r.left, r.top, u, r.height))
        pygame.draw.rect(screen, ui.GREY[0], (r.left, r.bottom - u, r.width, u))
        pygame.draw.rect(screen, ui.GREY[0], (r.right - u, r.top, u, r.height))
        if img is not None:
            screen.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))

    def player_icon(self, world, scale: int = 1) -> pygame.Surface | None:
        """The player running, both halves, put together as the renderer does (top_draw)."""
        key = ("player", scale)
        cache = self.t._icons
        if key not in cache:
            img = None
            bot_t, top_t = world.types.get("DARNEL"), world.types.get("MGUN_TOP")
            if bot_t is not None and top_t is not None and self.t.sprites:
                bf, tf = bot_t.sequences["running"][6], top_t.sequences["stopped"][0]
                bot, _ = self.t.sprites.figure(bf)
                top, _ = self.t.sprites.figure(tf)
                ty = 29 - bf.height - tf.height + 1  # the top half's top, from the feet
                by = -bf.height + 1
                left = min(-bf.xcfg, -tf.xcfg)
                height = max(0, by + bf.height) - min(by, ty)
                width = max(bf.width - bf.xcfg, tf.width - tf.xcfg) - left
                img = pygame.Surface((width, height), pygame.SRCALPHA)
                y0 = -min(by, ty)
                img.blit(bot, (-bf.xcfg - left, by + y0))
                img.blit(top, (-tf.xcfg - left, ty + y0))
                s = scale * self.u
                img = pygame.transform.scale(img, (width * s, height * s))
            cache[key] = img
        return cache[key]

    def show_power(self, power: int) -> None:
        self.banner = {"power": power, "frames": 200}

    def _banner(self, screen, app) -> None:
        """A big prompt when you get a power: what it is, and the keys that use it."""
        b = self.banner
        b["frames"] -= 1
        if b["frames"] <= 0 or b["power"] not in POWERS:
            self.banner = None
            return
        t, u = self.t, self.u
        w, h = screen.get_size()
        name, image, verb = POWERS[b["power"]]
        box = pygame.Rect(w // 2 - 120 * u, h // 2 - 70 * u, 240 * u, 44 * u)
        t.panel(screen, box, accent=AMBER if (b["frames"] // 12) % 2 else None)
        img = t.icon("art/misc.spe", image)
        if img is not None:
            screen.blit(img, (box.left + 8 * u, box.top + (box.height - img.get_height()) // 2))
        cx = box.left + 30 * u + (box.width - 30 * u) // 2
        t.text(screen, f"{name}!", (cx, box.top + 8 * u), AMBER, size="big", align="center")
        if verb is None:
            t.text(screen, "YOUR HEALTH LIMIT IS NOW 200", (cx, box.top + 24 * u), TEXT, align="center")
        else:
            t.keys_line(screen, ["HOLD", *power_keys(), verb], (cx, box.top + 25 * u), align="center")

    # --- the upgrade cards -----------------------------------------------------------------------
    def draw_cards(self, screen, app) -> None:
        t, u = self.t, self.u
        w, h = screen.get_size()
        st = app.game.horde.state
        cards = st["cards"]
        self.card_rects = []
        if not cards:
            return
        t.dim(screen, 150)
        info = app.last_clear or {}
        head = pygame.Rect(w // 2 - 150 * u, 12 * u, 300 * u, 46 * u)
        t.panel(screen, head)
        t.text(screen, f"WAVE {st['cleared']} CLEARED", (w // 2, head.top + 7 * u), AMBER, size="big", scale=2,
               align="center")
        bonus = f"+{info.get('bonus', 0)} WAVE BONUS"
        if info.get("clean"):
            bonus += f"   +{info['clean']} NO-DAMAGE BONUS"
        t.text(screen, bonus, (w // 2, head.top + 27 * u), TEXT, align="center")
        t.text(screen, "CHOOSE ONE UPGRADE", (w // 2, head.top + 37 * u), ORANGE, align="center")
        cw, ch, gap = 136 * u, 122 * u, 10 * u
        x0 = (w - 3 * cw - 2 * gap) // 2
        y0 = head.bottom + 10 * u
        lasts = st["wave"] + 1
        for i, card in enumerate(cards):
            name, icon, desc, held = CARDS[card]
            r = pygame.Rect(x0 + i * (cw + gap), y0, cw, ch)
            self.card_rects.append(r)
            focus = i == app.card_focus
            t.panel(screen, r, accent=AMBER if focus else None)
            t.key(screen, str(i + 1), (r.left + 6 * u, r.top + 6 * u), AMBER if focus else TEXT)
            if card == "dash":
                img = self.player_icon(app.game.world)
            elif icon[0] == "type":
                img = t.figure(app.game.world, icon[1], "stopped", 2 if icon[1] != "ROCKET_ICON5" else 1)
            else:
                img = t.icon(icon[0], icon[1], 2)
            sock = 46 * u
            self.socket(screen, None, (r.centerx - sock // 2, r.top + 7 * u), sock)
            if img is not None:
                ix = r.centerx - img.get_width() // 2
                iy = r.top + 7 * u + sock // 2 - img.get_height() // 2
                if card == "dash":  # afterimages behind the runner, as the dash draws them
                    ghost = img.copy()
                    ghost.fill((120, 220, 255, 90), special_flags=pygame.BLEND_RGBA_MULT)
                    screen.blit(ghost, (ix - 10 * u, iy))
                    screen.blit(ghost, (ix - 5 * u, iy))
                screen.blit(img, (ix, iy))
            t.text(screen, name, (r.centerx, r.top + 58 * u), AMBER if focus else TEXT, size="big", align="center")
            y = r.top + 70 * u
            for line in t.wrap(desc, cw - 14 * u):
                t.text(screen, line, (r.centerx, y), TEXT, align="center")
                y += 9 * u
            if held:
                t.text(screen, "HOLD", (r.centerx, y + 2 * u), DIM, align="center")
                t.keys_line(screen, [("key", "SHIFT"), "OR", ("key", "RMB")], (r.centerx, y + 12 * u), align="center")
                y += 24 * u
            if card in POWER_CARDS:
                t.text(screen, f"UNTIL WAVE {lasts} ENDS", (r.centerx, r.bottom - 12 * u), DIM, align="center")
            elif card == "dash":
                rs = app.game.remastered.state if app.game.remastered else {}
                now = rs.get("cooldown_max", 18)
                t.text(screen, f"RECHARGE {now / 15:.1f}S \u2192 {max(10, now - 4) / 15:.1f}S",
                       (r.centerx, r.bottom - 12 * u), DIM, align="center")
            else:
                t.text(screen, "INSTANT", (r.centerx, r.bottom - 12 * u), DIM, align="center")
        foot = pygame.Rect(w // 2 - 170 * u, y0 + ch + 10 * u, 340 * u, 30 * u)
        t.plate(screen, foot, alpha=210)
        t.keys_line(screen, ["PRESS", ("key", "1"), ("key", "2"), ("key", "3"), "OR CLICK A CARD.",
                             ("key", "\u2190"), ("key", "\u2192"), ("key", "ENTER"), "ALSO WORK"],
                    (w // 2, foot.top + 6 * u), align="center")
        heart = t.figure(app.game.world, "HEALTH")
        line = "HEALTH AND AMMO DROPPED NEAR YOU: WALK OVER THEM"
        tw, _ = t.measure(line)
        if heart is not None:
            screen.blit(heart, (w // 2 - tw // 2 - 20 * u, foot.top + 17 * u))
        t.text(screen, line, (w // 2, foot.top + 19 * u), TEXT, align="center")


def dev_badge(t: ui.Theme, screen, pos, hint: bool = False) -> pygame.Rect:
    """DEV MODE in red, always on screen in developer test mode (devmode.py), so no screenshot or
    recording of it passes for real play; ``hint`` adds the key that opens its menu."""
    u = t.u
    lw, lh = t.measure("DEV MODE")
    tail = t.measure("MENU")[0] + t.measure("TAB")[0] + 16 * u if hint else 0
    box = pygame.Rect(pos[0], pos[1], lw + 8 * u + tail, lh + 9 * u)
    pygame.draw.rect(screen, (90, 14, 10), box)
    pygame.draw.rect(screen, RED, box, u)
    t.text(screen, "DEV MODE", (box.left + 4 * u, box.top + 4 * u), TEXT)
    if hint:
        k = t.key(screen, "TAB", (box.left + lw + 10 * u, box.top + 2 * u))
        t.text(screen, "MENU", (k.right + 3 * u, box.top + 4 * u), DIM)
    return box
