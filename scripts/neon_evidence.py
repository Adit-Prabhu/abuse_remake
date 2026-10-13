"""Generate reproducible Neon screenshots and a checked development smoke trace.

This is a development tool with full engine access, NOT a playing agent or fair evaluation.
No human playtest results or model calls are implied. Run: uv run python scripts/neon_evidence.py
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from abuse_remake.engine.view import Inputs  # noqa: E402
from abuse_remake.game.app import parse_args  # noqa: E402
from abuse_remake.game.human_replay import replay_human  # noqa: E402
from abuse_remake.game.neon_app import NeonApp  # noqa: E402


def campaign_input(game, tick):
    """Developer-only smoke controller, allowed to inspect the map and all enemies."""
    p = game.player
    sector = sum(r.active for r in game.relays)
    left = game.doors[sector - 1][0] if 0 < sector <= len(game.doors) else 0
    right = game.doors[sector][0] if sector < len(game.doors) else game.width
    targets = [e for e in game.enemies if left <= e.x < right]
    enemy = min(targets, key=lambda e: abs(e.x - p.x)) if targets else None
    goal = game.relays[sector].x - 10 if sector < 3 else game.exit_x
    move = 1 if p.x < goal - 5 else -1 if p.x > goal + 5 else 0
    action = 1 if move == 0 and tick % 2 == 0 else -1 if tick % 30 == 0 else 0
    return Inputs(x=move, y=action, b2=int(enemy is not None),
                  pointer_x=enemy.x + enemy.w // 2 if enemy else goal,
                  pointer_y=enemy.y + enemy.h // 2 if enemy else 480)


def generate(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    trace = out / "development-smoke.jsonl"
    args = parse_args(["--mode", "neon", "--no-audio", "--scale", "1", "--seed", "7", "--record", str(trace)])
    args.trace_player = "development-smoke-controller"
    app = NeonApp(args)

    def shot(name):
        app.acc = 1 / 15  # show the current tick's positions in a still screenshot
        app.draw()
        pygame.image.save(app.screen, str(out / f"{name}.png"))

    shot("title")
    app.start("tutorial")
    shot("training")
    app.on_key(pygame.K_F1)
    shot("controls")
    app.on_key(pygame.K_ESCAPE)
    app.start("campaign")
    core_shown = False
    for tick in range(1800):
        app.tick(campaign_input(app.game, tick))
        app.renderer.update_effects(1 / 15)
        if tick == 70:
            shot("campaign")
        if app.game.player.x >= 3540 and not core_shown:
            shot("core")
            core_shown = True
        if app.state != "play":
            break
    campaign = {"status": app.game.status, "ticks": app.game.frames, "kills": app.game.kills,
                "relays": sum(r.active for r in app.game.relays), "health": app.game.player.hp}
    shot("extraction")
    app.start("horde")
    for _ in range(165):
        app.tick(app.scripted_inputs())
        app.renderer.update_effects(1 / 15)
        if app.state != "play":
            break
    shot("horde")
    app.close_trace()
    pygame.quit()
    replay = replay_human(trace)
    report = {"purpose": "developer smoke only; full map access, not a fair player evaluation or human playtest",
              "seed": 7, "difficulty": "hard", "campaign": campaign, "trace_replay": replay,
              "screenshots": [f"{name}.png" for name in
                              ("title", "campaign", "core", "horde", "training", "controls", "extraction")]}
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    if campaign["status"] != "won" or replay["mismatches"]:
        raise SystemExit("Neon smoke or replay failed")
    print(json.dumps({"campaign": campaign, "replay_checks": replay["checks"], "mismatches": replay["mismatches"]}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("evidence/neon"))
    generate(p.parse_args().out)
