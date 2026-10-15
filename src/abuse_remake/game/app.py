"""``abuse-remake``: play Level 1, or Remastered mode's campaign.

Rules run at a fixed 15 Hz, as in the original; drawing runs at the display rate with
interpolation in between. Classic mode shows the original 316x162 view and the original rules,
on Level 1 only. Remastered mode shows a wider 16:9 view with modern effects and adds a dash (F)
with brief invulnerability, quick restart at the last console (R), a stats screen with your best
time, a ghost race against your best finished run, and the campaign: the shareware training
level, Level 1 and Level 2, each exit leading on to the next level (L on the title picks where
to start).

Controls (original defaults, plus modern ones):
  move A/D or arrows; jump W, Up or Space; action (switches, doors, consoles, exit) S or Down
  aim with the mouse; fire left button (or J); special right button (or Shift)
  weapons 1-4, Ctrl/Home and Insert/PageUp (the original keys),
  Q/E, the mouse wheel or the middle button; pause Esc; gamepad: left stick move, right stick
  aim, A jump, B action, right trigger fire, bumpers switch weapon
  Remastered only: dash F (gamepad X), quick restart at the last console R, ghost on/off G
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

from ..engine import campaign
from ..engine.game import Game, WeaponCommand
from ..engine.horde import ARENAS, CARDS
from ..engine.horde import VERSION as HORDE_VERSION
from ..engine.view import VIEW_H, VIEW_W, Inputs
from ..engine.world import DIFFICULTIES

TICK = 1.0 / 15.0
# The training level's messages name the original keys (english.lsp:226-246); the modern ones too
MODERN_KEYS = {0: "  (or J)", 5: "  (or left Shift)", 6: "  (or Q/E, the mouse wheel)", 7: "  (W or Up)",
               8: "  (S or Down)", 2: "  (S or Down)", 3: "  (S or Down)", 4: "  (S or Down)",
               11: "  (S or Down)"}
MAX_CATCHUP = 4 * TICK  # after a stall, run at most 4 owed ticks instead of all of them


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="abuse-remake", description="Abuse (1996), Level 1, rebuilt")
    p.add_argument("--mode", choices=("classic", "remastered"), default=None,
                   help="default: remastered, or classic with --playtest (playtests are the human reference)")
    p.add_argument("--difficulty", choices=DIFFICULTIES, default="hard")
    p.add_argument("--seed", type=int, default=None, help="random table start (default: from the clock)")
    p.add_argument("--scale", type=int, default=0, help="window scale (default: fit the screen)")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--record", type=Path, help="write this session's inputs as a replayable trace")
    p.add_argument("--playtest", action="store_true", help="record into playtests/raw/ with a session id")
    p.add_argument("--horde", action="store_true", help="Remastered's Horde: survive waves of enemies")
    p.add_argument("--arena", choices=sorted(ARENAS), default="prison", help="Horde's arena (A on the title)")
    p.add_argument("--level", choices=campaign.LEVELS, default="level01",
                   help="where Remastered's campaign starts (Classic is Level 1; Horde uses --arena)")
    p.add_argument("--skip-title", action="store_true")
    p.add_argument("--frames", type=int, default=0, help="run N display frames with scripted input, then exit")
    p.add_argument("--screenshot", type=Path, help="save the last frame (with --frames)")
    args = p.parse_args(argv)
    if args.horde and args.mode == "classic":
        p.error("--horde is a Remastered rule set; it cannot run with --mode classic")
    if args.arena != "prison" and not args.horde:
        p.error("--arena is for Horde; add --horde")
    if args.level != "level01" and (args.mode == "classic" or args.playtest or args.horde):
        p.error("--level is for Remastered's campaign; Classic mode and playtests are Level 1, Horde uses --arena")
    if not campaign.playable(args.level):
        p.error(f"{campaign.title(args.level)} is not playable yet: its objects are not all ported")
    if args.mode is None:
        args.mode = "classic" if args.playtest else "remastered"
    return args


class App:
    def __init__(self, args):
        import pygame

        self.pg = pygame
        self.args = args
        if args.frames:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pygame.init()
        if getattr(args, "horde", False):
            args.mode = "remastered"  # Horde is a Remastered rule set
        self.modern = args.mode == "remastered"
        self.view_w, self.view_h = (480, 270) if self.modern else (VIEW_W, VIEW_H)
        info = pygame.display.Info()
        scale = args.scale or max(2, min((info.current_w or 1600) // self.view_w,
                                         ((info.current_h or 900) - 80) // self.view_h))
        self.scale = scale
        from .display import opaque_surface, window_flags

        size = (self.view_w * scale, self.view_h * scale)
        self.window = pygame.display.set_mode(size, window_flags(args))
        self.screen = opaque_surface(size)  # every frame is drawn here, then copied to the window
        pygame.display.set_caption("Abuse — Level 1 (remake)")
        from .audio import Audio
        from .hud import Hud
        from .particles import Particles
        from .render import Renderer
        from .sprites import SpriteCache

        self.sprites = SpriteCache()
        self.audio = Audio(enabled=not args.no_audio and not args.frames, modern=args.mode == "remastered")
        self.hud = Hud(self.sprites)
        self.particles = Particles()
        self.seed = args.seed if args.seed is not None else int(time.time()) % 1024
        if not self.modern or getattr(args, "horde", False):
            args.level = "level01"  # the campaign is Remastered only; Horde picks its level by arena
        self.level = getattr(args, "level", "level01")
        self.Renderer = Renderer
        self.joystick = None
        self.clock = pygame.time.Clock()
        self.state = "play" if (args.skip_title or args.frames) else "title"
        self.trace = getattr(self, "trace", None)  # one trace per session, kept across title toggles
        self.joy_rest: list[float] = []
        self.ghost_painter = None
        if self.trace is None:
            self._open_trace()
        self.new_game()

    # --- game lifecycle ---
    def new_game(self):
        self.horde = bool(getattr(self.args, "horde", False)) and self.modern
        self.level = getattr(self.args, "level", "level01")
        self.arena = getattr(self.args, "arena", "prison")
        self.game = Game(seed=self.seed, difficulty=self.args.difficulty, level=self.level, remastered=self.modern,
                         horde=self.horde, arena=self.arena)
        self.pending_card: int | None = None
        self.renderer = self.Renderer(self.game, self.sprites, self.view_w, self.view_h)
        self.renderer.modern = self.modern
        self.game.world.globals["save_hook"] = self._on_console_save
        self._level_started()
        self.acc = 0.0
        self.pending_weapon: WeaponCommand | None = None
        self.pending_dash = False
        self.show_ghost = True
        self._write({"kind": "new_game", "seed": self.seed, "difficulty": self.args.difficulty,
                     "mode": self.args.mode, "horde": self.horde, "level": self.level, "arena": self.arena,
                     "horde_version": HORDE_VERSION,
                     "rules": "remastered" if self.modern else "classic"})

    def _level_started(self) -> None:
        """Per-level state: the restart points, the stats screen's counts, records and ghost."""
        from .remaster import GhostRecorder, load_ghost

        where = f"Horde: {ARENAS[self.arena].title}" if self.horde else campaign.title(self.level)
        self.pg.display.set_caption(f"Abuse — {where} (remake)")
        self.level_start = self.game.snapshot()
        self.checkpoint = self.level_start
        self.stats = {"ticks": 0, "kills": 0, "secrets": 0, "deaths": 0, "shots": 0, "enemies_hit": 0,
                      "damage_taken": 0, "dashes": 0}
        self.hit_uids: set[int] = set()
        self.finish: dict | None = None
        self.next_level: str | None = None
        self.locked_said = -1000
        self.ghost_rec = GhostRecorder() if self.modern and not self.horde else None
        self.ghost = load_ghost(self.args.difficulty, self.record_level) if self.modern and not self.horde else None

    @property
    def record_level(self) -> str:
        """Records and ghosts keep a level reached from the one before apart from fresh starts."""
        return f"campaign-{self.level}" if self.game.carried else self.level

    def change_level(self, name: str) -> None:
        """Go on into the level an exit led to, keeping the player and weapons (Remastered's
        campaign; ``Game(carry=...)`` follows the original's level change)."""
        self.level = name
        self.game = Game(seed=self.seed, difficulty=self.args.difficulty, level=name, remastered=True,
                         carry=self.game)
        self.game.view.update_scroll()  # the camera only: the first tick snaps the view the same way
        self._rebind()
        self._level_started()
        self._write({"kind": "level", "level": name})
        self.hud.say(campaign.title(name))

    def _open_trace(self):
        path = self.args.record
        if self.args.playtest:
            sid = time.strftime("%Y%m%d-%H%M%S")
            path = Path("playtests/raw") / f"session-{sid}.jsonl"
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.trace = open(path, "w")  # noqa: SIM115 - closed on exit
        self._write({"kind": "header", "game": "abuse_remake", "level": getattr(self.args, "level", "level01"),
                     "player": "human", "format": "human-trace-1"})

    def _write(self, row: dict) -> None:
        """Human traces (game/human_replay.py replays them): a header, then for each game a
        new_game row, one input row per tick, and restore and check rows."""
        if self.trace is not None:
            self.trace.write(json.dumps(row) + "\n")

    def _check(self, why: str) -> None:
        self._write({"kind": "check", "why": why, "frames": self.game.frames, "state_hash": self.game.state_hash()})

    def _on_console_save(self, console):
        # restart_ai calls this with the player's health already set for the save
        self.checkpoint = self.game.snapshot()
        self.hud.say("Station secured!")

    def _restore(self, which: str) -> None:
        """Back to the level start or the last console save, as the original's restart_player
        reloads the level or the save (people.lsp:503-521)."""
        self._check(f"before restore to {which}")
        snap = self.level_start if which == "level_start" else self.checkpoint
        self.game.restore(snap)
        if snap is self.level_start:
            campaign.restart_health(self.game)  # no console save: the level restarts at full health
        if which == "level_start":
            self.checkpoint = self.level_start  # a restarted level has no console save yet
        self._rebind()
        self._write({"kind": "restore", "to": which})

    # --- input ---
    def read_inputs(self) -> Inputs:
        pg = self.pg
        keys = pg.key.get_pressed()
        mb = pg.mouse.get_pressed(3)
        left = keys[pg.K_a] or keys[pg.K_LEFT]
        right = keys[pg.K_d] or keys[pg.K_RIGHT]
        x = -1 if left else (1 if right else 0)  # both held: left wins, as get_local_input does
        up = keys[pg.K_w] or keys[pg.K_UP] or keys[pg.K_SPACE]
        down = keys[pg.K_s] or keys[pg.K_DOWN]
        y = -1 if up else (1 if down else 0)
        fire = mb[0] or keys[pg.K_j]
        special = mb[2] or keys[pg.K_LSHIFT]
        mx, my = pg.mouse.get_pos()
        px, py = self.screen_to_game(mx, my)
        if self.joystick is not None:
            j = self.joystick

            def axis(i: int) -> float:  # deflection from the resting value measured at connection,
                if i >= j.get_numaxes():  # so a trigger that rests at -1 reads as 0
                    return 0.0
                return j.get_axis(i) - (self.joy_rest[i] if i < len(self.joy_rest) else 0.0)

            ax = axis(0)
            if abs(ax) > 0.35:
                x = 1 if ax > 0 else -1
            if j.get_numbuttons() > 0 and j.get_button(0):
                y = -1
            if j.get_numbuttons() > 1 and j.get_button(1):
                y = 1
            if j.get_numaxes() > 4:
                rx, ry = axis(2), axis(3)
                if math.hypot(rx, ry) > 0.3:
                    p = self.game.player
                    px, py = p.x + int(rx * 120), p.y - 20 + int(ry * 120)
                if axis(5) > 0.3:
                    fire = True
        return Inputs(x=x, y=y, b1=int(special), b2=int(fire), pointer_x=px, pointer_y=py)

    def screen_to_game(self, sx, sy):
        """The level point under the mouse, through the camera that was drawn last and the real
        window scale (a fullscreen mode can differ from the requested scale)."""
        xoff, yoff = self.renderer.last_cam
        sw, sh = self.screen.get_size()
        return int(sx * self.view_w / sw + xoff), int(sy * self.view_h / sh + yoff)

    def scripted_inputs(self, tick) -> Inputs:
        p = self.game.player
        rng = random.Random(tick // 20)
        return Inputs(x=1 if rng.random() < 0.7 else -1, y=-1 if tick % 30 == 0 else 0,
                      b2=int(tick % 4 == 0), pointer_x=p.x + 120, pointer_y=p.y - 25)

    # --- loop ---
    def run(self) -> int:
        pg = self.pg
        frames = 0
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for ev in pg.event.get():
                running = self.on_event(ev) and running
            if self.state == "play":
                self.advance(dt if not self.args.frames else TICK / 2, frames)
            self.draw()
            frames += 1
            if self.args.frames and frames >= self.args.frames:
                running = False
        if self.args.screenshot:
            pg.image.save(self.screen, str(self.args.screenshot))
        if self.trace:
            self._check("session end")
            self.trace.close()
        pg.quit()
        return 0

    def on_event(self, ev) -> bool:
        """Handle one window event; False asks to quit."""
        pg = self.pg
        if ev.type == pg.QUIT:
            return False
        if ev.type == pg.KEYDOWN:
            from .display import is_fullscreen_key

            if is_fullscreen_key(ev.key, getattr(ev, "mod", 0)):
                self.toggle_fullscreen()  # in every state, and nothing else: no start, no dash
                return True
            return self.on_key(ev.key)
        if ev.type == pg.JOYDEVICEADDED and self.joystick is None:
            self.joystick = pg.joystick.Joystick(ev.device_index)
            self.joy_rest = [self.joystick.get_axis(i) for i in range(self.joystick.get_numaxes())]
        elif ev.type == pg.JOYDEVICEREMOVED:
            self.joystick, self.joy_rest = None, []
        elif ev.type == pg.MOUSEBUTTONDOWN and ev.button == 2 and self.state == "play":
            self.pending_weapon = WeaponCommand(cycle=-1)  # middle button: previous weapon
        elif ev.type == pg.MOUSEWHEEL and self.state == "play":
            self.pending_weapon = WeaponCommand(cycle=-1 if ev.y > 0 else 1)
        elif ev.type == pg.JOYBUTTONDOWN and self.state == "play" and ev.button in (4, 5):
            self.pending_weapon = WeaponCommand(cycle=-1 if ev.button == 4 else 1)
        elif self._cards_up() and ev.type == pg.JOYBUTTONDOWN and ev.button in (0, 1, 2):
            self.pending_card = ev.button  # A, B, X choose a card while they are up
            self.card_masks_input = True
        elif self._cards_up() and ev.type == pg.MOUSEBUTTONDOWN and ev.button == 1:
            hit = [i for i, r in enumerate(self.hud.card_rects) if r.collidepoint(ev.pos)]
            if hit:
                self.pending_card = hit[0]
                self.card_masks_input = True
        elif ev.type == pg.JOYBUTTONDOWN and self.state == "play" and ev.button == 2 and self.modern:
            self.pending_dash = True
        return True

    def toggle_fullscreen(self) -> None:
        """Full screen on or off. The frame keeps its size; SDL scales it (``pygame.SCALED``)."""
        pg = self.pg
        self.args.fullscreen = not getattr(self.args, "fullscreen", False)
        if self.args.frames:
            return  # headless: there is no window
        try:
            pg.display.toggle_fullscreen()
        except pg.error:
            from .display import window_flags

            pg.display.set_mode(self.screen.get_size(), window_flags(self.args))
        self.window = pg.display.get_surface()

    def advance(self, dt: float, frame_no: int = 0) -> None:
        """Run the 15 Hz ticks that ``dt`` seconds of display time owe, and none after the end."""
        self.acc = min(self.acc + dt, MAX_CATCHUP)
        while self.acc >= TICK and self.state == "play":
            self.acc -= TICK
            self.tick(frame_no)

    def on_key(self, key) -> bool:
        pg = self.pg
        if self.state == "title":
            if key in (pg.K_RETURN, pg.K_SPACE):
                self.state = "play"
            elif key == pg.K_m:
                self.args.mode = "classic" if self.modern else "remastered"
                if self.args.mode == "classic":
                    self.args.horde = False  # Horde is Remastered only
                self.__init__(self.args)
                self.state = "title"
            elif key == pg.K_h:
                self.args.horde = not getattr(self.args, "horde", False)
                if self.args.horde:
                    self.args.mode = "remastered"
                self.__init__(self.args)
                self.state = "title"
            elif key == pg.K_d:
                i = DIFFICULTIES.index(self.args.difficulty)
                self.args.difficulty = DIFFICULTIES[(i + 1) % len(DIFFICULTIES)]
                self.new_game()
            elif key == pg.K_a and self.horde:
                keys = list(ARENAS)
                self.args.arena = keys[(keys.index(self.arena) + 1) % len(keys)]
                self.new_game()
            elif key == pg.K_l and self.modern and not self.horde and not self.args.playtest:
                levels = campaign.playable_levels()
                i = levels.index(self.level) if self.level in levels else -1
                self.args.level = levels[(i + 1) % len(levels)]
                self.new_game()
            elif key == pg.K_ESCAPE:
                return False
        elif self.state == "play":
            if key == pg.K_ESCAPE:
                self.state = "paused"
            elif self.horde and self.game.horde.state["cards"] and pg.K_1 <= key <= pg.K_3:
                self.pending_card = key - pg.K_1  # while upgrade cards are up, 1/2/3 choose one
            elif pg.K_1 <= key <= pg.K_7:
                self.pending_weapon = WeaponCommand(select=key - pg.K_1)
            elif key == pg.K_q:
                self.pending_weapon = WeaponCommand(cycle=-1)
            elif key == pg.K_e:
                self.pending_weapon = WeaponCommand(cycle=1)
            elif key in (pg.K_LCTRL, pg.K_RCTRL, pg.K_HOME):  # the original's previous weapon
                self.pending_weapon = WeaponCommand(cycle=-1)
            elif key in (pg.K_INSERT, pg.K_PAGEUP):  # and next weapon (view.c:606-612)
                self.pending_weapon = WeaponCommand(cycle=1)
            elif key == pg.K_l:
                self.renderer.lighting = not self.renderer.lighting
            elif self.modern and key == pg.K_f:
                self.pending_dash = True
            elif self.modern and key == pg.K_r:
                self._restore("checkpoint")  # quick restart at the last console
                self.hud.say("Back to the last console")
            elif self.modern and key == pg.K_g:
                self.show_ghost = not self.show_ghost
        elif self.state == "paused":
            if key == pg.K_ESCAPE:
                self.state = "play"
            elif key == pg.K_r:
                self._restore("level_start")
                self.state = "play"
            elif key == pg.K_x:
                return False
        elif self.state == "dead":
            if key == pg.K_SPACE:  # the original waits for space (cop.c:668-674)
                self._restore("checkpoint")
                self.state = "play"
        elif self.state == "complete" and self.next_level and key in (pg.K_RETURN, pg.K_SPACE):
            self.change_level(self.next_level)
            self.state = "play"
        elif self.state in ("complete", "horde_over"):
            if key in (pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE):
                self.seed = (self.seed + 1) % 1024
                self.new_game()
                self.state = "title"
        return True

    def stats_lines(self) -> list[str]:
        s = self.stats
        lines = [f"{campaign.title(self.level).upper()} COMPLETE" if self.modern else "LEVEL COMPLETE",
                 f"time {clock_text(s['ticks'])}",
                 f"kills {s['kills']}   secrets {s['secrets']}   deaths {s['deaths']}"]
        if self.modern:
            lines.append(f"damage taken {s['damage_taken']}   shots fired {s['shots']}   enemies hit "
                         f"{s['enemies_hit']}   dashes {s['dashes']}")
            f = self.finish or {}
            best = f.get("best")
            if f.get("new_best"):
                lines.append("NEW BEST TIME" + (f" (was {clock_text(best['ticks'])})" if best else "")
                             + " - saved as your ghost")
            elif best:
                lines.append(f"best {clock_text(best['ticks'])}")
        if self.next_level:
            lines.append(f"Enter: on to {campaign.title(self.next_level)}    Esc: back to the title")
        else:
            lines.append("Enter to continue")
        return lines

    def _cards_up(self) -> bool:
        return self.state == "play" and self.horde and bool(self.game.horde.state["cards"])

    def horde_over_lines(self) -> list[str]:
        st = self.game.horde.state
        f = self.finish or {}
        lines = [f"HORDE OVER - {ARENAS[self.arena].title}",
                 f"score {st['score']}   waves cleared {st['cleared']}   kills {st['kills']}   "
                 f"best combo x{st['best_combo']}"]
        by = ", ".join(f"{n} {HORDE_NAMES.get(k, k)}" for k, n in sorted(st["kills_by"].items()))
        if by:
            lines.append(by)
        if f.get("rank"):
            lines.append(f"#{f['rank']} on this arena's top 10")
        top = f.get("top") or []
        if top:
            lines.append("top 5 of the table:")
        for i, r in enumerate(top[:5]):
            lines.append(f"{i + 1}. {r['score']}  ({r['cleared']} waves, {r['kills']} kills)")
        return lines + ["Enter to continue"]

    def _rebind(self):
        self.renderer.game = self.game
        self.renderer.reset_camera()
        self.game.world.globals["save_hook"] = self._on_console_save
        self.particles.items.clear()

    def tick(self, frame_no):
        inp = self.scripted_inputs(self.stats["ticks"]) if self.args.frames else self.read_inputs()
        weapon, self.pending_weapon = self.pending_weapon, None
        dash_asked = False
        if self.pending_dash and self.game.remastered is not None:
            self.pending_dash = False
            dash_asked = True  # recorded as asked; the replay gets the same answer from the engine
            self.stats["dashes"] += int(self.game.remastered.request_dash(inp.x))
        card, self.pending_card = self.pending_card, None
        if getattr(self, "card_masks_input", False):  # the click or button that chose a card
            self.card_masks_input = False  # does not also fire, jump or act this tick
            inp = Inputs(x=inp.x, pointer_x=inp.pointer_x, pointer_y=inp.pointer_y)
        if card is not None and self.game.horde is not None:
            self.game.horde.choose(card)  # recorded as asked, like a dash
        hp_before = self.game.player.hp
        self.game.step(inp, weapon)
        self.renderer.note_tick()
        self.stats["ticks"] += 1
        if self.ghost_rec is not None:
            self.ghost_rec.capture(self.game)
        w = self.game.world
        for e in w.events:
            if e.kind == "enemy_killed":
                self.stats["kills"] += 1
            elif e.kind == "damage" and e.data.get("by_player") and e.data["target"] != self.game.player.uid \
                    and not e.data["type"].startswith("HIDDEN_WALL"):
                self.hit_uids.add(e.data["target"])
                self.stats["enemies_hit"] = len(self.hit_uids)
            elif e.kind == "horde_wave":
                boss = "  - BOSS WAVE" if e.data.get("boss") else ""
                self.hud.say(f"Wave {e.data['wave']}: {e.data['size']} incoming{boss}")
            elif e.kind == "horde_cleared":
                self.hud.say(f"Wave {e.data['wave']} cleared - supplies dropped. Pick an upgrade: 1, 2 or 3")
            elif e.kind == "horde_card":
                self.hud.say(f"Upgrade: {CARDS[e.data['card']]}")
            elif e.kind == "wall_destroyed":
                self.stats["secrets"] += 1
            elif e.kind == "help":
                self.hud.show_help(e.data["text"] + MODERN_KEYS.get(e.data["number"], ""))
            elif e.kind == "level_locked" and self.stats["ticks"] - self.locked_said > 45:
                self.locked_said = self.stats["ticks"]
                name = e.data["level"]
                why = "is not ready yet" if campaign.in_build(name) else "is not part of this remake"
                self.hud.say(f"{campaign.title(name)} {why}")
            elif e.kind == "shot" and e.data.get("by_player"):  # the player's own shots only
                self.stats["shots"] += 1
        self.stats["damage_taken"] += max(0, hp_before - self.game.player.hp)
        self.renderer.note_events(w.events)
        if self.modern:
            self.particles.on_events(w.events)
        self.audio.play_events(w.events, self.game.player.x, self.game.player.y)
        if self.trace:
            rec = {"kind": "input", "tick": self.stats["ticks"], "x": inp.x, "y": inp.y, "b1": inp.b1,
                   "b2": inp.b2, "px": inp.pointer_x, "py": inp.pointer_y}
            if weapon is not None:
                rec["weapon"] = {"select": weapon.select, "cycle": weapon.cycle}
            if dash_asked:
                rec["dash"] = 1
            if card is not None:
                rec["card"] = card
            self._write(rec)
        if self.horde and self.game.horde.state["over"]:
            from .remaster import record_horde

            st = self.game.horde.state
            self.finish = record_horde(self.args.difficulty, st["cleared"], st["kills"], arena=self.arena,
                                       score=st["score"])
            self.state = "horde_over"
        elif self.game.player.aistate >= 3:
            self.stats["deaths"] += 1
            self.state = "dead"
            self._check("died")
        if w.globals.get("level_complete"):
            self.state = "complete"
            self._check("level complete")
            if self.modern:
                from .remaster import record_finish

                self.next_level = w.globals.get("next_level")
                self.finish = record_finish(self.args.difficulty, self.stats, self.record_level)
                if self.finish["new_best"] and self.ghost_rec is not None:
                    self.ghost_rec.save(self.args.difficulty, self.record_level)

    def draw(self):
        pg = self.pg
        alpha = min(1.0, self.acc / TICK) if self.state == "play" else 1.0
        surf = self.renderer.render(alpha)
        if self.modern:
            self.particles.step(0.25)
            xoff, yoff = self.renderer.camera(alpha)
            if self.ghost and self.show_ghost and self.state == "play":
                # rows[k] is the state after tick k+1, and the game has run stats["ticks"] ticks
                row = self.ghost[max(0, min(self.stats["ticks"] - 1, len(self.ghost) - 1))]
                if self.ghost_painter is None:
                    from .remaster import GhostPainter

                    self.ghost_painter = GhostPainter(pg, self.sprites)
                self.ghost_painter.draw(surf, self.game, row, xoff, yoff)
            self.particles.draw(surf, xoff, yoff)
        pg.transform.scale(surf, self.screen.get_size(), self.screen)
        if self.state in ("play", "paused", "dead", "complete", "horde_over"):
            self.hud.draw(self.screen, self.game, self.stats)
        if self.horde and self.state == "play":
            self.hud.draw_horde(self.screen, self.game)
        if self.state == "play":
            mx, my = pg.mouse.get_pos()
            pg.draw.circle(self.screen, (255, 80, 80), (mx, my), 9, 1)
            pg.draw.line(self.screen, (255, 80, 80), (mx - 13, my), (mx - 5, my))
            pg.draw.line(self.screen, (255, 80, 80), (mx + 5, my), (mx + 13, my))
        if self.state == "title":
            start = f"    Start: {campaign.title(self.level)} (L)" if self.modern and not self.horde else ""
            levels = ", ".join(campaign.title(n) for n in campaign.playable_levels())
            self.hud.center(self.screen, ["ABUSE", "Level 1 — reconstructed" if not self.modern
                                          else f"Remastered — {levels}",
                                          f"Mode: {self.args.mode} (M)    Difficulty: {self.args.difficulty} (D)"
                                          + (f"    HORDE (H): {ARENAS[self.arena].title} (A)" if self.horde
                                             else "    Horde: off (H)") + start,
                                          "Enter to start    Esc to quit"],
                            "Original game © 1996 Crack dot Com (public-domain code and shareware data)")
        elif self.state == "paused":
            self.hud.center(self.screen, ["PAUSED", "Esc resume    R restart level    X quit"])
        elif self.state == "dead":
            self.hud.center(self.screen, ["YOU DIED", "Space to restart from the last save"])
        elif self.state == "complete":
            self.hud.center(self.screen, self.stats_lines())
        elif self.state == "horde_over":
            self.hud.center(self.screen, self.horde_over_lines())
        self.present()

    def present(self) -> None:
        """Copy the drawn frame to the window and show it."""
        self.window.blit(self.screen, (0, 0))
        self.pg.display.flip()


HORDE_NAMES = {"ANT_ROOF": "ants", "FLYER": "flyers", "GREEN_FLYER": "green flyers", "ROB1": "robots",
               "JUGGER": "juggernauts", "BOSS": "bosses"}


def clock_text(ticks: int) -> str:
    t = ticks // 15
    return f"{t // 60}:{t % 60:02d}.{(ticks % 15) * 100 // 15:02d}"


def main(argv=None) -> int:
    args = parse_args(argv)
    return App(args).run()


if __name__ == "__main__":
    sys.exit(main())
