"""``game_object``: the physics and state machine every Abuse object shares.

A line-for-line port of historicalsource/abuse@01cce80:
- fields and setters:     abuse/inc/extend.hpp (``simple_object``), objects.hpp
- tick / mover / try_move / float_tick / bmove: abuse/src/objects.c:744-1487
- states and frames:      objects.c:263-318 (next_sequence), 575-602, 1109-1133
- damage:                 objects.c:441-552
- character types:        abuse/inc/chars.hpp, abuse/src/chars.c

Narrow C types are kept: the fractional parts and ``flags`` are ``uchar``, ``hp`` and
``aistate`` are ``ushort``, ``direction`` is ``schar``. ``sf*`` mirrors the original's uchar
return type, so a negative fraction wraps (``-F & 0xFF``), exactly as in the C.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cmath import u8, u16

if TYPE_CHECKING:
    from .world import CharType, World

BLOCKED_LEFT, BLOCKED_RIGHT, BLOCKED_UP, BLOCKED_DOWN = 1, 2, 4, 8
FLAG_JUST_HIT, FLAG_JUST_BLOCKED, FLOATING_FLAG, KNOWN_FLAG = 1, 2, 4, 8


class GameObject:
    __slots__ = (
        "world", "ctype", "uid", "x", "y", "last_x", "last_y", "direction", "active", "state",
        "current_frame", "fade_dir", "fade_count", "fade_max", "flags", "grav_on", "targetable_on",
        "xvel", "yvel", "xacel", "yacel", "fx", "fy", "fxvel", "fyvel", "fxacel", "fyacel",
        "aitype", "aistate", "aistate_time", "hp", "mp", "fmp", "frame_dir", "objs", "lights",
        "controller", "lvars", "deleted", "level_index",
    )

    def __init__(self, world: World, ctype: CharType, x: int = 0, y: int = 0):
        # simple_object::simple_object (extend.c)
        self.world = world
        self.ctype = ctype
        self.uid = world.next_uid()
        self.x = x
        self.y = y
        self.last_x = x
        self.last_y = y
        self.direction = 1
        self.active = 0
        self.state = "stopped"
        self.current_frame = 0
        self.fade_dir = 0
        self.fade_count = 0
        self.fade_max = 16
        self.flags = 0
        self.grav_on = 1
        self.targetable_on = 1
        self.xvel = self.yvel = self.xacel = self.yacel = 0
        self.fx = self.fy = self.fxvel = self.fyvel = self.fxacel = self.fyacel = 0
        self.aitype = 0
        self.aistate = 0
        self.aistate_time = 0
        self.hp = self.mp = self.fmp = 0
        self.frame_dir = 1
        self.objs: list[GameObject] = []
        self.lights: list = []
        self.controller = None
        self.lvars = dict.fromkeys(ctype.vars, 0)
        self.deleted = False
        self.level_index = 0  # 1-based number in the level file, 0 for objects made in play

    def __repr__(self) -> str:
        return f"<{self.ctype.name}#{self.uid} {self.x},{self.y} {self.state}>"

    # --- flags from the character type (objects.hpp) ---
    def hurtable(self) -> bool:
        return "hurtable" in self.ctype.cflags

    def pushable(self) -> bool:
        return "pushable" in self.ctype.cflags

    def can_block(self) -> bool:
        return "can_block" in self.ctype.cflags

    def stoppable(self) -> bool:
        return "stoppable" in self.ctype.cflags

    def hurt_all(self) -> bool:
        return "hurt_all" in self.ctype.cflags

    def ability(self, name: str) -> int:
        return self.ctype.abilities[name]

    # --- narrow setters (extend.hpp) ---
    def set_fxvel(self, v): self.fxvel = u8(v)
    def set_fyvel(self, v): self.fyvel = u8(v)
    def set_fxacel(self, v): self.fxacel = u8(v)
    def set_fyacel(self, v): self.fyacel = u8(v)
    def set_fx(self, v): self.fx = u8(v)
    def set_fy(self, v): self.fy = u8(v)
    def set_hp(self, v): self.hp = u16(v)
    def set_aistate(self, v): self.aistate = u16(v)
    def set_aistate_time(self, v): self.aistate_time = u16(v)
    def set_aitype(self, v): self.aitype = u8(v)
    def set_fade_count(self, v): self.fade_count = u8(v)
    def set_flags(self, v): self.flags = u8(v)

    def sfxvel(self): return self.fxvel if self.xvel >= 0 else u8(-self.fxvel)
    def sfyvel(self): return self.fyvel if self.yvel >= 0 else u8(-self.fyvel)
    def sfxacel(self): return self.fxacel if self.xacel >= 0 else u8(-self.fxacel)
    def sfyacel(self): return self.fyacel if self.yacel >= 0 else u8(-self.fyacel)

    def gravity(self) -> int:
        return self.grav_on

    def set_gravity(self, v) -> None:
        self.grav_on = u8(v)

    def floating(self) -> bool:
        return bool(self.flags & FLOATING_FLAG)

    def stop_x(self):
        self.xvel = 0
        self.fxvel = 0
        self.xacel = 0
        self.fxacel = 0

    def stop(self):
        self.xvel = self.yvel = self.xacel = self.yacel = 0
        self.fxvel = self.fyvel = self.fxacel = self.fyacel = 0

    # --- links (extend.c add_object / remove_object) ---
    def add_object(self, o: GameObject | None) -> None:
        if o is None or o in self.objs:
            return
        o.set_flags(o.flags | KNOWN_FLAG)
        self.objs.append(o)

    def remove_object(self, o: GameObject) -> None:
        if o in self.objs:
            self.objs.remove(o)

    def total_objects(self) -> int:
        return len(self.objs)

    def get_object(self, i: int) -> GameObject:
        return self.objs[i]

    # --- frames and states ---
    def has_sequence(self, state: str) -> bool:
        return state in self.ctype.sequences

    def sequence(self):
        return self.ctype.sequences[self.state]

    def figure(self):
        return self.ctype.sequences[self.state][self.current_frame]

    def total_frames(self) -> int:
        return len(self.ctype.sequences[self.state])

    def x_center(self) -> int:
        return self.figure().xcfg

    def picture_width(self) -> int:
        return self.figure().width

    def picture_height(self) -> int:
        return self.figure().height

    def picture_space(self) -> tuple[int, int, int, int]:
        fig = self.figure()
        xc, w, h = fig.xcfg, fig.width, fig.height
        x1 = self.x - xc if self.direction > 0 else self.x - (w - xc - 1)
        return x1, self.y - h + 1, x1 + w - 1, self.y

    def tx(self, px: int) -> int:
        return px - self.x_center() if self.direction > 0 else self.x_center() - px

    def ty(self, py: int) -> int:
        return py - self.picture_height() + 1

    def set_state(self, state: str, frame_direction: int = 1) -> None:
        self.state = state if self.has_sequence(state) else "stopped"
        self.current_frame = 0
        if frame_direction != 1:  # objects.c:1129: only non-default directions are stored
            self.frame_dir = frame_direction
        self.frame_advance()

    def frame_advance(self) -> None:
        ad = self.figure().advance
        if ad:
            xv = ad if self.direction > 0 else -ad
            _, xv, _ = self.try_move(self.x, self.y, xv, 0, 3)
            self.x += xv

    def next_picture(self) -> bool:
        ret = True
        if self.frame_dir > 0:
            self.current_frame += 1
            if self.current_frame >= self.total_frames():
                self.current_frame = 0
                self.next_sequence()
                ret = False
        else:
            self.current_frame -= 1
            if self.current_frame < 0:
                self.current_frame = self.total_frames() - 1
                self.next_sequence()
                ret = False
        self.frame_advance()
        return ret

    def next_sequence(self) -> None:
        fn = self.ctype.next_state_fun
        if fn is not None:
            fn(self)
            return
        s = self.state
        if s == "dieing":
            self.set_state("dead")
        elif s == "end_run_jump":
            self.set_state("running")
        elif s in ("dead", "run_jump", "run_jump_fall", "running"):
            self.set_state(s)
        elif s == "start_run_jump":
            self.yvel = self.ability("jump_yvel")
            if self.xvel > 0:
                self.xvel = self.ability("jump_xvel")
            elif self.xvel < 0:
                self.xvel = -self.ability("jump_xvel")
            self.xacel = 0
            self.fxacel = 0
            self.set_gravity(1)
            self.set_state("run_jump")
        elif s in ("flinch_up", "flinch_down"):
            if self.gravity() and self.has_sequence("end_run_jump"):
                self.set_state("end_run_jump")
            else:
                self.set_state("stopped")
        else:
            self.set_state("stopped")

    def defaults(self) -> None:
        # objects.c:1098: default_simple.hp() is 0, so any non-zero start_hp is applied
        self.set_state(self.state)
        start_hp = self.ability("start_hp")
        if start_hp != 0:
            self.set_hp(start_hp)

    # --- health ---
    def alive(self) -> bool:
        return not (self.state == "dead" or self.hp <= 0)

    def add_hp(self, amount: int) -> None:
        if self.controller is not None and self.controller.god:
            return
        n = self.hp + amount
        n = max(0, min(n, self.world.max_hp))
        self.set_hp(n)

    def do_flinch(self, from_obj) -> None:
        if self.world.rng.jrandom(2) and self.has_sequence("flinch_down"):
            self.set_state("flinch_down")
        elif self.has_sequence("flinch_up"):
            self.set_state("flinch_up")

    def do_damage(self, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
        fn = self.ctype.damage_fun
        if fn is not None:
            fn(self, amount, from_obj, hitx, hity, push_xvel, push_yvel)
        else:
            self.damage_fun(amount, from_obj, hitx, hity, push_xvel, push_yvel)

    def damage_fun(self, amount, from_obj, hitx, hity, push_xvel, push_yvel) -> None:
        if not self.hurtable() or not self.alive():
            return
        self.add_hp(-amount)
        self.set_flags(self.flags | FLAG_JUST_HIT)
        self.do_flinch(from_obj)
        self.xvel += push_xvel
        if push_yvel < 0 and not self.gravity():
            self.set_gravity(1)
        self.yvel += push_yvel
        c = self.controller
        if c is not None and self.hp <= 0 and from_obj is not None:
            v = from_obj.controller
            if v is not None:
                v.kills += 1
            elif from_obj.total_objects() > 0:
                v = from_obj.get_object(0).controller
                if v is not None and v is not c:
                    v.kills += 1
                else:
                    c.kills -= 1  # suicide
        self.world.note_damage(self, amount, from_obj)

    # --- collision helpers ---
    def try_move(self, x: int, y: int, xv: int, yv: int, checks: int):
        """objects.c:744. Returns (object hit or None, safe xv, safe yv)."""
        if not (xv or yv):
            return None, xv, yv
        level = self.world
        who1 = who2 = None
        if checks & 1:
            x2, y2 = level.tiles.foreground_intersect(x, y, x + xv, y + yv)
            if not self.stoppable():
                who1, x2, y2 = level.boundary_setback(self, x, y, x2, y2)
            else:
                who1, x2, y2 = level.all_boundary_setback(self, x, y, x2, y2)
            xv = x2 - x
            yv = y2 - y
        if checks & 2:
            h = self.picture_height()
            x2, y2 = level.tiles.foreground_intersect(x, y - h + 1, x + xv, y - h + 1 + yv)
            if not self.stoppable():
                who2, x2, y2 = level.all_boundary_setback(self, x, y - h + 1, x2, y2)
            else:
                who2, x2, y2 = level.boundary_setback(self, x, y - h + 1, x2, y2)
            xv = x2 - x
            yv = y2 - y + h - 1
        return (who2 or who1), xv, yv

    # --- physics ---
    def tick(self) -> int:
        """objects.c:899-1096: gravity, acceleration, collision response, slopes."""
        blocked = 0
        _, _, yt = self.try_move(self.x, self.y - 2, 0, 2, 1)  # don't fall through the floor
        self.y = self.y - 2 + yt

        if self.flags & FLAG_JUST_BLOCKED:
            self.set_flags(self.flags - FLAG_JUST_BLOCKED)

        if self.gravity() and not self.floating():
            fya = self.sfyacel() + 200 if self.yacel >= 0 else self.sfyacel() - 200
            self.yacel += fya >> 8
            self.set_fyacel(fya & 255)

        xa, ya, fxa, fya = self.xacel, self.yacel, self.sfxacel(), self.sfyacel()
        if xa or ya or fxa or fya:
            fxv = self.sfxvel() + fxa
            fyv = self.sfyvel() + fya
            self.xvel = self.xvel + xa + (fxv >> 8)
            self.yvel = self.yvel + ya + (fyv >> 8)
            self.set_fxvel(fxv & 0xFF)
            self.set_fyvel(fyv & 0xFF)

        old_vy, old_vx = self.yvel, self.xvel
        if old_vx or old_vy:
            up = 2 if self.yvel <= 0 else 0
            h, xv, yv = self.try_move(self.x, self.y, self.xvel, self.yvel, 1 | up)
            self.xvel, self.yvel = xv, yv
            self.x += xv
            self.y += yv
            if h is not None and self.stoppable():
                return BLOCKED_LEFT | BLOCKED_RIGHT

            if xv != old_vx or yv != old_vy:
                if self.gravity():
                    old_fall_vy = fall_vy = old_vy - self.yvel
                    _, _, fall_vy = self.try_move(self.x, self.y, 0, fall_vy, 1 | up)
                    if old_vy > 0 and fall_vy < old_fall_vy:  # trying to fall, hit the ground
                        blocked |= BLOCKED_DOWN
                        if not self.xvel and self.has_sequence("end_run_jump"):
                            self.xvel = old_vx
                            self.set_state("end_run_jump")
                        else:
                            self.set_state("stopped")
                        if self.state == "run_jump_fall":
                            if self.has_sequence("running"):
                                self.set_state("running")
                            else:
                                self.stop_x()
                                self.set_state("stopped")
                        else:
                            self.yacel = 0
                            self.fyacel = 0
                            self.yvel = 0
                            self.fyvel = 0
                            self.set_gravity(0)
                    else:
                        if old_vy != 0:
                            testx = -1 if old_vx < 0 else 1
                            _, testx, _ = self.try_move(self.x, self.y, testx, 0, 1 | up)
                            if testx == 0:
                                blocked |= BLOCKED_LEFT if old_vx < 0 else BLOCKED_RIGHT
                            elif old_vy < 0:
                                blocked |= BLOCKED_UP
                            elif old_vy > 0:
                                blocked |= BLOCKED_DOWN
                        elif old_vx < 0:
                            blocked |= BLOCKED_LEFT
                        else:
                            blocked |= BLOCKED_RIGHT
                        self.xvel = 0
                        self.fxvel = 0
                        self.yvel = self.yvel + fall_vy  # both branches of the original add fall_vy
                    self.y += fall_vy
                else:  # try to climb the hill
                    ox, oy = self.x, self.y
                    _, _, climb_yvel = self.try_move(self.x, self.y, 0, -5, 3)
                    self.y += climb_yvel
                    climb_xvel = old_vx - self.xvel
                    climb_yvel = -abs(climb_xvel)  # now try a 45 degree slope
                    _, climb_xvel, climb_yvel = self.try_move(self.x, self.y, climb_xvel, climb_yvel, 3)
                    if abs(climb_xvel) > 0:
                        blocked &= ~(BLOCKED_LEFT | BLOCKED_RIGHT)
                        self.x += climb_xvel
                        self.y += climb_yvel
                        self.xvel += climb_xvel
                        self.yvel = 0
                        self.fyvel = 0
                        climb_yvel = abs(climb_xvel) + 5  # put him back on the ground
                        _, _, climb_yvel = self.try_move(self.x, self.y, 0, climb_yvel, 1)
                        if climb_yvel:
                            self.y += climb_yvel
                    else:
                        blocked |= BLOCKED_LEFT if old_vx < 0 else BLOCKED_RIGHT
                        self.set_state("stopped")
                        self.x, self.y = ox, oy
                if self.xvel != old_vx and self.state not in ("run_jump_fall", "end_run_jump"):
                    self.xacel = 0
                    self.fxacel = 0

        if self.yacel == 0 and not self.gravity():  # not falling: make sure he can't
            _, _, nvy = self.try_move(self.x, self.y, 0, self.yvel + 12, 1)
            if nvy > 11:
                if self.state != "run_jump_fall":
                    if self.has_sequence("run_jump_fall"):
                        self.set_state("run_jump_fall")
                    self.set_gravity(1)
            elif nvy:  # descend hills of under 3 pixels
                self.y += nvy
                blocked |= BLOCKED_DOWN
        return blocked

    def mover(self, cx: int, cy: int, button: int) -> int:
        """objects.c:1247-1436: walking, turning, stopping, jumping, speed limits."""
        if self.hp <= 0:
            return self.tick()
        if self.state in ("flinch_up", "flinch_down"):
            cx = cy = 0  # the original also zeroes button, which mover never reads
        ab = self.ability
        if cx:
            if self.state == "stopped":
                if self.has_sequence("running"):
                    if cx > 0:
                        self.direction = 1
                        self.xvel = ab("run_top_speed")
                    else:
                        self.direction = -1
                        self.xacel = -ab("run_top_speed")  # sic: right sets velocity, left accel
                    self.set_state("running")
            elif self.state in ("run_jump", "run_jump_fall"):
                self.direction = 1 if cx > 0 else -1
                self.xacel = ab("start_accel") if cx > 0 else -ab("start_accel")
            elif (cx > 0 > self.direction) or (cx < 0 < self.direction):
                self.direction = -self.direction
        elif not self.gravity() and self.state != "start_run_jump":
            if self.xvel < 0:
                stop_acel = ab("stop_accel")
                if self.xvel + stop_acel >= 0:
                    self.stop_x()
                    if not self.gravity():
                        self.set_state("stopped")
                else:
                    self.xacel = stop_acel
            elif self.xvel > 0:
                stop_acel = -ab("stop_accel")
                if self.xvel + stop_acel <= 0:
                    self.stop_x()
                    if not self.gravity():
                        self.set_state("stopped")
                else:
                    self.xacel = stop_acel
            elif not self.gravity():
                self.xacel = 0
                self.fxacel = 0
                if self.state == "running":
                    self.set_state("stopped")

        if cy < 0 and not self.floating() and not self.gravity():  # jump
            self.set_gravity(1)
            self.yvel = ab("jump_yvel")
            self.set_state("run_jump")
            if self.xvel != 0:
                self.xvel = ab("jump_top_speed") if self.direction > 0 else -ab("jump_top_speed")
            self.xacel = 0

        if self.state == "run_jump" and self.yvel > 0:
            self.set_state("run_jump_fall")

        if cx > 0:
            self.xacel = ab("start_accel")
        elif cx < 0:
            self.xacel = -ab("start_accel")

        if self.state in ("stopped", "end_run_jump"):
            top_speed = ab("walk_top_speed")
        elif self.state == "running":
            top_speed = ab("run_top_speed")
        elif self.state in ("run_jump", "run_jump_fall", "start_run_jump"):
            top_speed = ab("jump_top_speed")
            if not cx:
                top_speed = 0
        else:
            top_speed = 1000

        if abs(self.xvel + self.xacel) > top_speed:
            if self.xacel < 0:
                self.xacel = -top_speed - self.xvel
            else:
                self.xacel = top_speed - self.xvel

        old_state, old_frame = self.state, self.current_frame
        tick_stat = self.tick()
        if not tick_stat and old_state == "start_run_jump":
            self.set_state(old_state)
            self.current_frame = old_frame
            self.next_picture()
        return tick_stat

    def float_tick(self):
        """objects.c:785-897. Returns True, or (blocked, ('tile', tx, ty) | ('object', obj))."""
        if self.hp <= 0 and self.state != "dead":
            self.xacel = 0
            self.fxacel = 0
            if self.has_sequence("dieing"):
                if self.state != "dieing":
                    self.set_state("dieing")
                    self.xvel = 0
            else:
                self.xvel = 0
                self.fxvel = 0
                if self.has_sequence("dead"):
                    self.set_state("dead")
                else:
                    return False
        fxv = self.sfxvel() + self.sfxacel()
        fyv = self.sfyvel() + self.sfyacel()
        xv = self.xvel + self.xacel + (fxv >> 8)
        yv = self.yvel + self.yacel + (fyv >> 8)
        if xv != self.xvel or yv != self.yvel:
            self.xvel, self.yvel = xv, yv
        if fxv != self.sfxvel() or fyv != self.sfyvel():
            self.set_fxvel(fxv & 0xFF)
            self.set_fyvel(fyv & 0xFF)
        if fxv or fyv or xv or yv:
            ffx = self.fx + self.sfxvel()
            ffy = self.fy + self.sfyvel()
            nxv = self.xvel + (ffx >> 8)
            nyv = self.yvel + (ffy >> 8)
            self.set_fx(ffx & 0xFF)
            self.set_fy(ffy & 0xFF)
            old_nxv, old_nyv = nxv, nyv
            hit_object, nxv, nyv = self.try_move(self.x, self.y, nxv, nyv, 3)
            self.x += nxv
            self.y += nyv
            if old_nxv != nxv or old_nyv != nyv:
                lx, ly = self.world.tiles.last_tile_hit
                self.stop()
                ret = 0
                if old_nxv == 0:
                    if old_nyv > 0:
                        ret |= BLOCKED_DOWN
                    elif old_nyv < 0:
                        ret |= BLOCKED_UP
                elif old_nyv == 0:
                    if old_nxv > 0:
                        ret |= BLOCKED_RIGHT
                    elif old_nxv < 0:
                        ret |= BLOCKED_LEFT
                else:
                    tx = 1 if old_nxv > 0 else -1
                    _, tx, _ = self.try_move(self.x, self.y, tx, 0, 3)
                    if not tx:
                        ret |= BLOCKED_RIGHT if old_nxv > 0 else BLOCKED_LEFT
                    else:
                        tx = 0
                    ty = 1 if old_nyv > 0 else -1
                    _, tx, ty = self.try_move(self.x, self.y, tx, ty, 3)
                    if not ty:
                        ret |= BLOCKED_DOWN if old_nyv > 0 else BLOCKED_UP
                    if not ret:
                        ret |= ((BLOCKED_DOWN if old_nyv > 0 else BLOCKED_UP)
                                | (BLOCKED_RIGHT if old_nxv > 0 else BLOCKED_LEFT))
                if hit_object is not None:
                    return ret, ("object", hit_object)
                return ret, ("tile", lx, ly)
            return True
        return True

    def bmove(self, exclude: GameObject | None):
        """objects.c:1441-1487 ballistic move. Returns (hit object or None, hit_wall)."""
        xa, ya, fxa, fya = self.xacel, self.yacel, self.sfxacel(), self.sfyacel()
        if xa or ya or fxa or fya:
            fxv = self.sfxvel() + fxa
            fyv = self.sfyvel() + fya
            self.xvel = self.xvel + xa + (fxv >> 8)
            self.yvel = self.yvel + ya + (fyv >> 8)
            self.set_fxvel(fxv & 0xFF)
            self.set_fyvel(fyv & 0xFF)
        nx = self.x + self.xvel
        nfx = self.fx + self.fxvel
        ny = self.y + self.yvel
        nfy = self.fy + self.fyvel
        nx += nfx >> 8
        ny += nfy >> 8
        ox2, oy2 = nx, ny
        nx, ny = self.world.tiles.foreground_intersect(self.x, self.y, nx, ny)
        ret, nx, ny = self.world.all_boundary_setback(exclude, self.x, self.y, nx, ny)
        self.x, self.y = nx, ny
        self.set_fx(nfx & 0xFF)
        self.set_fy(nfy & 0xFF)
        if ret is not None:
            if not ret.hurtable():
                return None, True
            return ret, False
        return None, (nx != ox2 or ny != oy2)

    # --- per-tick dispatch (objects.c:388-423, 1185-1245) ---
    def decide(self) -> bool:
        ai = self.ctype.ai_fun
        if ai is not None:
            old = self.aistate
            ret = ai(self)
            if self.aistate != old:
                self.aistate_time = 0
            else:
                self.set_aistate_time(self.aistate_time + 1)
            return bool(ret)
        self.move(0, 0, 0)
        return True

    def move(self, cx: int, cy: int, button: int) -> int:
        fn = self.ctype.move_fun
        if fn is not None:
            return fn(self, cx, cy, button)
        return self.mover(cx, cy, button)

    def can_hurt(self, who: GameObject) -> bool:
        # objects.c:425: only fights between a player and something else count
        is_attacker = self.controller is not None
        return who.hurtable() and (is_attacker or who.controller is not None or self.hurt_all())
