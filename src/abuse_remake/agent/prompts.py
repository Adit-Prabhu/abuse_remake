"""Prompts for the model-driven player.

The system prompt holds only what a player could know from the game's manual and controls,
plus the same priors the scripted baseline has built into its rules (head right first, shoot
breakable walls, try switches, heal when low). It holds no map knowledge: nothing about where
the exit, switches or secrets are. ``docs/information-boundary.md`` lists both.

Each turn's prompt is rendered from the observation and legal actions alone, plus the memory
text for the chosen memory condition (``agent/memory.py``).
"""

from __future__ import annotations

SYSTEM = """\
You are playing Level 1 of Abuse (1996), a side-scrolling action game. You control the player
character, who runs, jumps and shoots in any direction.

Goal: reach the level exit (kind "exit") and use it ("use <ID>") before the tick limit. If you
die, the episode ends as a loss. The game runs at 15 ticks per second.

Each turn you see what is on screen. Positions are level pixels: x grows to the right, y grows
downward, and your position is where your feet are. The screen map shows the view as cells of
30x15 pixels: '.' open, '#' solid, '/' and '\\' slopes, '_' low ledge, '^' overhang, '+' partly
solid, '@' you, and a capital letter for an object (the first letter of its ID).

Actions (reply with exactly one string from LEGAL ACTIONS):
- wait: stand still for 8 ticks
- move left / move right: run for 6 ticks
- jump, jump left, jump right
- explore left / explore right: walk toward space you have not seen yet (up to 15 ticks)
- goto <ID>: walk toward a visible object (up to 15 ticks; repeat to keep going)
- use <ID>: walk to a switch, console, teleporter, lift or the exit and press the action key
- attack <ID>: aim at a visible target and fire the current weapon (up to 12 ticks)
- fire left / fire right / fire up / fire down: fire the current weapon that way, at nothing in
  particular (up to 12 ticks)
- weapon <name>: switch weapon
Actions stop early when you are hurt or a new threat appears, so you can react.

Object kinds:
- alien: an ant-like enemy that runs, pounces and spits; dangerous up close. Some hang from
  the ceiling ("hanging").
- turret: a gun in a wall or ceiling; "folded" while inactive. boulder: a rolling hazard you can
  shoot. rock: falling debris. nest: a crack in the wall that aliens come out of.
- projectile: an enemy shot.
- health, ammo_laser, ammo_grenade, ammo_rocket, ammo_firebomb: pickups (walk into them).
- switch (on/off): pressing it may change something elsewhere in the level. door: opens and
  closes. force_field: blocks the way while it is shown. wall_block: a wall showing cracks from
  damage; shoot it to break it.
- teleporter, door_teleporter: move you somewhere else when used. console: a save point.
  lift: a moving platform. exit: ends the level when used.

Weapons: laser (always available; slow with no ammo), grenade, rocket and firebomb (need ammo,
stronger). Ammo counts are in your status line.

General advice: levels are usually explored by heading right first; shoot cracked walls that
block your way, and if a wall or floor stops you, shooting it may reveal that it breaks;
switches may open paths you saw earlier; pick up health when hurt; deal with threats before they
reach you. If an action keeps failing to move you, try something else.
"""

NOTES_RULE = """
You also keep notes for yourself. Each turn, return your complete updated notes in "notes" (at
most 600 characters; longer notes are cut). Only your latest notes are shown to you next turn.
"""

REPLY_RULE = """
Reply with JSON only: {"action": "<one legal action, copied exactly>", "note": "<short reason>"%s}.
"""


def system_prompt(with_notes: bool) -> str:
    extra = ', "notes": "<your notes>"' if with_notes else ""
    return SYSTEM + (NOTES_RULE if with_notes else "") + REPLY_RULE % extra


def decision_schema(with_notes: bool) -> dict:
    props = {"action": {"type": "string"}, "note": {"type": "string"}}
    if with_notes:
        props["notes"] = {"type": "string"}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _signed(v: int) -> str:
    return f"{v:+d}"


def render_screen(obs: dict) -> list[str]:
    t = obs["tiles"]
    grid = [list(row) for row in t["rows"]]
    ox, oy, cw, ch = t["origin_x"], t["origin_y"], t["cell_w"], t["cell_h"]

    def put(x: int, y: int, mark: str) -> None:
        c, r = (x - ox) // cw, (y - 1 - oy) // ch
        if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
            grid[r][c] = mark

    for o in reversed(obs["objects"]):  # nearest drawn last
        put(o["x"], o["y"], o["id"][0])
    p = obs["player"]
    put(p["x"], p["y"], "@")
    return ["".join(row) for row in grid]


def describe_object(o: dict) -> str:
    parts = [o["id"], o["kind"]]
    if "state" in o:
        parts.append(o["state"])
    if "facing" in o:
        parts.append(f"facing {o['facing']}")
    if o.get("damaged"):
        parts.append("damaged")
    if o["kind"] == "projectile":
        parts.append(f"moving {_signed(o.get('vx', 0))},{_signed(o.get('vy', 0))}")
    if o.get("moving"):
        parts.append("moving")
    parts.append(f"dx {_signed(o['dx'])} dy {_signed(o['dy'])} (dist {o['dist']})")
    return " ".join(parts)


def describe_event(e: dict) -> str:
    kind = e["type"]
    if kind == "player_hurt":
        return f"you were hurt ({e.get('amount')} by {e.get('by')})"
    bits = [kind]
    for k in ("id", "item", "on", "opening"):
        if k in e:
            bits.append(f"{k}={e[k]}")
    return " ".join(bits)


def describe_result(last: dict) -> str:
    if last.get("action") is None and last.get("accepted", True):
        return "none yet"
    if last.get("accepted"):
        return f'"{last["action"]}" done ({last.get("ticks", 0)} ticks)'
    return f'"{last.get("action")}" REFUSED: {last.get("error")} (no time passed)'


def render_turn(obs: dict, legal: list[str], memory_text: str = "") -> str:
    p = obs["player"]
    ammo = ", ".join(f"{k} {v}" for k, v in p["ammo"].items()) or "none"
    lines = [
        f"TICK {obs['tick']} ({obs['ticks_left']} ticks left)",
        f"YOU: x {p['x']} y {p['y']}, health {p['hp']}, facing {p['facing']}, {p['posture'].replace('_', ' ')}, "
        f"weapon {p['weapon']}; ammo: {ammo}" + ("; teleporting" if p.get("teleporting") else ""),
        f"LAST ACTION: {describe_result(obs['last_result'])}",
        "EVENTS: " + ("; ".join(describe_event(e) for e in obs["events"]) or "none"),
        f"SCREEN (view x {obs['view']['x']}..{obs['view']['x'] + obs['view']['w'] - 1}, "
        f"y {obs['view']['y']}..{obs['view']['y'] + obs['view']['h'] - 1}):",
        *render_screen(obs),
        "OBJECTS ON SCREEN (nearest first; dx, dy from you in pixels):",
        *([describe_object(o) for o in obs["objects"]] or ["none"]),
    ]
    if memory_text:
        lines += ["", memory_text]
    lines += ["", "LEGAL ACTIONS: " + " | ".join(legal)]
    return "\n".join(lines)
