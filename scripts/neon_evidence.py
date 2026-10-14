"""Generate Neon Protocol v2 screenshots and a replay-checked development trace.

This is a development tool. The autopilot (engine/neon/autopilot.py) has full map access: it
is NOT a playing agent, a fair evaluation or a human playtest. It only presses normal
controls through the app; nothing is granted, moved or unlocked by hand. When it dies the app
restores the last checkpoint, exactly as a player's R / Space would.

Run: uv run python scripts/neon_evidence.py   (no network, no model calls)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from abuse_remake.engine.neon import NeonInput  # noqa: E402
from abuse_remake.engine.neon.autopilot import Autopilot  # noqa: E402
from abuse_remake.game.app import parse_args  # noqa: E402
from abuse_remake.game.human_replay import replay_human  # noqa: E402
from abuse_remake.game.neon.app import NeonApp  # noqa: E402


def generate(out: Path, seed: int, difficulty: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    trace = out / "development-campaign.jsonl"
    args = parse_args(["--mode", "neon", "--no-audio", "--scale", "2", "--seed", str(seed),
                       "--difficulty", difficulty, "--record", str(trace)])
    args.trace_player = "development-autopilot"
    app = NeonApp(args)
    shots: list[str] = []

    def shot(name: str) -> None:
        app.draw(1 / 60)
        pygame.image.save(app.screen, str(out / f"{name}.png"))
        shots.append(f"{name}.png")

    for _ in range(20):
        app.draw(1 / 60)
    shot("title")
    app.on_key(pygame.K_F1)
    for page, name in ((0, "manual-controls"), (2, "manual-hostiles")):
        app.page = page
        shot(name)
    app.on_key(pygame.K_ESCAPE)

    app.start("training")
    for _ in range(40):
        app.tick(NeonInput(x=1, px=app.game.player.cx + 100, py=app.game.player.cy))
        app.draw(1 / 30)
    shot("training")

    app.start("campaign")
    bot = Autopilot(app.game)
    deaths, sector_ticks, last_sector, start = 0, {}, 0, app.game.frames
    fought = set()
    laser_shown = False
    for tick in range(30000):
        inp = bot.step()
        app.pending_select = bot.select
        app.tick(inp)
        if tick % 3 == 0:
            app.draw(1 / 20)
        g = app.game
        if g.sector != last_sector:
            sector_ticks[last_sector] = g.frames - start
            start, last_sector = g.frames, g.sector
            for _ in range(60):
                app.tick(bot.step())
                app.draw(1 / 30)
            shot(f"sector{g.sector + 1}-arrival")
        near = [e for e in g.enemies if e.alerted and abs(e.cx - g.player.cx) < 260 and e.kind != "nest"]
        if g.sector not in fought and len(near) >= 2:
            fought.add(g.sector)
            shot(f"sector{g.sector + 1}-fight")
        boss = next((e for e in g.enemies if e.kind == "warden"), None)
        if boss is not None and boss.laser == "sweep" and not laser_shown:
            laser_shown = True
            shot("boss-laser")
        if app.state == "dead":
            deaths += 1
            app.restore()
            bot = Autopilot(g, patience=deaths * 37 % 90)
        if app.state == "complete":
            sector_ticks[last_sector] = g.frames - start
            shot("campaign-complete")
            break
    campaign = {"status": app.game.status, "deaths_restored": deaths, "ticks": app.game.frames,
                "seconds": app.game.frames // 30, "kills": app.game.kills, "secrets": app.game.secrets,
                "damage_taken": app.game.damage_taken, "sector_ticks": sector_ticks}

    app.start("horde")
    bot = Autopilot(app.game)
    bot.targets = []
    for tick in range(20000):  # until the run ends
        g = app.game
        if app.state == "upgrade":
            if "horde-upgrade.png" not in shots:
                shot("horde-upgrade")
            app.choose(0)
            continue
        aim, fire = bot._combat()
        p = g.player
        sx, sy = p.shoulder()
        px, py = aim if aim else (sx + 100, sy)
        app.pending_select = bot.select
        app.tick(NeonInput(x=1 if (tick // 70) % 2 == 0 else -1, jump=tick % 45 < 10, fire=fire,
                           dash=tick % 120 == 0, px=px, py=py))
        if tick % 3 == 0:
            app.draw(1 / 20)
        if tick == 900:
            shot("horde")
        if app.state in ("dead", "complete"):
            shot("horde-over")
            break
    horde = {"waves_cleared": app.game.horde.cleared, "kills": app.game.kills, "status": app.game.status}
    app.close_trace()
    pygame.quit()
    replay = replay_human(trace)
    report = {"purpose": "development evidence only: a full-map-access autopilot pressing normal controls; "
                         "not a playing agent, a fair evaluation or a human playtest",
              "seed": seed, "difficulty": difficulty, "campaign": campaign, "horde": horde,
              "trace_replay": {"checks": replay["checks"], "mismatches": replay["mismatches"],
                               "games": len(replay["games"])},
              "screenshots": shots}
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    if campaign["status"] != "won" or replay["mismatches"]:
        raise SystemExit("Neon evidence run failed: " + json.dumps(report))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("evidence/neon"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--difficulty", default="hard")
    r = generate(p.parse_args().out, p.parse_args().seed, p.parse_args().difficulty)
    print(json.dumps({"campaign": r["campaign"], "horde": r["horde"], "replay": r["trace_replay"]}, indent=1))
