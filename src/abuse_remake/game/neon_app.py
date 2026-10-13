"""Playable Neon Protocol campaign, Horde and tutorial. Input/presentation only."""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import pygame as pg

from ..engine.neon import NeonGame
from ..engine.view import Inputs
from ..engine.world import DIFFICULTIES, Event
from .app import MAX_CATCHUP, TICK
from .audio import Audio
from .controls import draw_controls
from .neon_art import WORLD_H, WORLD_W
from .neon_render import CYAN, H, NeonRenderer, W


class NeonApp:
    def __init__(self, args):
        self.args = args
        if args.frames:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pg.init()
        size = (W * args.scale, H * args.scale) if args.scale else (1280, 720)
        self.screen = pg.display.set_mode(size, pg.FULLSCREEN if args.fullscreen else pg.RESIZABLE)
        pg.display.set_caption("Neon Protocol / Campaign + Horde")
        self.audio = Audio(enabled=not args.no_audio and not args.frames)
        self.seed = args.seed if args.seed is not None else int(time.time()) % 1024
        self.game = NeonGame(self.seed, "campaign", args.difficulty)
        self.renderer = NeonRenderer(self.game)
        self.clock = pg.time.Clock()
        self.next_mode = None
        self.running = True
        self.state = "title"
        self.help_return = "title"
        self.selection = 0
        self.buttons = []
        self.acc = 0.0
        self.pending_select = None
        self.pending_cycle = 0
        self.pending_dash = False
        self.message, self.message_ticks = "", 0
        self.joystick = None
        self.joy_rest = []
        self.trace = None
        path = args.record
        if args.playtest:
            path = Path("playtests/raw") / f"neon-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            append = getattr(args, "_append_trace", False) and path.exists()
            self.trace = path.open("a" if append else "w")
            if not append:
                self.write({"kind": "header", "format": "neon-trace-1",
                            "player": getattr(args, "trace_player", "human"), "game": "neon_protocol"})
        variant = "tutorial" if args.tutorial else "horde" if args.horde else "campaign"
        # Explicit --horde/--tutorial still shows the title unless skip-title was requested,
        # but selects the requested variant for Enter and headless smoke runs.
        self.selection = ("campaign", "horde", "tutorial").index(variant)
        self.level_start = self.game.snapshot()
        self.checkpoint = self.level_start
        # The preview is a real simulation too: record it for quitting at the title after
        # a mode handoff. Zero-tick previews are omitted from replay summaries.
        self.write({"kind": "new_game", "rules": "neon", "seed": self.seed,
                    "variant": self.game.variant, "difficulty": self.game.difficulty})
        if args.skip_title or args.frames:
            self.start(variant)

    def write(self, row):
        if self.trace:
            self.trace.write(json.dumps(row) + "\n")

    def check(self, why):
        self.write({"kind": "check", "why": why, "state_hash": self.game.state_hash()})

    def close_trace(self):
        if self.trace:
            self.check("session end")
            self.trace.close()
            self.trace = None

    def start(self, variant):
        if self.state != "title":
            self.check("before new game")
        self.game = NeonGame(self.seed, variant, self.args.difficulty)
        self.renderer.reset(self.game)
        self.level_start = self.game.snapshot()
        self.checkpoint = self.level_start
        self.acc = 0.0
        self.pending_dash, self.pending_select, self.pending_cycle = False, None, 0
        self.state = "play"
        self.message = "Link all three relays. Clear security, then press S / Down." if variant == "campaign" else ""
        self.message_ticks = 120
        self.write({"kind": "new_game", "rules": "neon", "seed": self.seed, "variant": variant,
                    "difficulty": self.args.difficulty})

    def restore(self, which="checkpoint"):
        self.check(f"before restore to {which}")
        self.game.restore(self.level_start if which == "level_start" else self.checkpoint)
        if which == "level_start":
            self.checkpoint = self.level_start
        self.renderer.reset(self.game)
        self.acc = 0.0
        self.pending_dash, self.pending_select, self.pending_cycle = False, None, 0
        self.state = "play"
        self.message, self.message_ticks = "Checkpoint restored", 45
        self.write({"kind": "restore", "to": which})

    def screen_to_game(self, x, y):
        sw, sh = self.screen.get_size()
        cx, cy = self.renderer.last_camera
        return int(x * WORLD_W / sw + cx), int(y * WORLD_H / sh + cy)

    def read_inputs(self):
        k = pg.key.get_pressed()
        x = -1 if k[pg.K_a] or k[pg.K_LEFT] else 1 if k[pg.K_d] or k[pg.K_RIGHT] else 0
        y = -1 if k[pg.K_SPACE] or k[pg.K_w] or k[pg.K_UP] else 1 if k[pg.K_s] or k[pg.K_DOWN] else 0
        mx, my = self.screen_to_game(*pg.mouse.get_pos())
        fire = pg.mouse.get_pressed(3)[0] or k[pg.K_j]
        j = self.joystick
        if j:
            def axis(i):
                return j.get_axis(i) - self.joy_rest[i] if i < j.get_numaxes() else 0

            if abs(axis(0)) > .35:
                x = 1 if axis(0) > 0 else -1
            if j.get_numbuttons() and j.get_button(0):
                y = -1
            elif j.get_numbuttons() > 1 and j.get_button(1):
                y = 1
            if j.get_numaxes() > 3 and math.hypot(axis(2), axis(3)) > .3:
                mx, my = self.game.player.x + int(axis(2) * 180), self.game.player.y + 15 + int(axis(3) * 180)
            fire = fire or axis(5) > .3
        return Inputs(x=x, y=y, b2=int(fire), pointer_x=mx, pointer_y=my)

    def scripted_inputs(self):
        p = self.game.player
        targets = [e for e in self.game.enemies if abs(e.x - p.x) < 750]
        target = min(targets, key=lambda e: abs(e.x - p.x)) if targets else None
        tx, ty = (target.x + target.w // 2, target.y + target.h // 2) if target else (p.x + 200, p.y + 15)
        move = 1 if self.game.frames % 100 < 70 else -1
        return Inputs(x=move, y=-1 if self.game.frames % 30 == 0 else 0, b2=1, pointer_x=tx, pointer_y=ty)

    def tick(self, inp=None):
        inp = inp if inp is not None else self.scripted_inputs() if self.args.frames else self.read_inputs()
        asked = self.pending_dash
        if asked:
            self.game.request_dash(inp.x)
        select, cycle = self.pending_select, self.pending_cycle
        self.pending_dash, self.pending_select, self.pending_cycle = False, None, 0
        self.game.step(inp, select, cycle)
        self.write({"kind": "input", "x": inp.x, "y": inp.y, "b2": inp.b2,
                    "px": inp.pointer_x, "py": inp.pointer_y, "select": select, "cycle": cycle, "dash": asked})
        self.renderer.note_tick(self.game)
        sounds = []
        for e in self.game.events:
            kind = e["kind"]
            if kind == "checkpoint":
                self.checkpoint = self.game.snapshot()
                self.message, self.message_ticks = "Relay online / checkpoint saved / supplies recharged", 75
            elif kind == "locked":
                self.message, self.message_ticks = "Clear this sector's nearby security before linking", 45
            elif kind == "pickup":
                self.message, self.message_ticks = e["pickup"].upper() + " ACQUIRED", 40
            elif kind == "wave":
                self.message, self.message_ticks = f"Wave {e['wave']:02} / security inbound", 45
            elif kind == "wave_clear":
                self.message, self.message_ticks = "Wave cleared / collect supplies / regroup", 60
            elif kind == "empty":
                self.message, self.message_ticks = "No charges / press 1 for the unlimited pulse rifle", 30
            name = {"shot": ("ZAP_SND", "SWITCH_SND", "TELEPORTER_SND")[e.get("weapon", 0)],
                    "hurt": "PLAYER_PAIN0", "kill": "P_EXPLODE_SND", "pickup": "AMMO_SND",
                    "checkpoint": "SAVE_SND", "dash": "SWISH", "vortex": "FIREBOMB_SND"}.get(kind)
            if name:
                sounds.append(Event("sound", {"name": name, "x": e["x"], "y": e["y"]}))
        self.audio.play_events(sounds, self.game.player.x, self.game.player.y)
        self.message_ticks = max(0, self.message_ticks - 1)
        if self.game.status != "running":
            self.state = "dead" if self.game.status == "dead" else "complete"
            self.check(self.game.status)

    def advance(self, dt):
        if self.state != "play":
            return
        self.acc = min(self.acc + dt, MAX_CATCHUP)
        while self.acc >= TICK and self.state == "play":
            self.acc -= TICK
            self.tick()

    def on_key(self, key):
        if self.state == "controls":
            if key in (pg.K_ESCAPE, pg.K_F1, pg.K_c):
                self.state = self.help_return
                self.acc = 0.0
            return
        if key == pg.K_F1 or (key == pg.K_c and self.state == "paused"):
            self.help_return, self.state = self.state, "controls"
            return
        if self.state == "title":
            if key in (pg.K_UP, pg.K_w):
                self.selection = (self.selection - 1) % 4
            elif key in (pg.K_DOWN, pg.K_s):
                self.selection = (self.selection + 1) % 4
            elif key in (pg.K_RETURN, pg.K_SPACE):
                self.activate(("campaign", "horde", "tutorial", "controls")[self.selection])
            elif key in (pg.K_c, pg.K_h, pg.K_t):
                self.start({pg.K_c: "campaign", pg.K_h: "horde", pg.K_t: "tutorial"}[key])
            elif key == pg.K_d:
                self.args.difficulty = DIFFICULTIES[(DIFFICULTIES.index(self.args.difficulty) + 1) % 4]
            elif key == pg.K_m:
                self.next_mode, self.running = "remastered", False
            elif key == pg.K_ESCAPE:
                self.running = False
        elif self.state == "play":
            if key == pg.K_ESCAPE:
                self.state = "paused"
            elif pg.K_1 <= key <= pg.K_3:
                self.pending_select = key - pg.K_1
            elif key in (pg.K_q, pg.K_LCTRL, pg.K_RCTRL, pg.K_HOME):
                self.pending_cycle = -1
            elif key in (pg.K_e, pg.K_INSERT, pg.K_PAGEUP):
                self.pending_cycle = 1
            elif key == pg.K_f:
                self.pending_dash = True
            elif key == pg.K_r:
                self.restore()
        elif self.state == "paused":
            if key == pg.K_ESCAPE:
                self.state, self.acc = "play", 0.0
            elif key == pg.K_r:
                self.restore("level_start")
            elif key == pg.K_t:
                self.check("return to title")
                self.state = "title"
            elif key == pg.K_x:
                self.running = False
        elif self.state == "dead":
            if key in (pg.K_SPACE, pg.K_r):
                self.restore("level_start" if self.game.variant == "horde" else "checkpoint")
            elif key in (pg.K_ESCAPE, pg.K_t):
                self.state = "title"
        elif self.state == "complete":
            if key in (pg.K_SPACE, pg.K_RETURN):
                if self.game.variant == "tutorial":
                    self.start("campaign")
                else:
                    self.state = "title"
            elif key == pg.K_ESCAPE:
                self.state = "title"

    def activate(self, action):
        if action == "controls":
            self.help_return, self.state = "title", "controls"
        else:
            self.start(action)

    def draw(self, dt=0.0):
        self.renderer.update_effects(dt if self.state == "play" else 0.0)
        sw, sh = self.screen.get_size()
        mx, my = pg.mouse.get_pos()
        mouse = (mx * W / sw, my * H / sh)
        if self.state == "title":
            self.buttons = self.renderer.menu(self.game, mouse, self.selection, self.args.difficulty)
        else:
            alpha = min(1, self.acc / TICK) if self.state == "play" else 1
            self.renderer.render(self.game, alpha, self.message if self.message_ticks else "")
            if self.state == "paused":
                self.renderer.overlay("SIMULATION PAUSED", ["Esc resume / F1 or C controls",
                                                            "R restart level / T title / X quit"])
            elif self.state == "dead":
                detail = (f"{self.game.cleared} waves cleared / {self.game.kills} kills"
                          if self.game.variant == "horde" else "Your relay checkpoint is ready.")
                self.renderer.overlay("SIGNAL LOST", [detail, "Space restart / Esc title"])
            elif self.state == "complete":
                tutorial = self.game.variant == "tutorial"
                self.renderer.overlay("TRAINING COMPLETE" if tutorial else "CORE RECLAIMED",
                                      ["You are ready to breach the grid." if tutorial else
                                       f"{self.game.frames // 15}s / {self.game.kills} kills / "
                                       f"{self.game.dashes} dashes",
                                       "Enter / Space: campaign" if tutorial else "Enter / Space: title"])
        if self.state == "controls":
            draw_controls(self.renderer.surface, "neon")
        if self.state == "play":
            pg.draw.circle(self.renderer.surface, CYAN, (round(mouse[0]), round(mouse[1])), 7, 1)
            pg.draw.line(self.renderer.surface, CYAN, (mouse[0] - 11, mouse[1]), (mouse[0] - 4, mouse[1]))
            pg.draw.line(self.renderer.surface, CYAN, (mouse[0] + 4, mouse[1]), (mouse[0] + 11, mouse[1]))
        pg.transform.scale(self.renderer.surface, self.screen.get_size(), self.screen)
        pg.display.flip()

    def run(self):
        frames = 0
        while self.running:
            dt = self.clock.tick(60) / 1000
            for e in pg.event.get():
                if e.type == pg.QUIT:
                    self.running = False
                elif e.type == pg.KEYDOWN:
                    self.on_key(e.key)
                elif e.type == pg.MOUSEBUTTONDOWN:
                    if self.state == "title" and e.button == 1:
                        sw, sh = self.screen.get_size()
                        pos = (e.pos[0] * W / sw, e.pos[1] * H / sh)
                        for action, rect in self.buttons:
                            if rect.collidepoint(pos):
                                self.activate(action)
                                break
                    elif self.state == "play" and e.button == 2:
                        self.pending_cycle = -1
                elif e.type == pg.MOUSEWHEEL and self.state == "play":
                    self.pending_cycle = -1 if e.y > 0 else 1
                elif e.type == pg.JOYDEVICEADDED and self.joystick is None:
                    self.joystick = pg.joystick.Joystick(e.device_index)
                    self.joy_rest = [self.joystick.get_axis(i) for i in range(self.joystick.get_numaxes())]
                elif e.type == pg.JOYDEVICEREMOVED:
                    self.joystick, self.joy_rest = None, []
                elif e.type == pg.JOYBUTTONDOWN and self.state == "play":
                    if e.button == 2:
                        self.pending_dash = True
                    elif e.button in (4, 5):
                        self.pending_cycle = -1 if e.button == 4 else 1
            self.advance(TICK / 2 if self.args.frames else dt)
            self.draw(dt)
            frames += 1
            if self.args.frames and frames >= self.args.frames:
                self.running = False
        if self.args.screenshot:
            pg.image.save(self.screen, str(self.args.screenshot))
        self.close_trace()
        pg.quit()
        return 0
