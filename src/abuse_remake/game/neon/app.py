"""Playable Neon Protocol: title, campaign, Horde, training, field manual. Input and drawing only.

The simulation (engine/neon) runs at 30 ticks a second; drawing runs at the display rate and
interpolates. Sessions can be recorded (``--record``) as ``neon-trace-2`` and replayed by
``abuse-replay --human-trace``, which checks every recorded state hash.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import pygame as pg

from ...engine.neon import DIFFICULTIES, NeonGame, NeonInput
from ...engine.neon.horde import UPGRADES
from ...engine.neon.tilemap import LADDER, ONEWAY, SHIFT
from ..remaster import data_dir
from .hud import AMBER, CYAN, GREEN, MAGENTA, MANUAL_PAGES, RED, WHITE, H, Hud, W
from .render import SCENE_H, SCENE_W, WorldRenderer
from .sound import Sound, music_for

TICK = 1 / 30
MAX_CATCHUP = 5 * TICK
MENU = ("campaign", "horde", "training", "manual", "legacy")


def _records_path() -> Path:
    return data_dir() / "neon-records.json"


def load_records() -> dict:
    try:
        got = json.loads(_records_path().read_text())
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def save_record(key: str, value: dict, better) -> bool:
    recs = load_records()
    old = recs.get(key)
    if old is not None and not better(value, old):
        return False
    recs[key] = value
    try:
        _records_path().parent.mkdir(parents=True, exist_ok=True)
        _records_path().write_text(json.dumps(recs))
    except OSError:
        return False
    return True


class NeonApp:
    def __init__(self, args):
        self.args = args
        if args.frames:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pg.init()
        size = (SCENE_W * args.scale, SCENE_H * args.scale) if args.scale else (W, H)
        flags = pg.FULLSCREEN if args.fullscreen else pg.RESIZABLE
        self.screen = pg.display.set_mode(size, flags)
        pg.display.set_caption("NEON PROTOCOL")
        pg.mouse.set_visible(False)
        self.canvas = pg.Surface((W, H))
        self.renderer = WorldRenderer()
        self.hud = Hud(self.renderer.art)
        self.sound = Sound(enabled=not args.no_audio and not args.frames)
        self.clock = pg.time.Clock()
        self.seed = args.seed if args.seed is not None else int(time.time()) % 100000
        self.difficulty = args.difficulty
        self.next_mode = None
        self.running = True
        self.state = "title"
        self.back_state = "title"
        self.selection = 0
        self.page = 0
        self.buttons: list = []
        self.cards: list = []
        self.acc = 0.0
        self.pending_select = None
        self.pending_cycle = 0
        self.pending_upgrade = None
        self.joystick = None
        self.joy_rest: list[float] = []
        self.records = load_records()
        self.hints_done: set[str] = set()
        self.hint_time: dict[str, int] = {}
        self.hint = ""
        self.finish_note = ""
        self.trace = None
        self._open_trace()
        variant = "training" if getattr(args, "tutorial", False) else "horde" if args.horde else "campaign"
        self.selection = MENU.index(variant)
        self.preview = NeonGame(self.seed, "campaign", self.difficulty)
        self.game = self.preview
        self.renderer.reset(self.game)
        self.level_start = self.checkpoint = None
        if args.skip_title or args.frames:
            self.start(variant)

    # ------------------------------------------------------------ traces
    def _open_trace(self):
        path = self.args.record
        if self.args.playtest:
            path = Path("playtests/raw") / f"neon-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        if not path:
            return
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        append = getattr(self.args, "_append_trace", False) and path.exists()
        self.trace = path.open("a" if append else "w")
        if not append:
            self.write({"kind": "header", "format": "neon-trace-2", "game": "neon_protocol",
                        "player": getattr(self.args, "trace_player", "human")})

    def write(self, row):
        if self.trace:
            self.trace.write(json.dumps(row) + "\n")

    def check(self, why):
        if self.state != "title" or self.game is not self.preview:
            self.write({"kind": "check", "why": why, "state_hash": self.game.state_hash()})

    def close_trace(self):
        if self.trace:
            self.check("session end")
            self.trace.close()
            self.trace = None

    # ------------------------------------------------------------ flow
    def start(self, variant: str, sector: int = 0):
        if self.game is not self.preview:
            self.check("before new game")
        self.game = NeonGame(self.seed, variant, self.difficulty, sector)
        self.seed = (self.seed + 1) % 100000
        self.renderer.reset(self.game)
        self.level_start = self.checkpoint = self.game.snapshot()
        self.acc = 0.0
        self.pending_select, self.pending_cycle, self.pending_upgrade = None, 0, None
        self.state = "play"
        self.finish_note = ""
        g = self.game
        self.write({"kind": "new_game", "rules": "neon", "seed": g.seed, "variant": variant,
                    "difficulty": g.difficulty, "sector": g.sector})
        intro = {"campaign": f"SECTOR {g.sector + 1} · {g.map.title}", "horde": "HORDE · survive",
                 "training": "TRAINING DECK"}[variant]
        self.hud.say(intro, CYAN, 3.0)
        self.sound.ambience(True)

    def restore(self, which="checkpoint"):
        if self.checkpoint is None:
            return
        self.check(f"before restore to {which}")
        self.game.restore(self.level_start if which == "level_start" else self.checkpoint)
        if which == "level_start":
            self.checkpoint = self.level_start
        self.renderer.reset(self.game)
        self.acc = 0.0
        self.pending_select, self.pending_cycle, self.pending_upgrade = None, 0, None
        self.state = "play"
        self.hud.say("CHECKPOINT RESTORED" if which == "checkpoint" else "LEVEL RESTARTED", CYAN)
        self.write({"kind": "restore", "to": which})

    def to_title(self):
        if self.game is not self.preview:
            self.check("return to title")
        self.game = self.preview
        self.renderer.reset(self.game)
        self.state = "title"
        self.records = load_records()

    # ------------------------------------------------------------ input
    def screen_to_world(self, x, y):
        sw, sh = self.screen.get_size()
        cx, cy = self.renderer.last_camera
        return int(x * SCENE_W / sw + cx), int(y * SCENE_H / sh + cy)

    def canvas_mouse(self):
        mx, my = pg.mouse.get_pos()
        sw, sh = self.screen.get_size()
        return mx * W / sw, my * H / sh

    def read_inputs(self) -> NeonInput:
        k = pg.key.get_pressed()
        mb = pg.mouse.get_pressed(3)
        x = -1 if k[pg.K_a] or k[pg.K_LEFT] else 1 if k[pg.K_d] or k[pg.K_RIGHT] else 0
        y = -1 if k[pg.K_w] or k[pg.K_UP] else 1 if k[pg.K_s] or k[pg.K_DOWN] else 0
        px, py = self.screen_to_world(*pg.mouse.get_pos())
        jump = bool(k[pg.K_SPACE])
        fire = bool(mb[0] or k[pg.K_j])
        dash = bool(mb[2] or k[pg.K_LSHIFT] or k[pg.K_RSHIFT] or k[pg.K_f])
        interact = bool(k[pg.K_e])
        j = self.joystick
        if j is not None:
            def axis(i):
                return j.get_axis(i) - (self.joy_rest[i] if i < len(self.joy_rest) else 0) \
                    if i < j.get_numaxes() else 0.0

            if abs(axis(0)) > 0.35:
                x = 1 if axis(0) > 0 else -1
            if abs(axis(1)) > 0.6:
                y = 1 if axis(1) > 0 else -1
            nb = j.get_numbuttons()
            jump = jump or (nb > 0 and j.get_button(0))
            interact = interact or (nb > 1 and j.get_button(1))
            dash = dash or (nb > 2 and j.get_button(2))
            if j.get_numaxes() > 3 and math.hypot(axis(2), axis(3)) > 0.3:
                p = self.game.player
                sx, sy = p.shoulder()
                px, py = sx + int(axis(2) * 200), sy + int(axis(3) * 200)
            fire = fire or (j.get_numaxes() > 5 and axis(5) > 0.3)
        return NeonInput(x=x, y=y, jump=jump, fire=fire, dash=dash, interact=interact, px=px, py=py)

    def scripted_inputs(self) -> NeonInput:
        """Headless demo input for --frames runs: run, hop and shoot at the nearest hostile."""
        g = self.game
        p = g.player
        targets = [e for e in g.enemies if abs(e.cx - p.cx) < 300 and abs(e.cy - p.cy) < 200 and e.hittable()]
        t = min(targets, key=lambda e: abs(e.cx - p.cx), default=None)
        sx, sy = p.shoulder()
        px, py = (t.cx, t.cy) if t else (sx + 150, sy)
        move = 1 if g.frames % 160 < 120 else -1
        return NeonInput(x=move, jump=g.frames % 40 < 12, fire=t is not None, px=px, py=py,
                         dash=g.frames % 90 == 0)

    # ------------------------------------------------------------ simulation
    def tick(self, inp: NeonInput | None = None):
        g = self.game
        inp = inp if inp is not None else self.scripted_inputs() if self.args.frames else self.read_inputs()
        select, cycle, upgrade = self.pending_select, self.pending_cycle, self.pending_upgrade
        self.pending_select, self.pending_cycle, self.pending_upgrade = None, 0, None
        g.step(inp, select, cycle, upgrade)
        self.write({"kind": "input", "x": inp.x, "y": inp.y, "jump": int(inp.jump), "fire": int(inp.fire),
                    "dash": int(inp.dash), "interact": int(inp.interact), "px": inp.px, "py": inp.py,
                    "select": select, "cycle": cycle, "upgrade": upgrade})
        self.renderer.note_tick(g)
        self.sound.events(g)
        for e in g.events:
            self._message(e)
        self._hints()
        if g.horde is not None and g.horde.offer and self.state == "play":
            self.state = "upgrade"
        if g.status == "dead":
            self.state = "dead"
            self.check("dead")
            if g.variant == "horde":
                h = g.horde
                new = save_record("horde", {"cleared": h.cleared, "kills": g.kills},
                                  lambda a, b: (a["cleared"], a["kills"]) > (b["cleared"], b["kills"]))
                self.finish_note = "NEW BEST" if new else ""
        elif g.status == "won":
            self.state = "complete"
            self.check("won")
            if g.variant == "campaign":
                new = save_record("campaign", {"frames": g.frames, "kills": g.kills},
                                  lambda a, b: a["frames"] < b["frames"])
                self.finish_note = "NEW BEST TIME" if new else ""
            self.sound.music(None)

    def _message(self, e):
        k = e["kind"]
        say = self.hud.say
        if k == "checkpoint":
            self.checkpoint = self.game.snapshot()
            say("CHECKPOINT SAVED · systems restored", GREEN)
        elif k == "sector_start":
            # the new sector's start is both the checkpoint and where "restart sector" goes
            self.checkpoint = self.level_start = self.game.snapshot()
            say(f"SECTOR {self.game.sector + 1} · {e['title']}", CYAN, 3.5)
        elif k == "sector_clear":
            say(f"{e['title']} CLEARED", GREEN, 3)
        elif k == "pickup":
            name = e["pickup"]
            if name.startswith("weapon"):
                from ...engine.neon.weapons import WEAPONS

                say(f"{WEAPONS[int(name[6:])].name} ACQUIRED · press {int(name[6:]) + 1}", MAGENTA, 3)
            else:
                text = {"health": "+30 INTEGRITY", "ammo": "AMMO CELLS", "shield": "SHIELD ONLINE",
                        "overcharge": "OVERCHARGE · double damage", "haste": "HASTE", "phase": "PHASE DRIVE",
                        "boots": "VAULT BOOTS · press jump again in mid-air", "key_red": "RED KEYCARD",
                        "key_gold": "GOLD KEYCARD"}.get(name, name.upper())
                say(text, AMBER)
        elif k == "locked":
            say("LOCKED · destroy the Core Warden" if e.get("why") == "boss" else
                f"LOCKED · needs the {e.get('key', '').upper()} keycard", RED)
        elif k == "alarm":
            say("ALARM · the vents are opening", RED)
        elif k == "wave":
            say(f"WAVE {e['wave']} · {e['size']} hostiles", AMBER, 2.5)
        elif k == "upgrade":
            say(f"UPGRADE · {UPGRADES[e['upgrade']][0]}", AMBER)
        elif k == "boss_phase":
            say("THE WARDEN IS ENRAGED" if e["phase"] == 2 else "OVERLOAD · watch the laser", RED, 3)
        elif k == "boss_wake":
            say("THE CORE WARDEN WAKES", RED, 3)
        elif k == "boss_dead":
            say("CORE WARDEN DESTROYED · get to the exit", GREEN, 4)
        elif k == "lesson":
            say(f"✓ {e['name']}", GREEN, 1.8)
        elif k == "empty":
            say("OUT OF AMMO · 1 for the pulse carbine", RED, 1.5)
        elif k == "door_open" and self.game.variant == "campaign":
            pass

    def _hints(self):
        g = self.game
        p = g.player
        self.hint = ""
        if g.variant != "campaign" or p.dying:
            return
        grid = g.grid
        tx = p.cx >> SHIFT

        def show(key, text):
            if key not in self.hints_done:
                self.hint_time[key] = self.hint_time.get(key, 0) + 1
                if self.hint_time[key] > 210:  # 7 s of play is enough
                    self.hints_done.add(key)
                    return False
                self.hint = text
                return True
            return False

        if p.climbing:
            self.hints_done.add("ladder")
        if any(e["kind"] == "drop" for e in g.events):
            self.hints_done.add("drop")
        if any(e["kind"] == "dash" for e in g.events):
            self.hints_done.add("dash")
        if p.crouching:
            self.hints_done.add("crouch")
        near_ladder = any(grid.at(tx, (p.bottom >> SHIFT) + d) == LADDER for d in (-2, -1, 0, 1))
        if near_ladder and show("ladder", "W / S  climb the ladder"):
            return
        on_ledge = grid.at(tx, p.bottom >> SHIFT) == ONEWAY and p.grounded
        if on_ledge and show("drop", "S + SPACE  drop through the grating"):
            return
        if p.hp < 35 and show("lowhp", "Low integrity · find a + cell or a save console (E)"):
            return
        if sum(g.owned) > 1 and show("weapons", "1-5, Q or the mouse wheel switch weapons"):
            return
        if g.frames > 300 and show("dash", "SHIFT / F / right click  dash · you cannot be hurt mid-dash"):
            return

    def advance(self, dt):
        if self.state != "play":
            return
        self.acc = min(self.acc + dt, MAX_CATCHUP)
        while self.acc >= TICK and self.state == "play":
            self.acc -= TICK
            self.tick()

    # ------------------------------------------------------------ keys
    def on_key(self, key):
        s = self.state
        if key in (pg.K_MINUS, pg.K_KP_MINUS):
            self.hud.say(f"VOLUME {int(self.sound.set_volume(-0.1) * 100)}%", WHITE, 1)
            return
        if key in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS):
            self.hud.say(f"VOLUME {int(self.sound.set_volume(0.1) * 100)}%", WHITE, 1)
            return
        if s == "manual":
            if key in (pg.K_ESCAPE, pg.K_F1):
                self.state = self.back_state
                self.acc = 0.0
            elif key in (pg.K_RIGHT, pg.K_d, pg.K_TAB):
                self.page = (self.page + 1) % len(MANUAL_PAGES)
            elif key in (pg.K_LEFT, pg.K_a):
                self.page = (self.page - 1) % len(MANUAL_PAGES)
            elif pg.K_1 <= key <= pg.K_4:
                self.page = key - pg.K_1
            return
        if s == "map":
            if key in (pg.K_TAB, pg.K_ESCAPE, pg.K_m):
                self.state, self.acc = "play", 0.0
            return
        if key == pg.K_F1 and s in ("title", "play", "paused"):
            self.back_state = "paused" if s == "play" else s
            self.state = "manual"
            self.sound.play("select", 0.6)
            return
        if s == "title":
            if key in (pg.K_UP, pg.K_w):
                self.selection = (self.selection - 1) % len(MENU)
                self.sound.play("click", 0.5)
            elif key in (pg.K_DOWN, pg.K_s):
                self.selection = (self.selection + 1) % len(MENU)
                self.sound.play("click", 0.5)
            elif key in (pg.K_RETURN, pg.K_SPACE, pg.K_KP_ENTER):
                self.activate(MENU[self.selection])
            elif key == pg.K_c:
                self.activate("campaign")
            elif key == pg.K_h:
                self.activate("horde")
            elif key == pg.K_t:
                self.activate("training")
            elif key == pg.K_d:
                self.difficulty = DIFFICULTIES[(DIFFICULTIES.index(self.difficulty) + 1) % len(DIFFICULTIES)]
                self.sound.play("switch", 0.6)
            elif key == pg.K_m:
                self.activate("legacy")
            elif key == pg.K_ESCAPE:
                self.running = False
        elif s == "play":
            if key == pg.K_ESCAPE:
                self.state = "paused"
                self.sound.play("back", 0.5)
            elif pg.K_1 <= key <= pg.K_5:
                self.pending_select = key - pg.K_1
            elif key == pg.K_q:
                self.pending_cycle = -1
            elif key == pg.K_TAB:
                self.state = "map"
            elif key == pg.K_r:
                self.restore()
            elif key == pg.K_l:
                self.renderer.lighting = not self.renderer.lighting
        elif s == "upgrade":
            if key in (pg.K_1, pg.K_KP1):
                self.choose(0)
            elif key in (pg.K_2, pg.K_KP2):
                self.choose(1)
        elif s == "paused":
            if key == pg.K_ESCAPE:
                self.state, self.acc = "play", 0.0
            elif key == pg.K_r:
                self.restore()
            elif key == pg.K_n:
                self.restore("level_start")
            elif key == pg.K_t:
                self.to_title()
            elif key == pg.K_x:
                self.running = False
        elif s == "dead":
            if key in (pg.K_SPACE, pg.K_RETURN, pg.K_r):
                if self.game.variant == "horde":
                    self.start("horde")
                else:
                    self.restore()
            elif key in (pg.K_ESCAPE, pg.K_t):
                self.to_title()
        elif s == "complete":
            if key in (pg.K_SPACE, pg.K_RETURN):
                if self.game.variant == "training":
                    self.start("campaign")
                else:
                    self.to_title()
            elif key == pg.K_ESCAPE:
                self.to_title()

    def choose(self, i):
        self.pending_upgrade = i
        self.state = "play"
        self.sound.play("power", 0.8)
        self.tick(NeonInput(px=self.game.player.cx + 100, py=self.game.player.cy))

    def activate(self, action):
        self.sound.play("confirm", 0.7)
        if action == "manual":
            self.back_state, self.state = "title", "manual"
        elif action == "legacy":
            self.next_mode, self.running = "remastered", False
        else:
            self.start(action)

    # ------------------------------------------------------------ drawing
    def draw(self, dt=0.0):
        g = self.game
        title = self.state == "title"
        if title:
            t = self.hud.time
            span = max(1, g.width - SCENE_W)
            self.renderer.cam = (span * (0.5 + 0.5 * math.sin(t * 0.03)) * 0.4, max(0, g.player.cy - 220))
        else:
            self.renderer.update(dt if self.state == "play" else 0.0, g)
        self.renderer.time += dt if title else 0
        self.hud.update(dt)
        alpha = min(1.0, self.acc / TICK) if self.state == "play" else 1.0
        scene = self.renderer.render(g, alpha)
        pg.transform.scale(scene, (W, H), self.canvas)
        mouse = self.canvas_mouse()
        if title:
            self.buttons = self.hud.title(self.canvas, self.selection, self.difficulty, mouse, self.records)
        else:
            self.hud.draw(self.canvas, g, self.hint)
            if g.transition:
                k = 1 - abs(g.transition - 25) / 25
                self.hud.shade(self.canvas, int(255 * k))
                self.hud.text(self.canvas, "SECTOR CLEARED", (W // 2, H // 2 - 40), GREEN, self.hud.h1, "midtop",
                              glow=True)
        if self.state == "paused":
            self.hud.center(self.canvas, "PAUSED", ["ESC resume", "R last checkpoint  ·  N restart sector",
                                                    "F1 field manual  ·  T title  ·  X quit",
                                                    "−/= volume  ·  TAB map  ·  L lighting"])
        elif self.state == "manual":
            self.hud.manual(self.canvas, self.page)
        elif self.state == "map":
            self.hud.automap(self.canvas, g, self.renderer.explored)
        elif self.state == "upgrade" and g.horde is not None:
            self.cards = self.hud.upgrade_cards(self.canvas, g.horde.offer, mouse)
        elif self.state == "dead":
            if g.variant == "horde":
                h = g.horde
                self.hud.center(self.canvas, "SIGNAL LOST", [f"Waves cleared {h.cleared}  ·  kills {g.kills}",
                                                             self.finish_note, "SPACE new run  ·  ESC title"], RED)
            else:
                self.hud.center(self.canvas, "SIGNAL LOST", ["Your last checkpoint is ready.",
                                                             "SPACE / R restore  ·  ESC title"], RED)
        elif self.state == "complete":
            if g.variant == "training":
                self.hud.center(self.canvas, "TRAINING COMPLETE", ["You know every move. Time to breach.",
                                                                   "ENTER start the campaign  ·  ESC title"], GREEN)
            else:
                secs = g.frames // 30
                self.hud.center(self.canvas, "PROTOCOL COMPLETE",
                                [f"time {secs // 60}:{secs % 60:02d}  ·  kills {g.kills}  ·  secrets {g.secrets}",
                                 f"damage taken {g.damage_taken}  ·  dashes {g.dashes}", self.finish_note,
                                 "ENTER title"], GREEN)
        if self.state in ("play",):
            self._crosshair(mouse)
        elif self.state not in ("play",):
            self._pointer(mouse)
        if self.screen.get_size() == (W, H):
            self.screen.blit(self.canvas, (0, 0))
        else:
            pg.transform.smoothscale(self.canvas, self.screen.get_size(), self.screen)
        pg.display.flip()
        if title:
            self.sound.music("menu")
            self.sound.ambience(False)
        elif self.state in ("play", "paused", "map", "upgrade"):
            p = g.player
            combat = any(e.alerted and abs(e.cx - p.cx) < 520 and abs(e.cy - p.cy) < 360 and e.kind != "nest"
                         for e in g.enemies)
            self.sound.music(music_for(g, combat))
        self.sound.tick(dt)
        if self.state == "play":
            self.sound.footsteps(g, dt)

    def _crosshair(self, pos):
        x, y = pos
        c = self.canvas
        col = (120, 240, 255)
        pg.draw.circle(c, col, (round(x), round(y)), 11, 1)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pg.draw.line(c, col, (x + dx * 6, y + dy * 6), (x + dx * 16, y + dy * 16), 2)
        c.fill(WHITE, (round(x) - 1, round(y) - 1, 2, 2))

    def _pointer(self, pos):
        x, y = pos
        pg.draw.polygon(self.canvas, CYAN, [(x, y), (x + 14, y + 6), (x + 6, y + 14)])

    # ------------------------------------------------------------ loop
    def run(self):
        frames = 0
        while self.running:
            dt = self.clock.tick(60) / 1000
            for e in pg.event.get():
                self.handle(e)
            self.advance(TICK if self.args.frames else dt)
            self.draw(1 / 60 if self.args.frames else dt)
            frames += 1
            if self.args.frames and frames >= self.args.frames:
                self.running = False
        if self.args.screenshot:
            pg.image.save(self.screen, str(self.args.screenshot))
        self.close_trace()
        self.sound.stop()
        pg.quit()
        return 0

    def handle(self, e):
        if e.type == pg.QUIT:
            self.running = False
        elif e.type == pg.KEYDOWN:
            self.on_key(e.key)
        elif e.type == pg.MOUSEBUTTONDOWN:
            pos = self.canvas_mouse()
            if self.state == "title" and e.button == 1:
                for action, rect in self.buttons:
                    if rect.collidepoint(pos):
                        self.activate(action)
                        break
            elif self.state == "upgrade" and e.button == 1:
                for i, rect in self.cards:
                    if rect.collidepoint(pos):
                        self.choose(i)
                        break
            elif self.state == "play" and e.button == 2:
                self.pending_cycle = 1
        elif e.type == pg.MOUSEWHEEL and self.state == "play":
            self.pending_cycle = -1 if e.y > 0 else 1
        elif e.type == pg.JOYDEVICEADDED and self.joystick is None:
            self.joystick = pg.joystick.Joystick(e.device_index)
            self.joy_rest = [self.joystick.get_axis(i) for i in range(self.joystick.get_numaxes())]
        elif e.type == pg.JOYDEVICEREMOVED:
            self.joystick, self.joy_rest = None, []
        elif e.type == pg.JOYBUTTONDOWN:
            if self.state == "play" and e.button in (4, 5):
                self.pending_cycle = -1 if e.button == 4 else 1
            elif self.state == "play" and e.button == 7:
                self.state = "paused"
            elif self.state == "paused" and e.button == 7:
                self.state = "play"
            elif self.state == "title" and e.button == 0:
                self.activate(MENU[self.selection])
            elif self.state == "upgrade" and e.button in (0, 1):
                self.choose(e.button)
            elif self.state in ("dead", "complete") and e.button == 0:
                self.on_key(pg.K_SPACE)
        elif e.type == pg.VIDEORESIZE and not self.args.fullscreen:
            self.screen = pg.display.set_mode((max(640, e.w), max(360, e.h)), pg.RESIZABLE)

