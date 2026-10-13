"""Training v2: one lesson per control, each finished by actually doing it.

The training deck runs left to right. Markers (``M`` in the map, ordered by x) are the
places a lesson asks you to reach. The player cannot be hurt in training.
"""

from __future__ import annotations

LESSONS = (
    ("MOVE", "A / D or the arrow keys run", "Run to the glowing marker"),
    ("JUMP", "Space or W jumps. Hold it to jump higher, tap it for a hop", "Jump up the steps"),
    ("LADDER", "At a ladder hold W to climb up or S to climb down. Space lets go", "Climb to the upper deck"),
    ("DROP", "On a thin ledge or a ladder top, hold S and press Space to drop through", "Drop through the grating"),
    ("CROUCH", "Hold S to crouch, and keep holding it to crawl through low vents", "Crawl through the vent"),
    ("AIM + FIRE", "The mouse aims all around you. Left click or J fires", "Destroy the three targets"),
    ("WEAPONS", "Walk over the Scatter Arc. Switch with 1-5, Q or the mouse wheel", "Fire the Scatter Arc"),
    ("DASH", "Shift, F or right click dashes. You cannot be hurt mid-dash", "Dash across the gap"),
    ("SWITCHES", "Press E (or S) at a switch to open its door", "Open the door"),
    ("SAVE", "Press E at a save console. It repairs you and saves your progress", "Save at the console"),
)
MARKER_LESSONS = {0: 0, 1: 1, 2: 2, 4: 3}  # lesson -> marker index


def tick(game) -> None:
    if game.lesson >= len(LESSONS):
        return
    p = game.player
    i = game.lesson
    done = False
    if i in MARKER_LESSONS:
        k = MARKER_LESSONS[i]
        if k < len(game.markers):
            mx, my = game.markers[k]
            done = abs(p.cx - mx) < 20 and abs(p.bottom - my) < 40
    elif i == 3:
        done = any(e["kind"] == "drop" for e in game.events)
    elif i == 5:
        done = game.targets_killed >= 3
    elif i == 6:
        done = any(e["kind"] == "shot" and e.get("weapon") == 1 for e in game.events)
    elif i == 7:
        done = any(e["kind"] == "dash" for e in game.events)
    elif i == 8:
        done = any(d.open for d in game.doors if d.group == "a")
    elif i == 9:
        done = any(e["kind"] == "checkpoint" for e in game.events)
    if done:
        game.lesson += 1
        game.emit("lesson", p.cx, p.y, lesson=i, name=LESSONS[i][0])
        if game.lesson >= len(LESSONS):
            game.status = "won"
            game.emit("training_complete", p.cx, p.y)
