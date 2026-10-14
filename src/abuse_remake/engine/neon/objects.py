"""Neon world objects: pickups, save consoles, switches and doors, keycard gates, elevators,
teleporters, the exit lift and energy-floor hazards."""

from __future__ import annotations

from dataclasses import dataclass

from .fixed import px
from .physics import step_y
from .tilemap import BREAK, DOOR, EMPTY, HAZARD, ONEWAY, SHIFT, SOLID

PICKUP_LIFE = 900  # dropped supplies fade after 30 s; placed ones stay
HAZARD_PERIOD, HAZARD_ON, HAZARD_WARN = 120, 40, 24  # ticks; the floor is live for the last 40


@dataclass
class Pickup:
    kind: str
    x: int  # centre
    y: int  # bottom
    vy: int = 0
    ry: int = 0
    life: int = -1
    spot: int = -1  # Horde: the respawn spot it came from
    placed: bool = False  # authored in the map: floats where it was put


@dataclass
class Console:
    x: int
    y: int
    used: bool = False


@dataclass
class Switch:
    group: str
    x: int
    y: int
    on: bool = False
    timer: int = 0  # 0: stays open; otherwise the door closes after this many ticks


@dataclass
class DoorGroup:
    group: str
    tiles: list
    open: bool = False
    close_in: int = 0
    key: str = ""  # "red" / "gold" for keycard gates


@dataclass
class Elevator:
    x: int
    y: int  # top surface
    top: int
    bottom: int
    home: int
    w: int = 48
    target: int = -1
    idle: int = 0
    ride: int = 0
    speed: int = 2
    armed: bool = True  # a rider must step off after a trip before it moves again

    @property
    def moving(self) -> bool:
        return self.target >= 0 and self.target != self.y


@dataclass
class Pad:
    x: int  # centre
    y: int  # bottom
    pair: str


def pickup_box(item: Pickup) -> tuple[int, int, int, int]:
    return item.x - 9, item.y - 18, 18, 18


def update_pickups(game) -> None:
    p = game.player
    keep = []
    for item in game.pickups:
        if item.life > 0:
            item.life -= 1
            if item.life == 0:
                continue
        if not item.placed and not _supported(game, item):
            item.vy = min(px(8), item.vy + px(0.5))
            item.ry += item.vy
            dy = item.ry // 256
            item.ry -= dy * 256
            for _ in range(dy):
                if _supported(game, item):
                    item.vy = 0
                    break
                item.y += 1
        x, y, w, h = pickup_box(item)
        if p.alive and p.x < x + w and p.x + p.w > x and p.y < y + h and p.bottom > y and game.collect(item):
            game.emit("pickup", item.x, item.y - 8, pickup=item.kind)
            continue
        keep.append(item)
    game.pickups = keep


def _supported(game, item: Pickup) -> bool:
    if item.y & 15:
        return False
    g = game.grid
    tx, ty = item.x >> SHIFT, item.y >> SHIFT
    return g.at(tx, ty) in (SOLID, ONEWAY, BREAK, DOOR) or g.ladder_top(tx, ty)


