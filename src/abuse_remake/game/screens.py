"""Full-screen panels in the original game's interface art (``ui.py``): the title menu, Horde's
briefing, the controls and HUD legend, and Remastered's pause, death, level-complete and Horde-over
screens. Classic mode keeps its plain text screens for pause, death and the end of the level.

The title is a menu. Up and down (or W and S, or the mouse) pick a line; left and right (or a
click on the arrows) change its setting; Enter or a click starts it. In Remastered, PLAY CAMPAIGN
and HORDE each open a list of their own (the levels, or the arenas), and Esc goes back, so a level
is never mistaken for an arena. The letter keys of the old title still work on its main page:
M mode, D difficulty, H Horde, A arena, L start level.
"""

from __future__ import annotations

import pygame

from ..engine import campaign
from ..engine.horde import ARENAS
from . import ui
from .ui import AMBER, DIM, GREEN, ORANGE, RED, TEXT

CONTROLS = (
    ("MOVE", [("key", "A"), ("key", "D"), "OR", ("key", "\u2190"), ("key", "\u2192")]),
    ("JUMP", [("key", "W"), ("key", "SPACE"), "OR", ("key", "\u2191")]),
    ("AIM, FIRE", ["MOUSE,", ("key", "LEFT BUTTON"), "OR", ("key", "J")]),
    ("USE A POWER", ["HOLD", ("key", "SHIFT"), "OR", ("key", "RIGHT BUTTON")]),
    ("WEAPONS", [("key", "1"), "-", ("key", "4"), ("key", "Q"), ("key", "E"), "OR THE WHEEL"]),
    ("SWITCHES, DOORS", [("key", "S"), "OR", ("key", "\u2193"), "WHEN YOU TOUCH ONE"]),
    ("DASH", [("key", "F"), "QUICK DODGE, NO DAMAGE"]),
    ("LAST CONSOLE", [("key", "R"), "CAMPAIGN ONLY"]),
    ("PAUSE", [("key", "ESC")]),
    ("FULL SCREEN", [("key", "F11"), "OR", ("key", "CMD"), ("key", "F")]),
)
GAMEPAD = ("Gamepad: left stick moves, right stick aims, A jumps, B acts, X dashes, RT fires, LB and RB switch "
           "weapons. On menus: the D-pad, A to choose, B to go back.")
LEGEND = (
    ("HEALTH  (bottom left)", "Your health, and its limit: 200 with ultra health."),
    ("DASH", "Refills after each dash. Dash when it is full."),
    ("WEAPONS  (bottom middle)", "Each one's key and ammo. The framed one is in your hands; the laser "
                                 "never runs out."),
    ("POWER  (top right)", "The power-up you carry, and the keys that use it."),
    ("WAVE PANEL  (top left)", "In Horde: the wave, enemies left, score and combo."),
)
HORDE_BRIEF = (
    ("THE GOAL", "Survive wave after wave. Each wave is bigger; every 5th brings a Juggernaut boss."),
    ("BETWEEN WAVES", "Walk over the health and ammo that drop, then pick 1 of 3 upgrades."),
    ("POWER-UPS", "Speed and flight work while you HOLD SHIFT or the RIGHT MOUSE BUTTON."),
    ("SCORE", "Kills score points. Quick kills build a combo up to x5. A wave without damage pays a bonus."),
    ("THE ARENA", "It is sealed: nothing can fall or fly out, and every enemy comes for you."),
)


LEVEL_BLURBS = {  # what the level holds, and what follows it
    "level00": ("On-screen tips teach the controls.", "Level 1 and Level 2 follow."),
    "level01": ("The prison: alien ants, gun turrets and secret walls.", "Level 2 follows."),
    "level02": ("Robots, a tracking gun and the Juggernaut.", "The last level."),
}
ARENA_BLURBS = {  # from each arena's size in engine/horde.py
    "prison": "The widest arena, under a low ceiling.",
    "rooftop": "Open sky: the highest ceiling, and room for flyers.",
    "pit": "The smallest arena: nowhere to hide.",
}
PAGE_TITLES = {"campaign": "CAMPAIGN", "horde": "HORDE"}


