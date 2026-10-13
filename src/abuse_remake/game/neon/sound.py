"""Neon Protocol audio: recorded sound effects and music. Presentation only.

Effects come from Kenney's Sci-Fi, Interface and RPG packs and rubberduck's creature pack;
music from vitalezzz, cinameng, SRG774 and MintoDog (all CC0; see assets/neon/PROVENANCE.md).
Each game event picks a random variant, is attenuated by distance from the runner and panned
in stereo, with a per-sound rate limit so a swarm never turns into noise. Music follows the
action: a calm track while exploring, the combat track while alerted hostiles are near, the
boss track in the Core. Changes fade out and in. Classic and Remastered keep game/audio.py.
"""

from __future__ import annotations

import random

import pygame as pg

from ...paths import assets_root

ROOT = assets_root() / "neon"

BANKS = {
    "pulse": ["sfx_scifi/Audio/laserSmall_00{}.ogg", range(5)],
    "scatter": ["sfx_scifi/Audio/laserRetro_00{}.ogg", range(5)],
    "rail": ["sfx_scifi/Audio/laserLarge_00{}.ogg", range(5)],
    "mortar": ["sfx_scifi/Audio/thrusterFire_00{}.ogg", range(3)],
    "seeker": ["sfx_scifi/Audio/thrusterFire_00{}.ogg", range(3)],
    "explode": ["sfx_scifi/Audio/explosionCrunch_00{}.ogg", range(5)],
    "boom": ["sfx_scifi/Audio/lowFrequency_explosion_00{}.ogg", range(2)],
    "metal": ["sfx_scifi/Audio/impactMetal_00{}.ogg", range(5)],
    "field": ["sfx_scifi/Audio/forceField_00{}.ogg", range(5)],
    "door_open": ["sfx_scifi/Audio/doorOpen_00{}.ogg", range(3)],
    "door_close": ["sfx_scifi/Audio/doorClose_00{}.ogg", range(3)],
    "computer": ["sfx_scifi/Audio/computerNoise_00{}.ogg", range(4)],
    "squish": ["sfx_scifi/Audio/slime_00{}.ogg", range(2)],
    "click": ["sfx_ui/Audio/click_00{}.ogg", range(1, 4)],
    "confirm": ["sfx_ui/Audio/confirmation_00{}.ogg", range(1, 5)],
    "back": ["sfx_ui/Audio/back_00{}.ogg", range(1, 3)],
    "select": ["sfx_ui/Audio/select_00{}.ogg", range(1, 4)],
    "error": ["sfx_ui/Audio/error_00{}.ogg", range(1, 5)],
    "glitch": ["sfx_ui/Audio/glitch_00{}.ogg", range(1, 5)],
    "switch": ["sfx_ui/Audio/switch_00{}.ogg", range(1, 4)],
    "power": ["sfx_ui/Audio/maximize_00{}.ogg", range(1, 4)],
    "step": ["sfx_foley/OGG/footstep0{}.ogg", range(10)],
    "latch": ["sfx_foley/OGG/metalLatch.ogg", [None]],
    "gunclick": ["sfx_foley/OGG/metalClick.ogg", [None]],
    "scream": ["sfx_creature/alien_{:02d}.ogg", range(7, 13)],
    "bug": ["sfx_creature/bug_{:02d}.ogg", range(5, 14)],
    "die": ["sfx_creature/die_{:02d}.ogg", range(1, 5)],
    "monster": ["sfx_creature/monster_{:02d}.ogg", range(10, 20)],
    "roar": ["sfx_creature/roar_{:02d}.ogg", range(4, 7)],
    "slime": ["sfx_creature/slime_{:02d}.ogg", range(1, 7)],
    "attack": ["sfx_creature/attack_{:02d}.ogg", range(1, 6)],
    "stomp": ["sfx_creature/stomp_01.ogg", [None]],
    "weird": ["sfx_creature/weird_{:02d}.ogg", range(6, 10)],
    "pain": ["sfx_creature/human_{:02d}.ogg", range(1, 9)],
    "victory": ["music_darkscifi/victory.ogg", [None]],
}
# event -> (bank, volume 0..1, minimum seconds between plays)
EVENTS = {
    "jump": ("step", 0.25, 0.1), "air_jump": ("field", 0.35, 0.1), "dash": ("field", 0.5, 0.1),
    "drop": ("latch", 0.4, 0.2),
    "empty": ("gunclick", 0.6, 0.15), "switch": ("gunclick", 0.5, 0.05),
    "explosion": ("explode", 0.9, 0.06), "impact": ("metal", 0.18, 0.05), "bounce": ("metal", 0.35, 0.05),
    "deflect": ("metal", 0.55, 0.06), "break": ("explode", 0.7, 0.1),
    "hurt": ("pain", 0.75, 0.25), "shield_hit": ("field", 0.5, 0.15), "player_death": ("pain", 1.0, 1.0),
    "pickup": ("confirm", 0.6, 0.05), "checkpoint": ("computer", 0.8, 0.5),
    "switch_on": ("switch", 0.8, 0.2), "door_open": ("door_open", 0.8, 0.2), "door_close": ("door_close", 0.7, 0.2),
    "locked": ("error", 0.6, 0.4), "elevator": ("door_open", 0.5, 0.4), "elevator_stop": ("latch", 0.5, 0.3),
    "teleport": ("glitch", 0.8, 0.3),
    "alert": ("scream", 0.75, 0.35), "crawler_drop": ("bug", 0.6, 0.2), "crawler_land": ("step", 0.4, 0.1),
    "crawler_wind": ("attack", 0.55, 0.15), "pounce": ("attack", 0.7, 0.15), "crawler_leap": ("bug", 0.45, 0.2),
    "bite": ("attack", 0.8, 0.15), "spit": ("slime", 0.6, 0.15), "dodge": ("bug", 0.4, 0.2),
    "stinger_wind": ("weird", 0.6, 0.2), "dive": ("bug", 0.7, 0.2), "sting": ("attack", 0.7, 0.2),
    "sentry_up": ("field", 0.55, 0.2), "enemy_shot": ("scatter", 0.35, 0.06),
    "lob_wind": ("computer", 0.4, 0.3), "stomp_wind": ("monster", 0.55, 0.3), "stomp": ("stomp", 1.0, 0.2),
    "strider_turn": ("metal", 0.4, 0.3), "alarm": ("glitch", 1.0, 0.5),
    "nest_open": ("slime", 0.7, 0.3), "nest_spawn": ("bug", 0.5, 0.2),
    "boss_phase": ("roar", 1.0, 1.0), "laser_charge": ("field", 0.9, 0.4), "laser_fire": ("rail", 1.0, 0.3),
    "vent": ("computer", 0.9, 0.5), "boss_dead": ("boom", 1.0, 1.0),
    "wave": ("glitch", 0.9, 0.5), "wave_clear": ("confirm", 0.9, 0.5), "upgrade": ("power", 0.9, 0.3),
    "lesson": ("confirm", 0.8, 0.3), "sector_clear": ("victory", 0.9, 1.0), "training_complete": ("victory", 0.9, 1.0),
}
KILL_SOUNDS = {"crawler": ("die", 0.7), "stinger": ("bug", 0.7), "nest": ("slime", 0.8), "warden": ("boom", 1.0),
               "strider": ("boom", 0.9), "drone": ("explode", 0.7), "sentry": ("explode", 0.7),
               "target": ("confirm", 0.6)}
