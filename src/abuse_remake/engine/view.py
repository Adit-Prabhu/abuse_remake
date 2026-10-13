"""The player's view: camera, inputs, weapons and ammo.

Port of historicalsource/abuse@01cce80 abuse/src/view.c and abuse/inc/view.hpp:
- construction and defaults: view.c:189-262 (ambient 32, weapon 0 owned with 0 ammo)
- camera offsets: view.c:98-187
- the play area: recalc_local_view_space (view.c:636-676), run at start-up (game.c:1423), with
  xres=319, yres=199 in 320x200 mode (imlib/port/dos4gw/video.c:333-334): one local player
  gets cx 2..317, cy 5..166, a 316x162 view
- ammo and weapons: view.c:40-96, 528-584; number keys and Ctrl/Insert: view.c:586-617
- per-area ambient light and view offsets: view.c:1019-1068
- inputs arrive as a packet and are applied before the step: view.c:447-512, game.c:2650-2670
"""

from __future__ import annotations

from dataclasses import dataclass

from .cmath import cdiv

SHIFT_DOWN_DEFAULT = 15
SHIFT_RIGHT_DEFAULT = 0
VIEW_X1, VIEW_Y1 = 2, 5
VIEW_W, VIEW_H = 316, 162  # h = yres/1 = 199; w = h*320/200 = 318 -> cx clamped to 2..317; cy2 = h-33
MAX_AMMO = 999


@dataclass
class Inputs:
    """One frame of the original controls (view::set_input)."""

    x: int = 0  # -1 left, 1 right
    y: int = 0  # -1 up (jump, climb), 1 down (action)
    b1: int = 0  # special power (right mouse button)
    b2: int = 0  # fire (left mouse button)
    b3: int = 0  # weapon toggle left (mouse button 5 or Ctrl)
    b4: int = 0  # weapon toggle right (Insert)
    pointer_x: int = 0  # aim point in game coordinates
    pointer_y: int = 0