def menu_items(app, page: str | None = None) -> list[dict]:
    """The lines of a title page (by default the one shown), from the app's current settings. The
    main page opens two lists: PLAY CAMPAIGN lists only the levels, HORDE only the arenas."""
    page = page or app.menu_page
    if page == "campaign":
        ghost = {"key": "ghost", "label": "GHOST", "value": "ON" if app.show_ghost else "OFF",
                 "desc": ["A red GHOST replays your best run on the level, to race.",
                          "Off only hides it: your best is still saved. G switches it in play."]}
        return [*(_level_item(app, name) for name in campaign.playable_levels()), ghost, BACK_ITEM]
    if page == "horde":
        return [*(_arena_item(app, key) for key in ARENAS), BACK_ITEM]
    items = []
    if app.modern and not app.args.playtest:
        items.append({"key": "campaign", "label": "PLAY CAMPAIGN", "value": None, "opens": True,
                      "desc": ["Training, then Level 1, then Level 2. Health and weapons carry on.",
                               "Enter to choose where to start."]})
    elif not app.modern:
        items.append({"key": "campaign", "label": "PLAY LEVEL 1", "value": None,
                      "desc": ["The original Level 1, exactly as it played in 1996."]})
    else:  # a playtest that switched to Remastered stays on Level 1
        items.append({"key": "campaign", "label": "PLAY LEVEL 1", "value": None,
                      "desc": ["Level 1 with Remastered's rules."]})
    if app.modern:
        items.append({"key": "horde", "label": "HORDE", "value": None, "opens": True,
                      "desc": ["Survive endless waves in a sealed arena; upgrades between waves.",
                               "Enter to choose an arena."]})
    items.append({"key": "difficulty", "label": "DIFFICULTY", "value": app.args.difficulty.upper(),
                  "desc": ["How hard enemies hit and how much health pickups give."]})
    items.append({"key": "mode", "label": "MODE", "value": app.args.mode.upper(),
                  "desc": ["REMASTERED: wider view, dash, campaign and Horde."
                           if app.modern else "CLASSIC: the faithful port of the original Level 1.",
                           "Left or right to switch."]})
    items.append({"key": "controls", "label": "CONTROLS", "value": None, "desc": ["Keys, mouse and gamepad."]})
    items.append({"key": "quit", "label": "QUIT", "value": None, "desc": ["Back to the desktop."]})
    return items


def dev_items(app) -> list[dict]:
    """The dev menu: the four power-ups (and none), the two switches, and back to the game."""
    from ..engine.behaviors.player import NO_POWER
    from .modern_hud import POWERS

    now = app.game.player.lvars.get("special_power", NO_POWER)
    items = []
    for power, (name, _image, verb) in [*POWERS.items(), (NO_POWER, ("NO POWER-UP", None, None))]:
        use = f"Hold SHIFT or right mouse {verb.lower()}." if verb else "Health up to 200."
        items.append({"key": "power", "power": power, "label": name, "value": None,
                      "note": "CARRIED" if power == now else None, "note_color": GREEN,
                      "desc": [use if power else "Drop the power-up you carry.",
                               "Enter gives it, and back to the game."]})
    on = app.dev_opts
    items.append({"key": "health", "label": "UNLIMITED HEALTH", "value": "ON" if on["health"] else "OFF",
                  "desc": ["No damage, and health stays full.", "Off: hits hurt again, to test damage."]})
    items.append({"key": "ammo", "label": "UNLIMITED AMMO", "value": "ON" if on["ammo"] else "OFF",
                  "desc": ["Laser, grenades, rockets and napalm: always full (the laser at its fast rate).",
                           "Off: shots use ammo again, from full."]})
    items.append({"key": "resume", "label": "BACK TO THE GAME", "value": None, "desc": ["Or Tab, or Esc."]})
    return items


BACK_ITEM = {"key": "back", "label": "BACK", "value": None, "desc": ["Back to the title menu."]}


def _level_item(app, name: str) -> dict:
    best = app.best_time(name)
    return {"key": "level", "level": name, "label": campaign.title(name).upper(), "value": None,
            "note": f"BEST {best}" if best else None,
            "desc": [*LEVEL_BLURBS.get(name, ()), f"Your best time here: {best}." if best else "No best time yet."]}


