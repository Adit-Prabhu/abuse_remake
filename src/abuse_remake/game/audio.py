"""Procedural sound effects, keyed by the original sound names.

The original sounds are Bobby Prince's copyright and are not shipped. Rather than depend on a
download, each effect is synthesised with numpy at start-up (a small sfxr-style generator), so
the game is self-contained and licence-clean.

Volume follows the original's ``game::play_sound`` (abuse/src/game.c:134-166): sounds quieter
than 15 are dropped; the distance is the octagonal ``dx + dy - min(dx, dy) / 2`` from the player
(``view::x_center`` is the focus); nothing plays beyond 500 px; it is full volume within 100 px;
and the volume is ``(400 - (d - 100)) * sfx_volume / 400 - (127 - vol)`` on the 0..127 scale.
Classic plays every sound, centred, as the original did. Remastered adds stereo pan and plays
one copy of each sound per tick.
"""

from __future__ import annotations

import numpy as np
import pygame

RATE = 22050


SFX_VOLUME = 127  # the original's full sound-effect volume


def original_volume(vol: int, dx: int, dy: int, sfx_volume: int = SFX_VOLUME) -> int:
    """game::play_sound's volume (0..127) for a sound at (dx, dy) from the listener, or 0."""
    if vol < 15:
        return 0
    cx, cy = abs(dx), abs(dy)
    d = cx + cy - ((cx if cx < cy else cy) >> 1)
    if d > 500:
        return 0
    d = 0 if d < 100 else d - 100
    v = (400 - d) * sfx_volume // 400 - (127 - vol)
    return max(0, v)


def _env(n, attack=0.01, decay=1.0):
    t = np.linspace(0, 1, n, endpoint=False)
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t * 6.0 / max(decay, 1e-3))


def _tone(freq0, freq1, dur, wave="square", decay=1.0, vib=0.0):
    n = int(RATE * dur)
    f = np.geomspace(max(freq0, 1), max(freq1, 1), n)
    if vib:
        f = f * (1 + vib * np.sin(np.linspace(0, 40 * dur * 2 * np.pi, n)))
    phase = np.cumsum(f) / RATE
    if wave == "square":
        s = np.sign(np.sin(2 * np.pi * phase))
    elif wave == "saw":
        s = 2 * (phase % 1.0) - 1
    elif wave == "tri":
        s = 2 * np.abs(2 * (phase % 1.0) - 1) - 1
    else:
        s = np.sin(2 * np.pi * phase)
    return s * _env(n, decay=decay)


def _noise(dur, decay=1.0, lowpass=0.5, seed=0):
    n = int(RATE * dur)
    rng = np.random.default_rng(seed)
    s = rng.uniform(-1, 1, n)
    out = np.empty_like(s)
    acc = 0.0
    k = max(0.01, min(1.0, lowpass))
    for i in range(n):  # one-pole low-pass
        acc += k * (s[i] - acc)
        out[i] = acc
    return out / (np.abs(out).max() + 1e-6) * _env(n, decay=decay)


def _mix(*parts):
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[: len(p)] += p
    return out