class View:
    def __init__(self, world, focus, player_number: int = 0, total_weapons: int = 7):
        self.world = world
        self.focus = focus
        self.player_number = player_number
        self.cx1, self.cy1 = VIEW_X1, VIEW_Y1
        self.cx2, self.cy2 = self.cx1 + VIEW_W - 1, self.cy1 + VIEW_H - 1
        self.no_xleft = self.no_xright = self.no_ytop = self.no_ybottom = 0
        self.last_x = focus.x if focus else 0
        self.last_y = focus.y if focus else 0
        self.last_last_x, self.last_last_y = self.last_x, self.last_y
        self.pan_x = self.pan_y = 0
        self.shift_down = SHIFT_DOWN_DEFAULT
        self.shift_right = SHIFT_RIGHT_DEFAULT
        self.ambient = 32
        self.god = 0
        self.kills = self.tkills = self.secrets = self.tsecrets = 0
        self.freeze_time = 0
        self.draw_solid = -1
        self.total_weapons = total_weapons
        self.weapons = [-1] * total_weapons
        if total_weapons:
            self.weapons[0] = 0
        self.current_weapon = 0
        self.pending_weapon: int | None = None
        self.x_suggestion = self.y_suggestion = 0
        self.b1_suggestion = self.b2_suggestion = self.b3_suggestion = self.b4_suggestion = 0
        self.pointer_x = self.pointer_y = 0
        if focus is not None:
            focus.controller = self

    # --- inputs ---
    def set_input(self, inp: Inputs) -> None:
        self.x_suggestion = 1 if inp.x > 0 else (-1 if inp.x < 0 else 0)
        self.y_suggestion = 1 if inp.y > 0 else (-1 if inp.y < 0 else 0)
        self.b1_suggestion = 1 if inp.b1 else 0
        self.b2_suggestion = 1 if inp.b2 else 0
        self.b3_suggestion = 1 if inp.b3 else 0
        self.b4_suggestion = 1 if inp.b4 else 0
        # SCMD_SET_INPUT carries the pointer as a signed short (view.c:507-511)
        self.pointer_x = ((inp.pointer_x + 0x8000) & 0xFFFF) - 0x8000
        self.pointer_y = ((inp.pointer_y + 0x8000) & 0xFFFF) - 0x8000

    def apply_pending_weapon_change(self) -> None:
        if self.pending_weapon is not None:  # SCMD_WEAPON_CHANGE (view.c:478-489)
            self.current_weapon = self.pending_weapon
            self.pending_weapon = None

    def select_weapon(self, index: int) -> bool:
        """Number keys 1-7: only a weapon with ammo can be chosen (view.c:590-603)."""
        if 0 <= index < self.total_weapons and self.weapon_total(index) > 0:
            self.pending_weapon = index
            return True
        return False

    def next_weapon(self) -> None:
        c = self.current_weapon
        while c < self.total_weapons - 1:
            c += 1
            if self.weapon_total(c) > 0:
                self.pending_weapon = c
                return
        c = 0
        while c != self.current_weapon:
            if self.weapon_total(c) > 0:
                self.pending_weapon = c
                return
            c += 1

    def last_weapon(self) -> None:
        c = self.current_weapon
        while c >= 1:
            c -= 1
            if self.weapon_total(c) > 0 or c == 0:
                self.pending_weapon = c
                return
        c = self.total_weapons - 1
        while c != self.current_weapon:
            if self.weapon_total(c) > 0 or c == 0:
                self.pending_weapon = c
                return
            c -= 1

    # --- weapons and ammo ---
    def weapon_total(self, wtype: int) -> int:
        if not 0 <= wtype < self.total_weapons:
            return 0
        if self.god:
            return 100
        return 0 if self.weapons[wtype] == -1 else self.weapons[wtype]

    def has_weapon(self, wtype: int) -> bool:
        return bool(self.god) or self.weapons[wtype] != -1

    def give_weapon(self, wtype: int) -> None:
        if 0 <= wtype < self.total_weapons and self.weapons[wtype] == -1:
            self.weapons[wtype] = 0

    def add_ammo(self, wtype: int, total: int) -> None:
        if not 0 <= wtype < self.total_weapons:
            return
        if self.weapons[wtype] == -1:
            return  # can't give ammo for a weapon you don't have
        self.weapons[wtype] = max(0, min(MAX_AMMO, self.weapons[wtype] + total))
        if self.weapon_total(self.current_weapon) == 0 and self.current_weapon:
            if self.world.globals.get("switch_to_powerful", True):  # options.lsp: true
                x = self.total_weapons - 1
                while x > 0 and (x == 3 or self.weapons[x] <= 0):
                    x -= 1
                self.pending_weapon = x
            else:
                self.pending_weapon = 0

    # --- camera ---
    def update_scroll(self) -> None:
        f = self.focus
        if f is None:
            return
        self.last_last_x, self.last_last_y = self.last_x, self.last_y
        if f.x > self.last_x:
            if f.x - self.last_x >= self.no_xright:
                self.last_x = f.x - self.no_xright
        elif f.x < self.last_x:
            if self.last_x - f.x >= self.no_xleft:
                self.last_x = f.x + self.no_xleft
        if f.y > self.last_y:
            if f.y - self.last_y >= self.no_ybottom:
                self.last_y = f.y - self.no_ybottom
        elif f.y < self.last_y:
            if self.last_y - f.y >= self.no_ytop:
                self.last_y = f.y + self.no_ytop

    def xoff(self) -> int:
        if self.focus is None:
            return self.pan_x
        x = self.last_x - cdiv(self.cx2 - self.cx1 + 1, 2) + self.shift_right + self.pan_x
        return max(0, x)

    def yoff(self) -> int:
        if self.focus is None:
            return self.pan_y
        y = self.last_y - cdiv(self.cy2 - self.cy1 + 1, 2) - self.shift_down + self.pan_y
        return max(0, y)

    def interpolated_xoff(self) -> int:
        x = cdiv(self.last_last_x + self.last_x, 2) - cdiv(self.cx2 - self.cx1 + 1, 2) \
            + self.shift_right + self.pan_x
        return max(0, x)

    def interpolated_yoff(self) -> int:
        y = cdiv(self.last_y + self.last_last_y, 2) - cdiv(self.cy2 - self.cy1 + 1, 2) \
            - self.shift_down + self.pan_y
        return max(0, y)

    def mouse_to_game(self, sx: int, sy: int) -> tuple[int, int]:
        """game::mouse_to_game (game.c:288-311) for a point inside this view."""
        return sx - self.cx1 + self.xoff(), sy - self.cy1 + self.yoff()

    def configure_for_area(self, a) -> None:
        if a.ambient >= 0 and a.ambient != self.ambient:
            if self.ambient > a.ambient:
                self.ambient = max(a.ambient, self.ambient - a.ambient_speed)
            else:
                self.ambient = min(a.ambient, self.ambient + a.ambient_speed)
        if a.view_xoff != self.pan_x:
            if self.pan_x > a.view_xoff:
                self.pan_x = max(a.view_xoff, self.pan_x - a.view_xoff_speed)
            else:
                self.pan_x = min(a.view_xoff, self.pan_x + a.view_xoff_speed)
        if a.view_yoff != self.pan_y:
            if self.pan_y > a.view_yoff:
                self.pan_y = max(a.view_yoff, self.pan_y - a.view_yoff_speed)
            else:
                self.pan_y = min(a.view_yoff, self.pan_y + a.view_yoff_speed)
