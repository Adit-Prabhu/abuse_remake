"""``abuse-replay``: watch an agent play, or replay a trace, on screen or into a video.

    uv run abuse-replay --player scripted --scenario level01-cp3 --seed 0          # watch live
    uv run abuse-replay --trace evidence/traces/offline-v2/scripted-level01-cp3-s0.jsonl
    uv run abuse-replay --trace runs/x.jsonl --video evidence/video/demo.mp4 --headless

The game runs under Classic rules through the same ``AbuseEpisode`` the evaluation uses. A
side panel shows what the player was given and what it chose: the decision, the action and its
result, the player's note, health and ammo, the objects it could see, and for model players the
tokens and latency. The object named by the current action is outlined in the view.

A trace replays deterministically: same scenario, seed and actions give the same game. The
replay checks every step's observation hash, that every step in the trace was replayed, and that
the final outcome (status, reason, score, ticks, decisions, invalid actions) matches the trace's.
An episode the runner ended early (a token, wall-clock or player-failure stop) is ended the same
way when the trace's steps run out. Exit status: 0 for a full match, 1 for any mismatch, 2 when
the replay was stopped before the end.

The spectator is a runner. Watching a live player, it enforces the same budgets and fatal-error
stops as ``abuse-agent`` (``runner.stop_reason``), and it checks a model player's setup first.
Players still get only observations and legal actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from ..agent.interface import PLAYER_ID, SCENARIOS, AbuseEpisode, Budgets
from ..agent.runner import add_usage, make_player, new_usage, stop_reason
from ..engine.view import VIEW_H, VIEW_W

PANEL_W = 380
FPS_PER_TICK = 2  # frames drawn per 15 Hz tick (30 fps video, interpolated)
OUTCOME_KEYS = ("status", "reason", "score", "ticks", "decisions", "invalid_actions")
RUNNER_STOPS = ("token budget exhausted", "wall-clock budget exhausted", "player failed")


class TracePlayer:
    """Plays back the actions recorded in a trace."""

    def __init__(self, path: Path):
        rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
        if not rows or rows[0].get("kind") != "header":
            raise SystemExit(f"{path}: not an abuse-agent trace (no header row)")
        self.header = rows[0]
        self.steps = [r for r in rows if r.get("kind") == "step"]
        self.outcome = next((r for r in rows if r.get("kind") == "outcome"), None)
        self.i = 0

    def start(self, info):
        pass

    def end(self, outcome):
        pass

    def decide(self, observation, legal_actions):
        if self.i >= len(self.steps):
            return {"action": None, "error": "trace ended", "trace_ended": True}
        r = self.steps[self.i]
        self.i += 1
        return {"action": r.get("action"), "note": r.get("note") or "", "meta": r.get("meta") or {},
                "expect_sha": r.get("obs_sha")}


def obs_sha(obs: dict) -> str:
    return hashlib.sha256(json.dumps(obs, sort_keys=True).encode()).hexdigest()[:16]


class Spectator:
    def __init__(self, ep: AbuseEpisode, player, label: str, scale: int = 3, headless: bool = False,
                 video: Path | None = None, speed: float = 1.0, max_frames: int = 0):
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame

        from .render import Renderer
        from .sprites import SpriteCache

        self.pg = pygame
        pygame.init()
        self.ep, self.player, self.label = ep, player, label
        self.scale = scale
        self.size = (VIEW_W * scale + PANEL_W, VIEW_H * scale)
        self.size = (self.size[0] + self.size[0] % 2, self.size[1] + self.size[1] % 2)  # even, for video
        self.screen = pygame.display.set_mode(self.size) if not headless else pygame.Surface(self.size)
        if not headless:
            pygame.display.set_caption(f"Abuse remake: spectating {label}")
        self.renderer = Renderer(ep._game, SpriteCache(), VIEW_W, VIEW_H)
        self.renderer.modern = False
        self.font = pygame.font.Font(None, 22)
        self.small = pygame.font.Font(None, 19)
        self.clock = pygame.time.Clock()
        self.headless = headless
        self.speed = speed
        self.max_frames = max_frames
        self.frames = 0
        self.quit = False
        self.info: dict = {"decision": 0, "action": None, "note": "", "result": "", "meta": {}, "visible": [],
                           "tokens_in": 0, "tokens_out": 0, "replay_ok": None, "mismatches": 0, "checked": 0}
        self.ffmpeg = None
        if video is not None:
            if not shutil.which("ffmpeg"):
                raise SystemExit("--video needs ffmpeg on PATH")
            video.parent.mkdir(parents=True, exist_ok=True)
            self.ffmpeg = subprocess.Popen(
                ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                 "-s", f"{self.size[0]}x{self.size[1]}", "-r", str(15 * FPS_PER_TICK), "-i", "-",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(video)], stdin=subprocess.PIPE)
        ep.on_tick = self.on_tick

    # --- drawing ---------------------------------------------------------------------------
    def on_tick(self) -> None:
        for k in range(1, FPS_PER_TICK + 1):
            self.frame(k / FPS_PER_TICK)

    def frame(self, alpha: float = 1.0) -> None:
        pg = self.pg
        if not self.headless:
            for ev in pg.event.get():
                if ev.type == pg.QUIT or (ev.type == pg.KEYDOWN and ev.key == pg.K_ESCAPE):
                    self.quit = True
        surf = self.renderer.render(alpha)
        view = pg.transform.scale(surf, (VIEW_W * self.scale, VIEW_H * self.scale))
        self.screen.fill((14, 14, 20))
        self.screen.blit(view, (0, 0))
        self._outline_target(alpha)
        self._panel()
        if self.ffmpeg is not None:
            self.ffmpeg.stdin.write(pg.image.tobytes(self.screen, "RGB"))
        if not self.headless:
            pg.display.flip()
            self.clock.tick(15 * FPS_PER_TICK * self.speed)
        self.frames += 1
        if self.max_frames and self.frames >= self.max_frames:
            self.quit = True

    def _outline_target(self, alpha: float) -> None:
        act = self.info["action"]
        if not isinstance(act, str) or len(act.split()) != 2 or act.split()[0] not in ("attack", "goto", "use"):
            return
        label = act.split()[1]
        uid = next((u for u, lab in self.ep._ids.labels.items() if lab == label), None)
        obj = next((o for o in self.ep._game.world.objects if o.uid == uid and not o.deleted), None)
        if obj is None:
            return
        xoff, yoff = self.renderer.camera(alpha)
        x1, y1, x2, y2 = obj.picture_space()
        s = self.scale
        color = (255, 90, 90) if act.startswith("attack") else (120, 220, 255)
        self.pg.draw.rect(self.screen, color, ((x1 - xoff) * s - 2, (y1 - yoff) * s - 2,
                                               (x2 - x1 + 1) * s + 4, (y2 - y1 + 1) * s + 4), 2)

    def _text(self, text: str, x: int, y: int, color=None, font=None) -> int:
        font = font or self.font
        self.screen.blit(font.render(text, True, color or (230, 230, 230)), (x, y))
        return y + font.get_linesize()

    def _panel(self) -> None:
        i, ep = self.info, self.ep
        x = VIEW_W * self.scale + 14
        y = 10
        y = self._text(f"Spectating: {self.label}", x, y, (255, 210, 120))
        y = self._text(f"{ep.scenario.name}, seed {ep.seed}, {ep.difficulty}, Classic rules", x, y, (170, 170, 170),
                       self.small)
        y += 6
        y = self._text(f"decision {ep.decisions}/{ep.budgets.max_decisions}   tick {ep.ticks}/{ep.budgets.max_ticks}",
                       x, y)
        y = self._text(f"invalid actions {ep.invalid_actions}", x, y, (255, 140, 140) if ep.invalid_actions else None)
        y += 6
        act = i["action"] if isinstance(i["action"], str) else repr(i["action"])
        y = self._text(f"action: {act}"[:44], x, y, (140, 230, 140))
        if i["result"]:
            y = self._text(i["result"][:52], x, y, (255, 140, 140) if "REFUSED" in i["result"] else (170, 170, 170),
                           self.small)
        note = i["note"] or ""
        for k in range(0, min(len(note), 156), 52):
            y = self._text(note[k:k + 52], x, y, (200, 200, 255), self.small)
        y += 6
        p = ep._game.player
        y = self._text(f"health {p.hp}", x, y)
        meta = i["meta"] or {}
        if meta.get("model") or i["tokens_in"]:
            y = self._text(f"model {meta.get('model') or '?'} ({meta.get('memory') or '-'})"[:52], x, y,
                           (170, 170, 170), self.small)
            lat = meta.get("latency_s")
            y = self._text(f"tokens {i['tokens_in']} in / {i['tokens_out']} out"
                           + (f", last {lat:.1f} s" if isinstance(lat, int | float) else ""), x, y,
                           (170, 170, 170), self.small)
        if i["replay_ok"] is not None:
            ok = i["mismatches"] == 0
            y = self._text(f"replay check: {i['checked'] - i['mismatches']}/{i['checked']} observations match",
                           x, y, (140, 230, 140) if ok else (255, 120, 120), self.small)
        y += 8
        y = self._text("what the player sees:", x, y, (255, 210, 120), self.small)
        for o in i["visible"][:12]:
            state = f" {o['state']}" if "state" in o else ""
            y = self._text(f"{o['id']} {o['kind']}{state}  dx {o['dx']:+d} dy {o['dy']:+d}"[:52], x, y,
                           (200, 200, 200), self.small)
        if not i["visible"]:
            self._text("(nothing)", x, y, (150, 150, 150), self.small)

    # --- the episode ---------------------------------------------------------------------------
    def run(self) -> dict:
        import time

        ep, player = self.ep, self.player
        player.start({"player_id": PLAYER_ID, "scenario": ep.scenario.name, "seed": ep.seed,
                      "difficulty": ep.difficulty, "budgets": asdict(ep.budgets)})
        obs = ep.observe(PLAYER_ID)
        self.info["visible"] = obs["objects"]
        self.frame()
        usage = new_usage()
        started = time.time()
        trace = player if isinstance(player, TracePlayer) else None
        while ep.outcome()["status"] == "ongoing" and not self.quit:
            legal = ep.legal_actions(PLAYER_ID)
            reply = player.decide(obs, legal)
            if reply.get("trace_ended"):
                reason = (trace.outcome or {}).get("reason")
                if reason in RUNNER_STOPS:
                    ep.stop(reason)  # the runner ended the recorded episode here; do the same
                else:
                    self.info["mismatches"] += 1  # the game goes on but the trace has no more steps
                break
            expect = reply.get("expect_sha")
            if expect is not None:
                self.info["replay_ok"] = True
            meta = reply.get("meta") or {}
            self.info.update(action=reply.get("action"), note=str(reply.get("note") or ""), meta=meta,
                             result="")
            self.info["tokens_in"] += int(meta.get("input_tokens") or 0)
            self.info["tokens_out"] += int(meta.get("output_tokens") or 0)
            res = ep.step(PLAYER_ID, reply.get("action"))
            obs = res["observation"]
            for late in reply.get("late_meta") or []:
                add_usage(usage, late)
            add_usage(usage, meta)
            if trace is None:  # a live player: the runner's budgets and fatal stops apply
                stop, _ = stop_reason(ep.budgets, usage, time.time() - started, reply)
                if stop:
                    ep.stop(stop)
            self.info["visible"] = obs["objects"]
            if res["accepted"]:
                self.info["result"] = f"done in {res['ticks']} ticks"
            else:
                self.info["result"] = f"REFUSED: {res['error']}"
                self.frame()  # a refusal takes no ticks; still show it
            if expect is not None:
                self.info["checked"] += 1
                self.info["mismatches"] += int(obs_sha(obs) != expect)
        out = ep.outcome()
        player.end(out)
        result = {**out, "complete": not self.quit}
        if trace is not None:
            if not self.quit:
                if self.info["checked"] != len(trace.steps):
                    self.info["mismatches"] += 1  # the game ended before the trace did
                expected = trace.outcome or {}
                diff = {k: (out.get(k), expected.get(k)) for k in OUTCOME_KEYS if out.get(k) != expected.get(k)}
                result["outcome_mismatch"] = diff
                self.info["mismatches"] += int(bool(diff))
            result.update(replay_checked=self.info["checked"], replay_steps=len(trace.steps),
                          replay_mismatches=self.info["mismatches"])
        else:
            result.update({k: usage[k] for k in ("input_tokens", "output_tokens", "model_calls", "model_errors")})
        if not self.quit:
            for _ in range(15 * FPS_PER_TICK if self.ffmpeg is not None else 0):  # hold the last frame a second
                self.frame()
        return result

    def close(self) -> None:
        if self.ffmpeg is not None:
            self.ffmpeg.stdin.close()
            self.ffmpeg.wait(timeout=120)
        self.pg.quit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="abuse-replay", description="Watch an Abuse player, or replay a trace")
    ap.add_argument("--trace", type=Path, help="replay this abuse-agent trace")
    ap.add_argument("--player", default=None, help="random | scripted | model | cmd:<command> (watch live)")
    ap.add_argument("--scenario", default="level01", choices=sorted(SCENARIOS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", default="hard")
    ap.add_argument("--max-decisions", type=int, default=None)
    ap.add_argument("--max-input-tokens", type=int, default=0, help="live players: per episode, 0 = no cap")
    ap.add_argument("--max-output-tokens", type=int, default=0, help="live players: per episode, 0 = no cap")
    ap.add_argument("--max-wall-s", type=float, default=0.0, help="live players: per episode, 0 = no cap")
    ap.add_argument("--isolation", choices=("process", "inprocess"), default="process")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--speed", type=float, default=1.0, help="1.0 = the original 15 Hz")
    ap.add_argument("--video", type=Path, help="write an MP4 (needs ffmpeg)")
    ap.add_argument("--headless", action="store_true", help="no window (for --video)")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("player_args", nargs="*", help="extra arguments for the player program (after --)")
    a = ap.parse_args(argv)
    if (a.trace is None) == (a.player is None):
        ap.error("give exactly one of --trace or --player")
    if a.trace is not None:
        player = TracePlayer(a.trace)
        h = player.header
        b = h.get("budgets") or {}
        budgets = Budgets(**{k: v for k, v in b.items() if k in Budgets.__dataclass_fields__})
        ep = AbuseEpisode(h["scenario"], h["seed"], h.get("difficulty", "hard"), budgets)
        label = f"replay of {h.get('label') or a.trace.name}"
    else:
        sc = SCENARIOS[a.scenario]
        budgets = Budgets(max_ticks=sc.max_ticks, max_input_tokens=a.max_input_tokens,
                          max_output_tokens=a.max_output_tokens, max_wall_s=a.max_wall_s)
        if a.max_decisions:
            budgets.max_decisions = a.max_decisions
        if a.player == "model":
            from ..agent.players.model_player import check_config

            problem = check_config(a.player_args)
            if problem:
                print(f"abuse-replay: {problem}", file=sys.stderr)
                return 2
        player = make_player(a.player, a.isolation, a.player_args)
        ep = AbuseEpisode(a.scenario, a.seed, a.difficulty, budgets)
        label = a.player
    sp = Spectator(ep, player, label, a.scale, a.headless, a.video, a.speed, a.max_frames)
    try:
        out = sp.run()
    finally:
        sp.close()
    print(json.dumps(out, indent=2))
    if out.get("replay_mismatches"):
        return 1
    return 0 if out["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
