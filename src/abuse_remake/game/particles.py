"""Modern particle effects driven by engine events. Visual only; uses its own RNG so it can
never disturb the game's random table."""

from __future__ import annotations

import random

import pygame


class Particles:
    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)
        self.items: list[list] = []  # x, y, vx, vy, life, max_life, color, size, gravity, additive

    def emit(self, x, y, n, speed, colors, life=(8, 18), size=(1, 2), gravity=0.25, additive=True):
        r = self.rng
        for _ in range(n):
            a = r.uniform(0, 6.2832)
            s = r.uniform(speed * 0.3, speed)
            lf = r.randint(*life)
            self.items.append([x, y, s * pygame.math.Vector2(1, 0).rotate_rad(a).x,
                               s * pygame.math.Vector2(1, 0).rotate_rad(a).y, lf, lf, r.choice(colors),
                               r.randint(*size), gravity, additive])

    def on_events(self, events, objects_by_uid=None) -> None:
        for e in events:
            d = e.data
            if e.kind == "explosion":
                self.emit(d["x"], d["y"] - 10, 40, 4.5, [(255, 220, 120), (255, 140, 40), (255, 80, 20)],
                          life=(8, 22), size=(1, 3))
                self.emit(d["x"], d["y"] - 10, 14, 1.5, [(90, 90, 90), (60, 60, 60)], life=(20, 40),
                          size=(3, 5), gravity=-0.05, additive=False)
            elif e.kind == "enemy_spawned" and "enemy" in d:  # Horde: show where each enemy comes in
                self.emit(d["x"], d["y"] - 14, 22, 2.6, [(255, 90, 60), (255, 200, 120), (180, 40, 30)],
                          life=(8, 18), size=(1, 2), gravity=0.0)
            elif e.kind == "enemy_killed":
                self.emit(d["x"], d["y"] - 12, 26, 3.5, [(120, 220, 60), (60, 160, 40), (200, 255, 120)],
                          life=(10, 26), size=(1, 3))
            elif e.kind == "wall_destroyed":
                self.emit(d["x"], d["y"] - 8, 30, 3.0, [(150, 140, 130), (110, 100, 90)], life=(12, 30),
                          size=(2, 3), additive=False)
            elif e.kind == "pickup":
                self.emit(d["x"], d["y"] - 6, 16, 1.8, [(120, 255, 200), (255, 255, 255)], life=(10, 20),
                          gravity=-0.08)
            elif e.kind == "dash":  # Remastered: a streak of light behind the player
                for i in range(6):
                    self.emit(d["x"] - d["direction"] * i * 6, d["y"] - 18, 4, 0.6,
                              [(120, 220, 255), (200, 240, 255)], life=(6, 12), size=(1, 2), gravity=0.0)
            elif e.kind == "sound" and d["name"] == "ZAP_SND":
                self.emit(d["x"], d["y"], 5, 2.0, [(255, 120, 90), (255, 230, 200)], life=(3, 7))

    def step(self, frames: float = 1.0) -> None:
        keep = []
        for p in self.items:
            p[0] += p[2] * frames
            p[1] += p[3] * frames
            p[3] += p[8] * frames
            p[4] -= frames
            if p[4] > 0:
                keep.append(p)
        self.items = keep

    def draw(self, surf: pygame.Surface, xoff: float, yoff: float) -> None:
        for x, y, _vx, _vy, life, max_life, color, size, _g, additive in self.items:
            k = max(0.0, life / max_life)
            c = (int(color[0] * k), int(color[1] * k), int(color[2] * k))
            rect = (round(x - xoff), round(y - yoff), size, size)
            if additive:
                surf.fill(c, rect, special_flags=pygame.BLEND_RGB_ADD)
            else:
                surf.fill(c, rect)