def open_door(game, door: DoorGroup, timer: int = 0) -> None:
    if not door.open:
        door.open = True
        for tx, ty in door.tiles:
            game.grid.set(tx, ty, EMPTY)
        tx, ty = door.tiles[len(door.tiles) // 2]
        game.emit("door_open", tx * 16 + 8, ty * 16 + 8, group=door.group)
    door.close_in = timer


def update_doors(game) -> None:
    for door in game.doors:
        if door.open and door.close_in:
            door.close_in -= 1
            if door.close_in == 0:
                if _door_blocked(game, door):
                    door.close_in = 10
                    continue
                door.open = False
                for tx, ty in door.tiles:
                    game.grid.set(tx, ty, DOOR)
                tx, ty = door.tiles[len(door.tiles) // 2]
                game.emit("door_close", tx * 16 + 8, ty * 16 + 8, group=door.group)
        if door.key and not door.open:
            p = game.player
            for tx, ty in door.tiles:
                if abs(p.cx - (tx * 16 + 8)) < 22 and p.y - 8 < ty * 16 + 16 and p.bottom + 8 > ty * 16:
                    if door.key in p.keys:
                        open_door(game, door)
                    elif game.frames - game.locked_at > 45:
                        game.locked_at = game.frames
                        game.emit("locked", p.cx, p.y, key=door.key)
                    break


def _door_blocked(game, door: DoorGroup) -> bool:
    bodies = [game.player, *game.enemies]
    for tx, ty in door.tiles:
        for b in bodies:
            if b.x < tx * 16 + 16 and b.x + b.w > tx * 16 and b.y < ty * 16 + 16 and b.bottom > ty * 16:
                return True
    return False


def update_elevators(game) -> None:
    riders = [game.player, *[e for e in game.enemies if e.surface == "floor"]]
    for i, el in enumerate(game.elevators):
        on = [b for b in riders if _standing_on(b, el)]
        player_on = game.player in on
        if el.target < 0 or el.target == el.y:
            el.target = -1
            if player_on and el.armed:
                el.ride += 1
                if el.ride >= 8:
                    el.target = el.top if el.y != el.top else el.bottom
                    el.ride = 0
                    game.emit("elevator", el.x + el.w // 2, el.y, up=el.target < el.y)
            elif not player_on:
                el.armed = True
                el.ride = 0
                el.idle += 1
                if el.idle > 150 and el.y != el.home:
                    el.target = el.home
                    el.idle = 0
            continue
        el.idle = 0
        dy = max(-el.speed, min(el.speed, el.target - el.y))
        if dy < 0 and any(not free_above(game, b, -dy) for b in on):
            el.target = -1  # a rider would be crushed against the ceiling: stop here
            continue
        el.y += dy
        for b in on:
            step_y(game, b, dy)  # with collision both ways: a rider over a solid edge stays on it
            b.riding = i
        if el.y == el.target:
            el.target = -1
            el.armed = game.player not in on
            game.emit("elevator_stop", el.x + el.w // 2, el.y)


def free_above(game, b, n: int) -> bool:
    return not game.grid.rect_hits(b.x, b.y - n, b.w, n, (SOLID, BREAK, DOOR))


def _standing_on(b, el: Elevator) -> bool:
    if getattr(b, "dash_t", 0) or getattr(b, "climbing", False):
        return False
    return b.bottom == el.y and b.x < el.x + el.w and b.x + b.w > el.x


def call_elevator(game, p) -> bool:
    for el in game.elevators:
        if abs(p.cx - (el.x + el.w // 2)) > 56:
            continue
        for end in (el.top, el.bottom):
            if abs(p.bottom - end) < 28 and el.y != end and not el.moving:
                el.target = end
                el.armed = True
                game.emit("elevator", el.x + el.w // 2, el.y, up=end < el.y)
                return True
    return False


def update_pads(game) -> None:
    p = game.player
    if game.pad_cd:
        game.pad_cd -= 1
        return
    if not p.alive:
        return
    for pad in game.pads:
        if abs(p.cx - pad.x) < 12 and abs(p.bottom - pad.y) < 6:
            dest = next((q for q in game.pads if q.pair == pad.pair and q is not pad), None)
            if dest is None:
                return
            game.emit("teleport", p.cx, p.cy, x2=dest.x, y2=dest.y - p.h // 2)
            p.x, p.y = dest.x - p.w // 2, dest.y - p.h
            p.vx = p.vy = p.rx = p.ry = 0
            p.climbing = False
            game.pad_cd = 45
            return


def hazard_live(game) -> bool:
    return game.frames % HAZARD_PERIOD >= HAZARD_PERIOD - HAZARD_ON


def hazard_warning(game) -> bool:
    f = game.frames % HAZARD_PERIOD
    return HAZARD_PERIOD - HAZARD_ON - HAZARD_WARN <= f < HAZARD_PERIOD - HAZARD_ON


def update_hazards(game) -> None:
    if not game.hazards or not hazard_live(game):
        return
    p = game.player
    if p.alive and game.grid.rect_hits(p.x, p.y, p.w, p.h, (HAZARD,)):
        p.hurt(game, 10, p.cx, "shock")
