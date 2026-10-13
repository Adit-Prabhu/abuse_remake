"""Horde v2: survive waves in a three-tier arena, and pick an upgrade after every wave.

Wave n queues min(34, 4 + 2n) hostiles: crawlers from the vents, stingers from wave 2, striders
from wave 4 (more as waves grow), and elite striders every fifth wave. Each wave hostiles have
6% more integrity and hit 3% harder than the wave before, so upgrades never make a run endless.
Supplies respawn on their spots when a wave is cleared, then the run offers two upgrades (each
at most three times); the break before the next wave starts once one is chosen. A hostile that
has not moved for 20 seconds is moved back to a vent, so a wave can never stall. The run ends
when the runner dies; the score is waves cleared and kills.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fixed import dist

UPGRADES = {
    "vitality": ("VITALITY", "+25 max integrity and a full repair"),
    "rapid": ("RAPID CYCLE", "Every weapon fires 15% faster"),
    "amp": ("AMP ROUNDS", "+20% weapon damage"),
    "coils": ("PHASE COILS", "The dash recharges 30% faster"),
    "mags": ("DEEP MAGS", "+50% ammo capacity, all refilled"),
    "boots": ("VAULT BOOTS", "Double jump"),
    "nano": ("NANO REPAIR", "Regenerate 1 integrity every 2 seconds"),
    "aegis": ("AEGIS CORE", "A 40-point shield at the start of every wave"),
    "arsenal": ("ARSENAL", "Unlock the next weapon with full ammo"),
}
FIRST_BREAK, BREAK, SPAWN_GAP = 90, 150, 22
MAX_STACK = 3
STUCK_TICKS = 600


@dataclass
class HordeState:
    wave: int = 0
    cleared: int = 0
    break_t: int = FIRST_BREAK
    queue: list = field(default_factory=list)
    spawn_t: int = 0
    offer: list = field(default_factory=list)
    taken: list = field(default_factory=list)
    active: bool = False
    watch: dict = field(default_factory=dict)  # uid -> [x, y, ticks without moving]


def hp_pct(wave: int) -> int:
    return 100 + 6 * max(0, wave - 1)


def damage_pct(wave: int) -> int:
    return 100 + 3 * max(0, wave - 1)


def max_alive(wave: int) -> int:
    return min(16, 10 + wave // 3)


def wave_plan(wave: int, rng) -> list[str]:
    n = min(34, 4 + 2 * wave)
    kinds = ["crawler"] * 6 + (["stinger"] * 3 if wave >= 2 else []) + (["strider"] if wave >= 4 else [])
    plan = ["strider elite"] * (wave // 5) if wave % 5 == 0 else []
    striders, cap = 0, 2 + wave // 6
    while len(plan) < n:
        k = rng.choice(kinds)
        if k == "strider":
            striders += 1
            if striders > cap:
                k = "crawler"
        plan.append(k)
    return plan


def eligible(game) -> list[str]:
    names = [n for n in UPGRADES if game.horde.taken.count(n) < MAX_STACK]
    if game.player.boots and "boots" in names:
        names.remove("boots")
    if all(game.owned) and "arsenal" in names:
        names.remove("arsenal")
    return names or ["vitality"]


def tick(game) -> None:
    h = game.horde
    if not game.player.alive or h.offer:
        return
    hostiles = [e for e in game.enemies if not e.dead and e.kind != "nest"]
    _unstick(game, hostiles)
    if h.active:
        if h.queue:
            h.spawn_t -= 1
            if h.spawn_t <= 0 and len(hostiles) < max_alive(h.wave):
                _spawn(game, h.queue.pop(0))
                h.spawn_t = SPAWN_GAP
            return
        if not hostiles:
            h.active = False
            h.cleared = h.wave
            h.break_t = BREAK
            game.emit("wave_clear", game.player.cx, game.player.cy, wave=h.wave)
            game.respawn_supplies()
            options = eligible(game)
            first = game.rng.choice(options)
            if len(options) > 1:
                options.remove(first)
            h.offer = [first, game.rng.choice(options)]
        return
    h.break_t -= 1
    if h.break_t <= 0:
        h.wave += 1
        h.active = True
        h.queue = wave_plan(h.wave, game.rng)
        h.spawn_t = 0
        if "aegis" in h.taken:
            game.player.shield = 40 * h.taken.count("aegis")
            game.player.shield_t = 1800
        game.emit("wave", game.player.cx, game.player.cy, wave=h.wave, size=len(h.queue))


def choose(game, index: int) -> bool:
    h = game.horde
    if not h.offer or index not in (0, 1):
        return False
    name = h.offer[index]
    h.offer = []
    h.taken.append(name)
    game.upgrades[name] = game.upgrades.get(name, 0) + 1
    p = game.player
    if name == "vitality":
        p.max_hp += 25
        p.hp = p.max_hp
    elif name == "mags":
        for i in range(1, 5):
            game.ammo_cap[i] = game.ammo_cap[i] * 3 // 2
            if game.owned[i]:
                game.ammo[i] = game.ammo_cap[i]
    elif name == "boots":
        p.boots = True
    elif name == "arsenal":
        slot = game.owned.index(False)
        game.owned[slot] = True
        game.ammo[slot] = game.ammo_cap[slot]
        game.weapon = slot
    game.emit("upgrade", p.cx, p.cy, upgrade=name)
    return True


def _unstick(game, hostiles) -> None:
    """Move a hostile that has not budged for STUCK_TICKS back to a vent."""
    h = game.horde
    seen = set()
    for e in hostiles:
        seen.add(e.uid)
        w = h.watch.get(e.uid)
        if w is None or abs(w[0] - e.x) > 8 or abs(w[1] - e.y) > 8:
            h.watch[e.uid] = [e.x, e.y, 0]
            continue
        w[2] += 1
        if w[2] > STUCK_TICKS:
            spots = [(n.cx, n.bottom) for n in game.enemies if n.kind == "nest"]
            if spots and e.kind != "stinger":
                x, y = game.rng.choice(spots)
                e.x, e.y = x - e.w // 2, y - e.h
                e.vx = e.vy = 0
                game.emit("enemy_spawn", e.cx, e.cy, enemy=e.kind)
            h.watch[e.uid] = [e.x, e.y, 0]
    for uid in [u for u in h.watch if u not in seen]:
        del h.watch[uid]


def _spawn(game, spec: str) -> None:
    kind, *rest = spec.split()
    p = game.player
    if kind == "stinger" and game.flyer_spawns:
        spots = game.flyer_spawns
    else:
        spots = [(n.cx, n.bottom) for n in game.enemies if n.kind == "nest"]
    far = [s for s in spots if dist(s[0] - p.cx, s[1] - p.cy) > 180] or spots
    x, y = game.rng.choice(far)
    e = game.spawn_enemy(kind, x, y, tuple(rest))
    e.hp = e.max_hp = e.max_hp * hp_pct(game.horde.wave) // 100
    e.alerted = True
    e.state = {"crawler": "chase", "stinger": "stalk", "strider": "stalk"}.get(kind, e.state)
    e.surface = "air" if kind == "stinger" else "floor"
    game.emit("enemy_spawn", e.cx, e.cy, enemy=kind)