PRESETS = {
    "ZAP_SND": lambda: _tone(1400, 260, 0.13, "square", 0.5) * 0.5,
    "GRENADE_THROW": lambda: _noise(0.18, 0.6, 0.3, 1) * 0.6,
    "GRENADE_SND": lambda: _mix(_noise(0.7, 0.9, 0.08, 2), _tone(90, 40, 0.5, "sine", 0.8)) * 0.8,
    "ROCKET_LAUNCH_SND": lambda: _mix(_noise(0.4, 1.2, 0.15, 3), _tone(200, 500, 0.4, "saw", 1.0) * 0.3),
    "ROCKET_SND": lambda: _noise(0.3, 1.0, 0.1, 4) * 0.5,
    "FIREBOMB_SND": lambda: _noise(0.5, 1.4, 0.2, 5) * 0.7,
    "SWITCH_SND": lambda: _mix(_tone(800, 800, 0.03, "square", 0.3), _tone(1200, 1200, 0.06, "square", 0.4)) * 0.4,
    "SWISH": lambda: _noise(0.35, 1.2, 0.12, 6) * 0.5,
    "AMMO_SND": lambda: np.concatenate([_tone(660, 660, 0.05), _tone(990, 990, 0.08)]) * 0.35,
    "HEALTH_UP_SND": lambda: np.concatenate([_tone(523, 523, 0.06, "tri"), _tone(659, 659, 0.06, "tri"),
                                             _tone(784, 784, 0.1, "tri")]) * 0.45,
    "ASCREAM_SND": lambda: _tone(900, 1500, 0.35, "saw", 1.2, vib=0.08) * 0.35,
    "APAIN_SND": lambda: _tone(1200, 600, 0.15, "saw", 0.6) * 0.35,
    "SCARE_SND": lambda: _tone(110, 80, 0.6, "saw", 1.5, vib=0.05) * 0.3,
    "ALAND_SND": lambda: _mix(_noise(0.12, 0.4, 0.05, 7), _tone(120, 60, 0.12, "sine")) * 0.5,
    "ASLASH_SND": lambda: _noise(0.15, 0.4, 0.6, 8) * 0.5,
    "LOW_HEALTH_SND": lambda: np.concatenate([_tone(70, 50, 0.08, "sine", 0.3), np.zeros(1500),
                                              _tone(70, 50, 0.08, "sine", 0.3)]) * 0.6,
    "HWALL_SND": lambda: _mix(_noise(0.6, 0.9, 0.1, 9), _tone(70, 35, 0.5, "sine", 0.9)) * 0.8,
    "P_EXPLODE_SND": lambda: _noise(0.5, 0.8, 0.12, 10) * 0.7,
    "BLOWN_UP": lambda: _mix(_noise(0.8, 1.0, 0.07, 11), _tone(60, 30, 0.6, "sine", 1.0)) * 0.8,
    "TELEPORTER_SND": lambda: _tone(300, 1800, 0.7, "sine", 1.5, vib=0.15) * 0.35,
    "APPEAR_SND": lambda: _tone(600, 1600, 0.25, "tri", 1.0, vib=0.1) * 0.25,
    "FF_SND": lambda: _tone(120, 120, 0.08, "saw", 0.2) * 0.12,
    "SAVE_SND": lambda: np.concatenate([_tone(784, 784, 0.08, "tri"), _tone(1046, 1046, 0.18, "tri")]) * 0.4,
    "DOOR_UP": lambda: _tone(180, 260, 0.25, "saw", 1.0) * 0.2,
    "DOOR_DOWN": lambda: _tone(260, 180, 0.25, "saw", 1.0) * 0.2,
    "PLAT_A_SND": lambda: _tone(140, 160, 0.2, "saw", 1.0) * 0.2,
    "PLAT_D_SND": lambda: _tone(160, 120, 0.2, "saw", 1.0) * 0.2,
    "SBALL_SND": lambda: _mix(_noise(0.15, 0.5, 0.05, 12), _tone(90, 50, 0.15, "sine")) * 0.6,
    "MGUN_SND": lambda: _noise(0.06, 0.3, 0.7, 13) * 0.4,
    "FADEON_SND": lambda: _tone(200, 400, 0.3, "sine", 1.2) * 0.2,
    "SPEED_SND": lambda: _tone(500, 900, 0.1, "square", 0.5) * 0.2,
    # the campaign levels (Remastered)
    "SPRING_SOUND": lambda: _tone(180, 720, 0.22, "tri", 0.8, vib=0.2) * 0.45,
    "LAVA_SND": lambda: _mix(_noise(0.4, 0.8, 0.04, 30), _tone(70, 45, 0.4, "sine", 0.8)) * 0.4,
    "FLYER_SND": lambda: _tone(240, 260, 0.12, "saw", 0.4, vib=0.3) * 0.12,
    "FLY_SND": lambda: _noise(0.12, 0.5, 0.25, 31) * 0.25,
}
for i in range(4):
    PRESETS[f"PLAYER_PAIN{i}"] = (lambda k=i: _tone(180 - 15 * k, 90, 0.18, "square", 0.6) * 0.4)
    PRESETS[f"PLAYER_DEATH{i}"] = (lambda k=i: _mix(_tone(160 - 10 * k, 40, 0.9, "saw", 1.4),
                                                   _noise(0.5, 1.0, 0.1, 20 + k) * 0.4) * 0.5)
for i in range(3):
    PRESETS[f"ASML_DEATH{i}"] = (lambda k=i: _tone(1500 - 200 * k, 300, 0.4, "saw", 1.0, vib=0.1) * 0.35)
    PRESETS[f"ALRG_DEATH{i}"] = (lambda k=i: _tone(700 - 100 * k, 120, 0.6, "saw", 1.2, vib=0.1) * 0.4)
for i in range(17):
    PRESETS[f"AMB_SOUND{i}"] = (lambda k=i: _tone(55 + 7 * k, 50 + 5 * k, 1.2, "sine", 3.0, vib=0.02) * 0.12)


class Audio:
    def __init__(self, enabled: bool = True, volume: float = 0.8, modern: bool = True):
        self.modern = modern
        self.enabled = enabled
        self.volume = volume
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        if not enabled:
            return
        try:
            pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(24)
        except pygame.error:
            self.enabled = False

    def _sound(self, name: str):
        snd = self.sounds.get(name)
        if snd is None:
            make = PRESETS.get(name, lambda: _tone(440, 440, 0.04, "square", 0.3) * 0.15)
            mono = np.clip(make(), -1, 1)
            pcm = (mono * 32767 * 0.9).astype(np.int16)
            stereo = np.repeat(pcm[:, None], 2, axis=1)
            snd = self.sounds[name] = pygame.sndarray.make_sound(np.ascontiguousarray(stereo))
        return snd

    def play_events(self, events, listener_x: int, listener_y: int) -> None:
        if not self.enabled:
            return
        played = set()
        for e in events:
            if e.kind != "sound":
                continue
            name = e.data["name"]
            if self.modern and name in played:  # Remastered: one copy per tick is enough
                continue
            played.add(name)
            dx = int(e.data["x"] - listener_x)
            dy = int(e.data["y"] - listener_y)
            v = original_volume(int(e.data.get("volume", 127)), dx, dy)
            if v <= 0:
                continue
            vol = self.volume * v / 127
            ch = self._sound(name).play()
            if ch is None:
                continue
            if self.modern:
                pan = max(-1.0, min(1.0, dx / 300))
                ch.set_volume(vol * (1 - max(0, pan)), vol * (1 + min(0, pan)))
            else:
                ch.set_volume(vol)