SHOT_BANKS = ("pulse", "scatter", "rail", "mortar", "seeker")
SHOT_VOLUME = (0.35, 0.5, 0.7, 0.6, 0.55)
MUSIC = {
    "menu": "music_pynchon/pynchon.mp3",
    "combat": "music_specular/specular_city.mp3",
    "boss": "music_boss/hard_boss_battle_2.mp3",
    "transit": "music_darkscifi/sector.ogg",
    "reactor": "music_darkscifi/airy.ogg",
    "hive": "music_darkscifi/pulse.ogg",
    "training": "music_darkscifi/sector.ogg",
    "tension": "music_darkscifi/urgent.ogg",
}
HEAR = 560  # px: beyond this an effect is silent


class Sound:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.sfx_volume = 0.8
        self.music_volume = 0.55
        self.banks: dict[str, list[pg.mixer.Sound]] = {}
        self.last: dict[str, float] = {}
        self.clock = 0.0
        self.track = None
        self.want = None
        self.rng = random.Random()
        self.step_t = 0.0
        self.hum = None
        if not enabled:
            return
        try:
            if not pg.mixer.get_init():
                pg.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pg.mixer.set_num_channels(40)
            pg.mixer.set_reserved(1)
        except pg.error:
            self.enabled = False
            return
        for name, (pattern, variants) in BANKS.items():
            sounds = []
            for v in variants:
                path = ROOT / (pattern.format(v) if v is not None else pattern)
                if path.exists():
                    try:
                        sounds.append(pg.mixer.Sound(str(path)))
                    except pg.error:
                        pass
            if sounds:
                self.banks[name] = sounds
        hum = ROOT / "sfx_scifi/Audio/spaceEngineLow_000.ogg"
        if hum.exists():
            self.hum = pg.mixer.Sound(str(hum))

    # ------------------------------------------------------------ effects
    def play(self, bank: str, volume: float = 1.0, pan: float = 0.0, gap: float = 0.0, key: str | None = None):
        if not self.enabled or bank not in self.banks:
            return
        key = key or bank
        if gap and self.clock - self.last.get(key, -9) < gap:
            return
        self.last[key] = self.clock
        snd = self.rng.choice(self.banks[bank])
        ch = snd.play()
        if ch is None:
            return
        v = max(0.0, min(1.0, volume * self.sfx_volume))
        ch.set_volume(v * min(1.0, 1 - pan), v * min(1.0, 1 + pan))

    def events(self, game) -> None:
        if not self.enabled:
            return
        p = game.player
        for e in game.events:
            k = e["kind"]
            dx, dy = e["x"] - p.cx, e["y"] - p.cy
            d = (dx * dx + dy * dy) ** 0.5
            if d > HEAR and k not in ("sector_clear", "boss_phase", "alarm", "wave"):
                continue
            near = max(0.15, 1 - d / HEAR)
            pan = max(-0.8, min(0.8, dx / 400))
            if k == "shot":
                w = e["weapon"]
                self.play(SHOT_BANKS[w], SHOT_VOLUME[w], pan, 0.03, key=f"shot{w}")
            elif k == "rail":
                self.play("field", 0.4, pan, 0.1)
            elif k == "kill":
                bank, vol = KILL_SOUNDS.get(e.get("enemy"), ("explode", 0.6))
                self.play(bank, vol * near, pan, 0.05, key="kill" + bank)
                if e.get("enemy") in ("crawler", "stinger"):
                    self.play("squish", 0.5 * near, pan, 0.05)
            elif k == "hit":
                if e.get("enemy") in ("crawler", "stinger", "nest"):
                    self.play("slime", 0.35 * near, pan, 0.08, key="hit-organic")
                else:
                    self.play("metal", 0.35 * near, pan, 0.06, key="hit-metal")
            elif k == "land":
                if e.get("speed", 0) > 1600:
                    self.play("step", 0.55, 0, 0.1, key="land")
            elif k in EVENTS:
                bank, vol, gap = EVENTS[k]
                self.play(bank, vol * near, pan, gap, key=k)

    def footsteps(self, game, dt: float) -> None:
        p = game.player
        if not self.enabled or not p.grounded or p.dying or abs(p.vx) < 200 or p.dash_t:
            self.step_t = 0.0
            return
        self.step_t -= dt * abs(p.vx) / 896
        if self.step_t <= 0:
            self.step_t = 0.28
            self.play("step", 0.22 if not p.crouching else 0.1)

    def tick(self, dt: float) -> None:
        self.clock += dt
        self._music_step()

    # ------------------------------------------------------------ music
    def music(self, name: str | None) -> None:
        self.want = name

    def ambience(self, on: bool) -> None:
        if not self.enabled or self.hum is None:
            return
        ch = pg.mixer.Channel(0)
        if on and not ch.get_busy():
            ch.play(self.hum, loops=-1, fade_ms=1500)
            ch.set_volume(0.12 * self.sfx_volume)
        elif not on and ch.get_busy():
            ch.fadeout(800)

    def _music_step(self) -> None:
        if not self.enabled:
            return
        if self.want == self.track:
            if self.track and not pg.mixer.music.get_busy():
                self._start(self.track)
            return
        if pg.mixer.music.get_busy() and self.track is not None:
            if not getattr(self, "_fading", False):
                pg.mixer.music.fadeout(900)
                self._fading = True
            return
        self._fading = False
        self.track = self.want
        if self.track:
            self._start(self.track)

    def _start(self, name: str) -> None:
        path = ROOT / MUSIC[name]
        if not path.exists():
            return
        try:
            pg.mixer.music.load(str(path))
            pg.mixer.music.set_volume(self.music_volume)
            pg.mixer.music.play(loops=-1, fade_ms=1200)
        except pg.error:
            pass

    def set_volume(self, delta: float) -> float:
        self.sfx_volume = max(0.0, min(1.0, self.sfx_volume + delta))
        self.music_volume = max(0.0, min(1.0, self.music_volume + delta * 0.7))
        if self.enabled:
            pg.mixer.music.set_volume(self.music_volume)
        return self.sfx_volume

    def stop(self) -> None:
        if self.enabled:
            pg.mixer.music.fadeout(300)
            pg.mixer.stop()


def music_for(game, combat: bool) -> str:
    if game.variant == "horde":
        return "combat"
    if game.variant == "training":
        return "training"
    if game.map.theme == "core":
        return "boss" if any(e.kind == "warden" and e.alerted for e in game.enemies) else "tension"
    return "combat" if combat else game.map.theme if game.map.theme in MUSIC else "transit"

