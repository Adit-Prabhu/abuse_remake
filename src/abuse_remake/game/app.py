"""``abuse-remake``: play Level 1.

Rules run at a fixed 15 Hz, as in the original; drawing runs at the display rate with
interpolation in between. Classic mode shows the original 311x151 view; Remastered mode shows
a wider 16:9 view with modern effects (and, from milestone 8, the Remastered-only mechanics).

Controls (original defaults, plus modern ones):
  move A/D or arrows; jump W, Up or Space; action (switches, doors, consoles, exit) S or Down
  aim with the mouse; fire left button (or J); special right button (or Shift)
  weapons 1-4, Q/E or the mouse wheel; pause Esc; gamepad: left stick move, right stick aim,
  A jump, B action, right trigger fire, bumpers switch weapon
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

from ..engine.game import Game, WeaponCommand
from ..engine.view import VIEW_H, VIEW_W, Inputs
from ..engine.world import DIFFICULTIES

TICK = 1.0 / 15.0


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="abuse-remake", description="Abuse (1996), Level 1, rebuilt")
    p.add_argument("--mode", choices=("classic", "remastered"), default="remastered")
    p.add_argument("--difficulty", choices=DIFFICULTIES, default="hard")
    p.add_argument("--seed", type=int, default=None, help="random table start (default: from the clock)")
    p.add_argument("--scale", type=int, default=0, help="window scale (default: fit the screen)")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--record", type=Path, help="write this session's inputs as a replayable trace")
    p.add_argument("--playtest", action="store_true", help="record into playtests/raw/ with a session id")
    p.add_argument("--skip-title", action="store_true")
    p.add_argument("--frames", type=int, default=0, help="run N display frames with scripted input, then exit")
    p.add_argument("--screenshot", type=Path, help="save the last frame (with --frames)")
    return p.parse_args(argv)


class App:
    def __init__(self, args):
        import pygame

        self.pg = pygame
        self.args = args
        if args.frames:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pygame.init()
        self.modern = args.mode == "remastered"
        self.view_w, self.view_h = (480, 270) if self.modern else (VIEW_W, VIEW_H)
        info = pygame.display.Info()
        scale = args.scale or max(2, min((info.current_w or 1600) // self.view_w,
                                         ((info.current_h or 900) - 80) // self.view_h))
        self.scale = scale
        flags = pygame.FULLSCREEN if args.fullscreen else 0
        self.screen = pygame.display.set_mode((self.view_w * scale, self.view_h * scale), flags)
        pygame.display.set_caption("Abuse — Level 1 (remake)")
        from .audio import Audio
        from .hud import Hud
        from .particles import Particles
        from .render import Renderer
        from .sprites import SpriteCache

        self.sprites = SpriteCache()
        self.audio = Audio(enabled=not args.no_audio and not args.frames)
        self.hud = Hud()
        self.particles = Particles()
        self.seed = args.seed if args.seed is not None else int(time.time()) % 1024
        self.Renderer = Renderer
        self.joystick = None
        self.clock = pygame.time.Clock()
        self.state = "play" if (args.skip_title or args.frames) else "title"
        self.trace = None
        self.new_game()

    # --- game lifecycle ---
    def new_game(self):
        self.game = Game(seed=self.seed, difficulty=self.args.difficulty)
        self.renderer = self.Renderer(self.game, self.sprites, self.view_w, self.view_h)
        self.renderer.modern = self.modern
        self.game.world.globals["save_hook"] = self._on_console_save
        self.level_start = self.game.snapshot()
        self.checkpoint = self.level_start
        self.stats = {"ticks": 0, "kills": 0, "secrets": 0, "deaths": 0, "shots": 0, "damage_taken": 0}
        self.acc = 0.0
        self.pending_weapon: WeaponCommand | None = None
        self._open_trace()

    def _open_trace(self):
        path = self.args.record
        if self.args.playtest:
            sid = time.strftime("%Y%m%d-%H%M%S")
            path = Path("playtests/raw") / f"session-{sid}.jsonl"
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.trace = open(path, "w")  # noqa: SIM115 - closed on exit
        self.trace.write(json.dumps({"kind": "header", "game": "abuse_remake", "level": "level01",
                                     "seed": self.seed, "difficulty": self.args.difficulty,
                                     "mode": self.args.mode, "player": "human"}) + "\n")

    def _on_console_save(self, console):
        # restart_ai calls this with the player's health already set for the save
        self.checkpoint = self.game.snapshot()
        self.hud.say("Station secured!")

    # --- input ---
    def read_inputs(self) -> Inputs:
        pg = self.pg
        keys = pg.key.get_pressed()
        mb = pg.mouse.get_pressed(3)
        x = (1 if keys[pg.K_d] or keys[pg.K_RIGHT] else 0) - (1 if keys[pg.K_a] or keys[pg.K_LEFT] else 0)
        up = keys[pg.K_w] or keys[pg.K_UP] or keys[pg.K_SPACE]
        down = keys[pg.K_s] or keys[pg.K_DOWN]
        y = -1 if up else (1 if down else 0)
        fire = mb[0] or keys[pg.K_j]
        special = mb[2] or keys[pg.K_LSHIFT]
        mx, my = pg.mouse.get_pos()
        px, py = self.screen_to_game(mx, my)
        if self.joystick is not None:
            j = self.joystick
            ax = j.get_axis(0)
            if abs(ax) > 0.35:
                x = 1 if ax > 0 else -1
            if j.get_numbuttons() > 0 and j.get_button(0):
                y = -1
            if j.get_numbuttons() > 1 and j.get_button(1):
                y = 1
            if j.get_numaxes() > 4:
                rx, ry = j.get_axis(2), j.get_axis(3)
                if math.hypot(rx, ry) > 0.3:
                    p = self.game.player
                    px, py = p.x + int(rx * 120), p.y - 20 + int(ry * 120)
                if j.get_numaxes() > 5 and j.get_axis(5) > 0.3:
                    fire = True
        return Inputs(x=x, y=y, b1=int(special), b2=int(fire), pointer_x=px, pointer_y=py)

    def screen_to_game(self, sx, sy):
        xoff, yoff = self.renderer.camera(1.0)
        return int(sx / self.scale + xoff), int(sy / self.scale + yoff)

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
                if ev.type == pg.QUIT:
                    running = False
                elif ev.type == pg.JOYDEVICEADDED and self.joystick is None:
                    self.joystick = pg.joystick.Joystick(ev.device_index)
                elif ev.type == pg.KEYDOWN:
                    running = self.on_key(ev.key) and running
                elif ev.type == pg.MOUSEWHEEL and self.state == "play":
                    self.pending_weapon = WeaponCommand(cycle=-1 if ev.y > 0 else 1)
                elif ev.type == pg.JOYBUTTONDOWN and self.state == "play" and ev.button in (4, 5):
                    self.pending_weapon = WeaponCommand(cycle=-1 if ev.button == 4 else 1)
            if self.state == "play":
                self.acc += dt if not self.args.frames else TICK / 2
                while self.acc >= TICK:
                    self.acc -= TICK
                    self.tick(frames)
            self.draw()
            frames += 1
            if self.args.frames and frames >= self.args.frames:
                running = False
        if self.args.screenshot:
            pg.image.save(self.screen, str(self.args.screenshot))
        if self.trace:
            self.trace.close()
        pg.quit()
        return 0

    def on_key(self, key) -> bool:
        pg = self.pg
        if self.state == "title":
            if key in (pg.K_RETURN, pg.K_SPACE):
                self.state = "play"
            elif key == pg.K_m:
                self.args.mode = "classic" if self.modern else "remastered"
                self.__init__(self.args)
                self.state = "title"
            elif key == pg.K_d:
                i = DIFFICULTIES.index(self.args.difficulty)
                self.args.difficulty = DIFFICULTIES[(i + 1) % len(DIFFICULTIES)]
                self.new_game()
            elif key == pg.K_ESCAPE:
                return False
        elif self.state == "play":
            if key == pg.K_ESCAPE:
                self.state = "paused"
            elif pg.K_1 <= key <= pg.K_7:
                self.pending_weapon = WeaponCommand(select=key - pg.K_1)
            elif key == pg.K_q:
                self.pending_weapon = WeaponCommand(cycle=-1)
            elif key == pg.K_e:
                self.pending_weapon = WeaponCommand(cycle=1)
            elif key == pg.K_l:
                self.renderer.lighting = not self.renderer.lighting
        elif self.state == "paused":
            if key == pg.K_ESCAPE:
                self.state = "play"
            elif key == pg.K_r:
                self.game.restore(self.level_start)
                self._rebind()
                self.state = "play"
            elif key == pg.K_x:
                return False
        elif self.state == "dead":
            if key in (pg.K_SPACE, pg.K_RETURN):
                self.game.restore(self.checkpoint)  # the original reloads the last save
                self._rebind()
                self.state = "play"
        elif self.state == "complete":
            if key in (pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE):
                self.seed = (self.seed + 1) % 1024
                self.new_game()
                self.state = "title"
        return True

    def _rebind(self):
        self.renderer.game = self.game
        self.game.world.globals["save_hook"] = self._on_console_save
        self.particles.items.clear()

    def tick(self, frame_no):
        inp = self.scripted_inputs(self.stats["ticks"]) if self.args.frames else self.read_inputs()
        weapon, self.pending_weapon = self.pending_weapon, None
        hp_before = self.game.player.hp
        self.game.step(inp, weapon)
        self.stats["ticks"] += 1
        w = self.game.world
        for e in w.events:
            if e.kind == "enemy_killed":
                self.stats["kills"] += 1
            elif e.kind == "wall_destroyed":
                self.stats["secrets"] += 1
            elif e.kind == "sound" and e.data["name"] == "ZAP_SND":
                self.stats["shots"] += 1
        self.stats["damage_taken"] += max(0, hp_before - self.game.player.hp)
        self.renderer.note_events(w.events)
        if self.modern:
            self.particles.on_events(w.events)
        self.audio.play_events(w.events, self.game.player.x, self.game.player.y)
        if self.trace:
            rec = {"tick": self.stats["ticks"], "x": inp.x, "y": inp.y, "b1": inp.b1, "b2": inp.b2,
                   "px": inp.pointer_x, "py": inp.pointer_y}
            if weapon is not None:
                rec["weapon"] = {"select": weapon.select, "cycle": weapon.cycle}
            self.trace.write(json.dumps(rec) + "\n")
        if self.game.player.aistate >= 3:
            self.stats["deaths"] += 1
            self.state = "dead"
        if w.globals.get("level_complete"):
            self.state = "complete"

    def draw(self):
        pg = self.pg
        alpha = min(1.0, self.acc / TICK) if self.state == "play" else 1.0
        surf = self.renderer.render(alpha)
        if self.modern:
            self.particles.step(0.25)
            xoff, yoff = self.renderer.camera(alpha)
            self.particles.draw(surf, xoff, yoff)
        pg.transform.scale(surf, self.screen.get_size(), self.screen)
        if self.state in ("play", "paused", "dead", "complete"):
            self.hud.draw(self.screen, self.game, self.stats)
        if self.state == "play":
            mx, my = pg.mouse.get_pos()
            pg.draw.circle(self.screen, (255, 80, 80), (mx, my), 9, 1)
            pg.draw.line(self.screen, (255, 80, 80), (mx - 13, my), (mx - 5, my))
            pg.draw.line(self.screen, (255, 80, 80), (mx + 5, my), (mx + 13, my))
        if self.state == "title":
            self.hud.center(self.screen, ["ABUSE", "Level 1 — reconstructed",
                                          f"Mode: {self.args.mode} (M)    Difficulty: {self.args.difficulty} (D)",
                                          "Enter to start    Esc to quit"],
                            "Original game © 1996 Crack dot Com (public-domain code and shareware data)")
        elif self.state == "paused":
            self.hud.center(self.screen, ["PAUSED", "Esc resume    R restart level    X quit"])
        elif self.state == "dead":
            self.hud.center(self.screen, ["YOU DIED", "Space to restart from the last save"])
        elif self.state == "complete":
            s = self.stats
            t = s["ticks"] // 15
            self.hud.center(self.screen, ["LEVEL COMPLETE", f"time {t // 60}:{t % 60:02d}",
                                          f"kills {s['kills']}   secrets {s['secrets']}   deaths {s['deaths']}",
                                          "Enter to continue"])
        pg.display.flip()


def main(argv=None) -> int:
    args = parse_args(argv)
    return App(args).run()


if __name__ == "__main__":
    sys.exit(main())