def _arena_item(app, key: str) -> dict:
    top = app.best_score(key)
    return {"key": "arena", "arena": key, "label": ARENAS[key].title.split(" (")[0].upper(), "value": None,
            "note": f"BEST {top}" if top else None,
            "desc": [f"{ARENAS[key].title}. {ARENA_BLURBS.get(key, '')}",
                     f"Your best score here: {top}." if top else "No best score yet."]}


class Screens:
    def __init__(self, theme: ui.Theme):
        self.t = theme
        self.u = theme.u
        self.rows: list[tuple[pygame.Rect, int]] = []
        self.arrows: list[tuple[pygame.Rect, int, int]] = []

    # --- the title -------------------------------------------------------------------------------
    def title(self, screen, app) -> None:
        t, u = self.t, self.u
        w, h = screen.get_size()
        t.dim(screen, 175)
        art = t.sprites.image("art/title.spe", "title_screen") if t.sprites else None
        if art is not None:
            s = max(1, h // 230)
            art = pygame.transform.scale(art, (art.get_width() * s, art.get_height() * s))
            screen.blit(art, (int(w * 0.27) - art.get_width() // 2, (h - art.get_height()) // 2 - 6 * u))
        heading = PAGE_TITLES.get(app.menu_page) or ("REMASTERED" if app.modern else "CLASSIC")
        pw = min(222 * u, int(w * 0.5))
        self._menu(screen, menu_items(app), app.menu_index, heading, AMBER if app.modern else TEXT, w - pw - 12 * u)
        if app.dev and app.modern:
            from .modern_hud import dev_badge

            dev_badge(t, screen, (8 * u, 8 * u))
        if app.menu_page == "main":
            parts = [("key", "ENTER"), "SELECT  ", ("key", "F1"), "CONTROLS  ", ("key", "F11"), "FULL SCREEN"]
        else:
            parts = [("key", "ENTER"), "START  ", ("key", "ESC"), "BACK  ", ("key", "F11"), "FULL SCREEN"]
        t.keys_line(screen, parts, (w // 2, h - 22 * u), align="center")
        t.text(screen, "Original game (c) 1996 Crack dot Com: public-domain code and shareware data",
               (w // 2, h - 9 * u), DIM, align="center")

    def _menu(self, screen, items: list[dict], focus_index: int, heading: str, color, left: int | None = None,
              dy: int = -4, keys: list | None = None) -> None:
        """A menu panel in the original's art: a heading, a line per item (a setting's value
        between arrows, a ► for a line that opens a list, or a note), the focused line's
        description, and ``keys`` (a keys line) at its foot. ``left`` None centres it. Lays out
        ``rows`` and ``arrows`` for the mouse."""
        t, u = self.t, self.u
        w, h = screen.get_size()
        pw = min(222 * u, int(w * 0.5))
        row_h = 17 * u
        desc_rows = max(sum(len(t.wrap(line, pw - 16 * u)) for line in it["desc"]) for it in items)
        ph = 30 * u + len(items) * row_h + (8 + 9 * desc_rows) * u + (18 * u if keys else 0)
        panel = pygame.Rect((w - pw) // 2 if left is None else left, (h - ph) // 2 + dy * u, pw, ph)
        t.panel(screen, panel)
        t.text(screen, heading, (panel.centerx, panel.top + 8 * u), color, size="big", align="center")
        self.rows, self.arrows = [], []
        y = panel.top + 24 * u
        for i, it in enumerate(items):
            r = pygame.Rect(panel.left + 6 * u, y, pw - 12 * u, row_h - 2 * u)
            focus = i == focus_index
            if focus:
                pygame.draw.rect(screen, ui.RUST[2], r)
                pygame.draw.rect(screen, AMBER, r, u)
            self.rows.append((r, i))
            t.text(screen, it["label"], (r.left + 5 * u, r.top + 4 * u), AMBER if focus else TEXT, size="big")
            if it["value"] is not None:
                vw, _ = t.measure(it["value"])
                right = r.right - 5 * u
                ra = t.text(screen, "\u25ba", (right, r.top + 5 * u), AMBER if focus else DIM, align="right")
                t.text(screen, it["value"], (ra.left - 4 * u, r.top + 5 * u), TEXT, align="right")
                la = t.text(screen, "\u25c4", (ra.left - 8 * u - vw, r.top + 5 * u), AMBER if focus else DIM,
                            align="right")
                self.arrows.append((la.inflate(6 * u, 8 * u), i, -1))
                self.arrows.append((ra.inflate(6 * u, 8 * u), i, 1))
            elif it.get("opens"):  # opens its own list: Enter, a click or right
                t.text(screen, "\u25ba", (r.right - 5 * u, r.top + 5 * u), AMBER if focus else DIM, align="right")
            elif it.get("note"):
                t.text(screen, it["note"], (r.right - 5 * u, r.top + 5 * u), it.get("note_color", DIM), align="right")
            y += row_h
        desc = items[focus_index]["desc"] if 0 <= focus_index < len(items) else []
        y += 3 * u
        for line in desc:
            for part in t.wrap(line, pw - 16 * u):
                t.text(screen, part, (panel.left + 8 * u, y), DIM)
                y += 9 * u
        if keys:
            t.keys_line(screen, keys, (panel.centerx, panel.bottom - 19 * u), align="center")

    # --- developer test mode (devmode.py) ------------------------------------------------------
    def dev_menu(self, screen, app) -> None:
        self.t.dim(screen, 150)
        self._menu(screen, dev_items(app), app.dev_index % len(dev_items(app)), "DEV MODE", RED, dy=-10,
                   keys=[("key", "ENTER"), "CHOOSE  ", ("key", "\u2190"), ("key", "\u2192"), "SWITCH  ",
                         ("key", "TAB"), "BACK"])

    # --- Horde's briefing ------------------------------------------------------------------------
    def briefing(self, screen, app) -> None:
        t, u = self.t, self.u
        w, h = screen.get_size()
        t.dim(screen, 160)
        pw, ph = min(380 * u, w - 20 * u), 206 * u
        panel = pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)
        t.panel(screen, panel)
        t.text(screen, "HORDE", (panel.centerx, panel.top + 8 * u), AMBER, size="big", scale=2, align="center")
        t.text(screen, f"{ARENAS[app.arena].title.upper()}   DIFFICULTY {app.args.difficulty.upper()}",
               (panel.centerx, panel.top + 28 * u), TEXT, align="center")
        y = panel.top + 42 * u
        for head, body in HORDE_BRIEF:
            t.text(screen, head, (panel.left + 10 * u, y), ORANGE)
            for line in t.wrap(body, pw - 100 * u):
                t.text(screen, line, (panel.left + 86 * u, y), TEXT)
                y += 9 * u
            y += 4 * u
        y += 2 * u
        t.text(screen, "CONTROLS", (panel.left + 10 * u, y), ORANGE)
        quick = [("MOVE", [("key", "A"), ("key", "D")]), ("JUMP", [("key", "W")]),
                 ("FIRE", [("key", "LMB")]), ("DASH", [("key", "F")]), ("WEAPON", [("key", "1"), "-", ("key", "4")])]
        x = panel.left + 86 * u
        for label, keys in quick:
            r = t.keys_line(screen, [label, *keys], (x, y))
            x = r.right + 8 * u
        y += 16 * u
        t.keys_line(screen, ["ALL CONTROLS, AND WHAT EACH PART OF THE SCREEN MEANS:", ("key", "F1")],
                    (panel.centerx, y), align="center")
        t.keys_line(screen, [("key", "ENTER"), "OR CLICK: START WAVE 1", "    ", ("key", "ESC"), "BACK"],
                    (panel.centerx, panel.bottom - 16 * u), align="center")

    # --- controls and legend ---------------------------------------------------------------------
    def help(self, screen, app) -> None:
        """Two columns: every control on the left, what each part of the screen means on the right."""
        t, u = self.t, self.u
        w, h = screen.get_size()
        t.dim(screen, 190)
        pw, ph = min(456 * u, w - 12 * u), min(218 * u, h - 8 * u)
        panel = pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)
        t.panel(screen, panel)
        left = panel.left + 10 * u
        right = panel.left + 262 * u
        t.text(screen, "CONTROLS", (left, panel.top + 9 * u), AMBER, size="big")
        y = panel.top + 24 * u
        for label, parts in CONTROLS:
            t.text(screen, label, (left, y), ORANGE)
            t.keys_line(screen, parts, (left + 98 * u, y))
            y += 13 * u
        y += 2 * u
        for line in t.wrap(GAMEPAD, 244 * u):
            t.text(screen, line, (left, y), DIM)
            y += 9 * u
        t.text(screen, "THE SCREEN", (right, panel.top + 9 * u), AMBER, size="big")
        y = panel.top + 24 * u
        for label, body in LEGEND:
            t.text(screen, label, (right, y), ORANGE)
            y += 9 * u
            for line in t.wrap(body, panel.right - right - 10 * u):
                t.text(screen, line, (right, y), TEXT)
                y += 9 * u
            y += 4 * u
        t.keys_line(screen, [("key", "F1"), "OR", ("key", "ESC"), "CLOSE"], (panel.centerx, panel.bottom - 15 * u),
                    align="center")

    # --- Remastered's end and pause screens ------------------------------------------------------
    def _card(self, screen, title: str, color, lines, keys) -> None:
        t, u = self.t, self.u
        w, h = screen.get_size()
        t.dim(screen, 150)
        pw = min(320 * u, w - 20 * u)
        rows = sum(len(t.wrap(text, pw - 24 * u)) for text, _ in lines)
        ph = 46 * u + rows * 10 * u + 24 * u
        panel = pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)
        t.panel(screen, panel)
        t.text(screen, title, (panel.centerx, panel.top + 9 * u), color, size="big", scale=2, align="center")
        y = panel.top + 34 * u
        for text, col in lines:
            for part in t.wrap(text, pw - 24 * u):
                t.text(screen, part, (panel.centerx, y), col, align="center")
                y += 10 * u
        t.keys_line(screen, keys, (panel.centerx, panel.bottom - 16 * u), align="center")

    def pause(self, screen, app) -> None:
        restart = "RESTART RUN" if app.horde else "RESTART LEVEL"
        self._card(screen, "PAUSED", AMBER, [("The game waits for you.", DIM)],
                   [("key", "ESC"), "RESUME  ", ("key", "R"), restart + "  ", ("key", "F1"), "CONTROLS  ",
                    ("key", "T"), "TITLE  ", ("key", "X"), "QUIT"])

    def dead(self, screen, app) -> None:
        where = "the last console you saved at" if app.checkpoint is not app.level_start else "the start of the level"
        self._card(screen, "YOU DIED", RED, [(f"You go back to {where}, at full health.", TEXT)],
                   [("key", "SPACE"), "TRY AGAIN"])

    def complete(self, screen, app, lines: list[str]) -> None:
        from .app import clock_text

        s, f = app.stats, app.finish or {}
        body = [(f"TIME {clock_text(s['ticks'])}", AMBER),
                (f"{s['kills']} kills, {s['secrets']} secrets, {s['deaths']} deaths", TEXT),
                (f"Damage taken {s['damage_taken']}, shots fired {s['shots']}, enemies hit {s['enemies_hit']}, "
                 f"dashes {s['dashes']}", DIM)]
        best = f.get("best")
        if f.get("dev"):
            body.append(("DEV MODE: NOT RECORDED", RED))
        elif f.get("new_best"):
            was = f" (was {clock_text(best['ticks'])})" if best else ""
            body.append((f"NEW BEST TIME{was}: saved as your ghost", GREEN))
        elif best:
            body.append((f"Your best: {clock_text(best['ticks'])}", TEXT))
        keys = ([("key", "ENTER"), f"ON TO {campaign.title(app.next_level).upper()}  ", ("key", "ESC"), "TITLE"]
                if app.next_level else [("key", "ENTER"), "BACK TO THE TITLE"])
        self._card(screen, lines[0], GREEN, body, keys)

    def horde_over(self, screen, app, lines: list[str]) -> None:
        body = [(line, AMBER if line.startswith(("#", "NEW")) else TEXT) for line in lines[1:]]
        self._card(screen, "HORDE OVER", RED, body,
                   [("key", "ENTER"), "PLAY AGAIN  ", ("key", "ESC"), "TITLE"])
