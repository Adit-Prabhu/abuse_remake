"""What a playing agent may see: the original screen and HUD, in semantic form.

Information boundary (docs/information-boundary.md):
- only objects whose picture overlaps the 316x162 play view, and only those the original
  draws in play (``dev_draw`` objects such as sensors and gates are invisible; hidden ants are
  a ``dev_draw`` type until they drop);
- each object's kind, position and visible state (door open or closed, switch on or off,
  alien hanging or running), never its HP, AI state, links, timers or the random table;
- the player's HUD: health, weapons owned and ammo, the current weapon;
- the tiles on screen, classified from their collision outlines (solid, slope, partial, empty);
- events the player would see or hear on screen, plus their own pickups and damage.

Positions are level pixels, as on the original's automap (``abuse/src/automap.c``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..engine.cmath import cdiv
from ..engine.geometry import FORE_H, FORE_W

SCHEMA = "abuse-obs-1"
WEAPON_NAMES = ("laser", "grenade", "rocket", "firebomb", "plasma", "saber", "frisbee")

# public kind for each visible type (types not listed are never shown)
KINDS = {
    "ANT_ROOF": "alien", "SPRAY_GUN": "turret", "BOLDER": "boulder", "SMALL_BOLDER": "rock",
    "ANT_CRACK": "nest",
    "HEALTH": "health",
    "MBULLET_ICON5": "ammo_laser", "MBULLET_ICON20": "ammo_laser", "GRENADE_ICON2": "ammo_grenade",
    "GRENADE_ICON10": "ammo_grenade", "ROCKET_ICON2": "ammo_rocket", "ROCKET_ICON5": "ammo_rocket",
    "FBOMB_ICON1": "ammo_firebomb", "FBOMB_ICON5": "ammo_firebomb",
    "SWITCH": "switch", "SWITCH_ONCE": "switch",
    "SWITCH_DOOR": "door", "TRAP_DOOR2": "door", "TRAP_DOOR3": "door",
    "FORCE_FIELD": "force_field",
    "HIDDEN_WALL1": "wall_block", "HIDDEN_WALL2": "wall_block", "HIDDEN_WALL3": "wall_block",
    "HIDDEN_WALL4": "wall_block", "HIDDEN_WALL5": "wall_block", "HIDDEN_WALL_2x2": "wall_block",
    "HIDDEN_WALL_3WAL": "wall_block", "HIDDEN_WALL_3FLR": "wall_block",
    "TELE2": "teleporter", "TP_DOOR": "door_teleporter", "RESTART_POSITION": "console",
    "NEXT_LEVEL": "exit", "SMART_PLAT_SMALL": "lift",
    "SHOTGUN_BULLET": "projectile", "GRENADE": "projectile", "ROCKET": "projectile", "FIREBOMB": "projectile",
}
ID_PREFIX = {"alien": "E", "turret": "E", "boulder": "E", "rock": "R", "nest": "N", "health": "H",
             "ammo_laser": "A", "ammo_grenade": "A", "ammo_rocket": "A", "ammo_firebomb": "A",
             "switch": "S", "door": "D", "force_field": "F", "wall_block": "W", "teleporter": "T",
             "door_teleporter": "T", "console": "C", "exit": "X", "lift": "L", "projectile": "P"}
ALIEN_STATES = {"hanging": "hanging", "fall_start": "falling", "falling": "falling", "landing": "landing",
                "stopped": "standing", "running": "running", "pounce_wait": "crouching", "turn_around": "turning",
                "run_jump": "jumping", "run_jump_fall": "jumping", "start_run_jump": "jumping",
                "fire_wait": "aiming", "weapon_fire": "firing", "ceil_fire": "firing", "top_walk": "on_ceiling",
                "jump_up": "jumping", "flinch_up": "hurt", "flinch_down": "hurt", "dead": "dying",
                "blown_back_dead": "dying"}
DOOR_STATES = {"stopped": "closed", "running": "opening", "blocking": "open", "walking": "closing"}


@dataclass
class IdMap:
    """Stable labels (E1, H2, ...) given the first time an object is seen."""

    labels: dict[int, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def label(self, uid: int, kind: str) -> str:
        got = self.labels.get(uid)
        if got is None:
            p = ID_PREFIX[kind]
            n = self.counters.get(p, 0) + 1
            self.counters[p] = n
            got = self.labels[uid] = f"{p}{n}"
        return got


_TILE_CLASS: dict[int, str] = {}


def tile_class(tilemap, num: int) -> str:
    """'.' open, '#' solid, '/' or '\\' slope, '_' low ledge, '^' overhang, '+' partial."""
    got = _TILE_CLASS.get(num)
    if got is not None:
        return got
    segs = tilemap.segments.get(num)
    if not num or not segs:
        _TILE_CLASS[num] = "."
        return "."
    pts = []
    for s in segs:
        pts.append((s[0], s[1]))
    cols = 6
    rows = 3
    filled = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            filled[r][c] = _inside(pts, (c + 0.5) * FORE_W / cols, (r + 0.5) * FORE_H / rows)
    total = sum(sum(row) for row in filled)
    if total == 0:
        cls = "."
    elif total == cols * rows:
        cls = "#"
    else:
        tops = []
        for c in range(cols):
            top = next((r for r in range(rows) if filled[r][c]), rows)
            tops.append(top)
        if all(filled[rows - 1]) and not any(filled[0]):
            if tops[0] < tops[-1]:
                cls = "\\"
            elif tops[0] > tops[-1]:
                cls = "/"
            else:
                cls = "_"
        elif all(filled[0]) and not any(filled[rows - 1]):
            cls = "^"
        else:
            cls = "+"
    _TILE_CLASS[num] = cls
    return cls


def _inside(pts, x, y) -> bool:
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xc:
                inside = not inside
    return inside


def view_rect(game) -> tuple[int, int, int, int]:
    v = game.view
    return v.xoff(), v.yoff(), v.cx2 - v.cx1 + 1, v.cy2 - v.cy1 + 1


def tile_grid(game, x0: int, y0: int, w: int, h: int) -> dict:
    tm = game.world.tiles
    c0, r0 = cdiv(x0, FORE_W), cdiv(y0, FORE_H)
    c1, r1 = cdiv(x0 + w - 1, FORE_W), cdiv(y0 + h - 1, FORE_H)
    rows = []
    for r in range(r0, r1 + 1):
        rows.append("".join(tile_class(tm, tm.get(c, r)) for c in range(c0, c1 + 1)))
    return {"origin_x": c0 * FORE_W, "origin_y": r0 * FORE_H, "cell_w": FORE_W, "cell_h": FORE_H, "rows": rows}


def visible_objects(game, ids: IdMap, x0, y0, w, h) -> list[dict]:
    p = game.player
    out = []
    from ..engine.behaviors.lispfns import activated

    for o in game.world.objects:
        if o.deleted or o is p:
            continue
        kind = KINDS.get(o.ctype.name)
        if kind is None:
            continue
        if kind == "projectile":
            owner = o.objs[0] if o.objs else None
            if owner is p or (owner is not None and owner.objs and owner.objs[0] is p):
                continue  # the player's own shots are not threats
        if kind.startswith("ammo") and not activated(o):
            continue  # on_draw: only drawn when activated
        if kind == "force_field" and not activated(o):
            continue  # ff_draw draws nothing while it is off
        x1, y1, x2, y2 = o.picture_space()
        if x2 < x0 or x1 > x0 + w - 1 or y2 < y0 or y1 > y0 + h - 1:
            continue
        cx, cy = o.x, o.y - cdiv(o.picture_height(), 2)
        entry = {"id": ids.label(o.uid, kind), "kind": kind, "x": o.x, "y": o.y,
                 "dx": o.x - p.x, "dy": o.y - p.y, "dist": int(((cx - p.x) ** 2 + (cy - (p.y - 20)) ** 2) ** 0.5)}
        if kind == "alien":
            entry["state"] = ALIEN_STATES.get(o.state, "moving")
            entry["facing"] = "right" if o.direction > 0 else "left"
        elif kind == "turret":
            entry["state"] = "folded" if o.state == "stopped" else "active"
        elif kind in ("door",):
            entry["state"] = DOOR_STATES.get(o.state, "closed")
        elif kind == "switch":
            entry["state"] = "on" if o.state == "running" else "off"
        elif kind == "wall_block":
            entry["damaged"] = o.current_frame > 0
        elif kind == "projectile":
            entry["vx"], entry["vy"] = o.xvel, o.yvel
        elif kind == "lift":
            entry["moving"] = o.aistate == 3
        out.append(entry)
    out.sort(key=lambda e: e["dist"])
    return out


EVENT_KINDS = {"pickup", "enemy_killed", "wall_destroyed", "door", "switch", "checkpoint_saved",
               "teleported", "enemy_fired", "enemy_revealed", "enemy_spawned", "explosion", "level_complete",
               "player_died"}


def visible_events(game, events, ids: IdMap, x0, y0, w, h) -> list[dict]:
    out = []
    p = game.player
    for e in events:
        if e.kind == "damage":
            if e.data["target"] == p.uid:
                out.append({"type": "player_hurt", "amount": e.data["amount"], "by": KINDS.get(e.data["source"] or "", "unknown")})
            continue
        if e.kind not in EVENT_KINDS:
            continue
        x, y = e.data.get("x"), e.data.get("y")
        if x is not None and y is not None and not (x0 - 40 <= x <= x0 + w + 40 and y0 - 40 <= y <= y0 + h + 40):
            continue  # off screen: the player would not see it
        item = {"type": e.kind}
        for k in ("item", "type", "radius", "on", "opening"):
            if k in e.data and k != "type":
                item[k] = e.data[k]
        if "uid" in e.data and e.data["uid"] in ids.labels:
            item["id"] = ids.labels[e.data["uid"]]
        out.append(item)
    return out


def player_view(game) -> dict:
    p, v = game.player, game.view
    ammo = {}
    for i, name in enumerate(WEAPON_NAMES[: v.total_weapons]):
        if v.weapons[i] != -1:
            ammo[name] = v.weapons[i]
    state = p.state
    if p.aistate >= 2 or state in ("dead",):
        posture = "dead"
    elif state in ("flinch_up", "flinch_down"):
        posture = "hurt"
    elif p.gravity():
        posture = "in_air"
    else:
        posture = "on_ground"
    return {"x": p.x, "y": p.y, "hp": p.hp, "facing": "right" if p.direction > 0 else "left",
            "posture": posture, "weapon": WEAPON_NAMES[v.current_weapon], "ammo": ammo,
            "teleporting": bool(p.lvars.get("is_teleporting"))}


def build_observation(game, ids: IdMap, events, tick: int, ticks_left: int, status: str,
                      last_result: dict | None) -> dict:
    x0, y0, w, h = view_rect(game)
    return {
        "schema": SCHEMA,
        "tick": tick,
        "ticks_left": ticks_left,
        "status": status,
        "player": player_view(game),
        "view": {"x": x0, "y": y0, "w": w, "h": h},
        "tiles": tile_grid(game, x0, y0, w, h),
        "objects": visible_objects(game, ids, x0, y0, w, h),
        "events": visible_events(game, events, ids, x0, y0, w, h),
        "last_result": last_result or {"accepted": True, "action": None, "error": None},
    }
