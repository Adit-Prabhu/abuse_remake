"""Development autopilot for Neon Protocol: map checks and evidence, NOT a playing agent.

It reads the whole map and every enemy (full access), plans over the nav tile graph
(``nav.py``) and turns the plan into ordinary ``NeonInput`` presses. The real physics then
decide whether each jump, climb, drop, elevator ride or teleport actually works. That is the
point: it proves a sector can be finished with the real movement, not only in the tile model.
It is never used by Classic, by the playing-agent interface or by evaluations.
"""

from __future__ import annotations

import heapq

from . import nav
from .fixed import dist
from .player import NeonInput
from .tilemap import LADDER, SHIFT


class Autopilot:
    def __init__(self, game, fight: bool = True, patience: int = 0):
        self.game = game
        self.fight = fight
        self.patience = patience  # ticks to hold back at the start (varies retries after a death)
        self.select: int | None = None  # weapon slot to pass to NeonGame.step
        self.skip: set[tuple[int, int]] = set()
        self.heal_t = 0
        self.plan: list[tuple[int, int]] = []
        self.edge: tuple[tuple[int, int], tuple[int, int]] | None = None
        self.replan = 0
        self.stuck = 0
        self.last_pos = (0, 0)
        self.jump_hold = 0
        self.air_jump_pending = False
        self.release = False
        self.targets: list[tuple[str, int, int]] = []
        self.map_name = None

    # ------------------------------------------------------------ route
    def _route(self) -> list[tuple[str, int, int]]:
        """What to visit, in order: things that unlock progress as nav.solve finds them, then the exit."""
        m = self.game.map
        groups: set[str] = {d.group for d in self.game.doors if d.open}
        boots = self.game.player.boots
        order: list[tuple[str, int, int]] = []
        while True:
            seen = nav.explore(m, groups, boots)
            new = []
            for e in m.entities_of("pickup"):
                k = e.args[0]
                if k.startswith("weapon") and nav.near(seen, e.tx, e.ty) and ("pickup", e.tx, e.ty) not in order:
                    order.append(("pickup", e.tx, e.ty))
            for e in m.entities_of("switch"):
                if e.args[0] not in groups and nav.near(seen, e.tx, e.ty):
                    new.append(("switch", e.tx, e.ty, e.args[0]))
            for e in m.entities_of("pickup"):
                k = e.args[0]
                if k.startswith("key_") and "key:" + k[4:] not in groups and nav.near(seen, e.tx, e.ty):
                    new.append(("pickup", e.tx, e.ty, "key:" + k[4:]))
                if k == "boots" and not boots and nav.near(seen, e.tx, e.ty):
                    new.append(("pickup", e.tx, e.ty, "boots"))
            if not new:
                break
            for kind, tx, ty, unlock in new:
                order.append((kind, tx, ty))
                if unlock == "boots":
                    boots = True
                else:
                    groups.add(unlock)
        if self.game.exit:
            ex, ey = self.game.exit
            order.append(("exit", ex >> SHIFT, (ey >> SHIFT) - 1))
        return order

    def _node(self) -> tuple[int, int]:
        p = self.game.player
        return p.cx >> SHIFT, (p.bottom - 1) >> SHIFT

    def _grid(self) -> nav.NavGrid:
        g = self.game
        opened = {d.group for d in g.doors if d.open}
        opened |= {"key:" + k for k in g.player.keys}
        key = (g.map.name, frozenset(opened), g.player.boots)
        if getattr(self, "_grid_key", None) != key:
            self._grid_key = key
            self._grid_obj = nav.NavGrid(g.map, opened, g.player.boots)
            self._adj: dict = {}
        return self._grid_obj

    def _neighbours(self, grid, node):
        got = self._adj.get(node)
        if got is None:
            got = self._adj[node] = list(dict.fromkeys(grid.neighbours(*node)))
        return got

    def _path(self, start, goal) -> list[tuple[int, int]]:
        """Cheapest path by distance (walking is cheap, jumps cost more), or toward the closest node."""
        grid = self._grid()
        prev = {start: None}
        cost = {start: 0}
        heap = [(0, start)]
        best, best_d = start, 1 << 30
        while heap:
            c, cur = heapq.heappop(heap)
            if c > cost[cur]:
                continue
            d = abs(cur[0] - goal[0]) + abs(cur[1] - goal[1])
            if d < best_d:
                best, best_d = cur, d
            if d <= 1:
                break
            for n in self._neighbours(grid, cur):
                dx, dy = abs(n[0] - cur[0]), n[1] - cur[1]
                if (dy == 0 and dx == 1) or (dx == 0 and abs(dy) == 1):
                    step = 1  # a step along the floor or a ladder rung
                else:
                    step = dx + abs(dy) + (4 if dy < 0 else 2)
                nc = c + step
                if nc < cost.get(n, 1 << 30):
                    cost[n] = nc
                    prev[n] = cur
                    heapq.heappush(heap, (nc, n))
        out, cur = [], best
        while cur is not None:
            out.append(cur)
            cur = prev[cur]
        return out[::-1]

    # ------------------------------------------------------------ the tick
    def step(self) -> NeonInput:
        g = self.game
        p = g.player
        if self.map_name != g.map.name:
            self.map_name = g.map.name
            self.targets = self._route()
            self.plan, self.edge = [], None
        while self.targets and self._reached(self.targets[0]):
            self.targets.pop(0)
            self.plan, self.edge, self.replan = [], None, 0
        aim, fire = self._combat()
        sx, sy = p.shoulder()
        px_, py_ = aim if aim else (sx + 140 * p.facing, sy)
        if self.patience > 0:
            self.patience -= 1
            return NeonInput(fire=fire, px=px_, py=py_)
        self._heal_detour()
        boss = next((e for e in g.enemies if e.kind == "warden" and e.alerted), None)
        if boss is not None and not g.boss_dead:
            return self._boss(boss, fire, px_, py_)
        if not self.targets:
            return NeonInput(fire=fire, px=px_, py=py_, interact=g.frames % 4 == 0)
        kind, tx, ty = self.targets[0]
        here = self._node()
        airborne = not p.grounded and not p.climbing
        if not airborne:
            self.replan -= 1
            if self.replan <= 0 or here not in self.plan:
                self.plan = self._path(here, (tx, ty))
                self.replan = 45
                end = self.plan[-1]
                if abs(end[0] - tx) + abs(end[1] - ty) > 2 and kind != "switch":
                    # blocked: a timed door may have closed again; go back and press its switch
                    for sw in g.switches:
                        door = next((d for d in g.doors if d.group == sw.group), None)
                        if door is not None and not door.open:
                            self.targets.insert(0, ("switch", sw.x >> SHIFT, (sw.y >> SHIFT) - 1))
                            self.plan, self.edge, self.replan = [], None, 0
                            return NeonInput(px=px_, py=py_)
            self.plan = self.plan[self.plan.index(here):] if here in self.plan else [here]
            self.edge = (here, self.plan[1]) if len(self.plan) > 1 else None
        inp = self._execute(kind, (tx, ty), airborne)
        inp.fire, inp.px, inp.py = fire, px_, py_
        moved = (p.x, p.y) != self.last_pos
        self.stuck = 0 if moved else self.stuck + 1
        self.last_pos = (p.x, p.y)
        if self.stuck > 60:
            inp.jump = g.frames % 30 < 18
            if self.stuck > 150:
                self.plan, self.edge, self.stuck, self.replan = [], None, 0, 0
        return inp

    def _reached(self, target) -> bool:
        kind, tx, ty = target
        g = self.game
        if kind == "heal":
            return g.player.hp > 70 or not any(i.kind == "health" and i.x >> SHIFT == tx for i in g.pickups)
        if kind == "switch":
            for s in g.switches:
                if s.x >> SHIFT == tx and (s.y >> SHIFT) - 1 == ty:
                    door = next((d for d in g.doors if d.group == s.group), None)
                    return door is None or door.open
            return True
        if kind == "pickup":
            return not any(i.x >> SHIFT == tx and (i.y >> SHIFT) - 1 == ty for i in g.pickups)
        return False


    def _execute(self, kind, goal, airborne) -> NeonInput:
        g = self.game
        p = g.player
        grid = g.grid
        inp = NeonInput()
        if self.edge is None:
            if kind in ("switch", "exit"):
                inp.interact = g.frames % 6 == 0
            gx = goal[0] * 16 + 8
            if abs(gx - p.cx) > 4:
                inp.x = 1 if gx > p.cx else -1
            return inp
        frm, to = self.edge
        dx, dy = to[0] - frm[0], to[1] - frm[1]
        target_x = to[0] * 16 + 8
        if abs(target_x - p.cx) > 3:
            inp.x = 1 if target_x > p.cx else -1
        on_ladder = grid.at(p.cx >> SHIFT, (p.y + p.h // 2) >> SHIFT) == LADDER or \
            grid.at(p.cx >> SHIFT, (p.bottom - 2) >> SHIFT) == LADDER
        # elevator rides and teleport pads (nav links)
        if to in self._grid().links.get(frm, ()):
            self.jump_hold = 0
            el = next((e for e in g.elevators if e.x <= frm[0] * 16 + 8 < e.x + e.w), None)
            if el is None:
                return inp  # a pad: walking onto it teleports
            inp.x = 0
            centre = el.x + el.w // 2
            here_end = abs(el.y - (frm[1] + 1) * 16) <= 4
            if here_end or el.moving:
                if abs(p.cx - centre) > 6 and not el.moving:
                    inp.x = 1 if centre > p.cx else -1
                return inp  # stand still and ride
            inp.interact = g.frames % 10 == 0  # call it to this end
            return inp
        # ladders
        if dx == 0 and dy != 0 and (on_ladder or grid.at(to[0], to[1]) == LADDER or
                                    grid.at(frm[0], frm[1] + 1) == LADDER):
            if not p.climbing and abs(p.cx - target_x) > 3:
                return inp  # line up with the ladder first
            inp.x = 0
            inp.y = -1 if dy < 0 else 1
            return inp
        if p.climbing:
            feet = (p.bottom - 1) >> SHIFT
            if feet > to[1]:
                inp.x, inp.y = 0, -1  # climb up to the level of the next step first
            elif feet < to[1] and dy > 0:
                inp.x, inp.y = 0, 1
            return inp  # level with it: step off sideways (x without y lets go of the ladder)
        # drop through a ledge, ladder top or elevator
        if dx == 0 and dy > 0:
            inp.x = 0
            inp.y = 1
            inp.jump = g.frames % 3 == 0
            return inp
        # one step along a floor: just walk (crouched under a low ceiling)
        if dy == 0 and abs(dx) == 1:
            nav_grid = self._grid()
            if not nav_grid.tall(to[0], to[1]) or not nav_grid.tall(frm[0], frm[1]):
                inp.y = 1
            return inp
        # jumps and falls
        rise = -dy
        if not airborne and (rise > 0 or abs(dx) > 1) and self.jump_hold == 0:
            if self.release:
                self.release = False
                return inp  # let go of jump for a tick so the next press counts
            self.jump_hold = 4 + min(12, max(0, rise) * 3 + abs(dx))
            self.air_jump_pending = rise > 4
            self.release = True
        if self.jump_hold:
            self.jump_hold -= 1
            inp.jump = True
        elif self.air_jump_pending and airborne and p.vy > -500 and p.air_jumps and not p.jump_held:
            inp.jump = True  # released for at least one tick since the first jump: a fresh press
            self.air_jump_pending = False
            self.jump_hold = 8
        return inp

    def _boss(self, w, fire, px_, py_) -> NeonInput:
        """Keep moving, jump shockwaves and the low beam, crouch under the high one."""
        g = self.game
        p = g.player
        inp = NeonInput(fire=fire, px=px_, py=py_)
        gap = p.cx - w.cx
        if abs(gap) < 150:
            inp.x = 1 if gap > 0 else -1  # too close: back away
            if (inp.x > 0 and p.cx > w.right + 160) or (inp.x < 0 and p.cx < w.left - 160):
                inp.x = -inp.x  # cornered: run under it while it is busy
        elif abs(gap) > 260:
            inp.x = -1 if gap > 0 else 1
        else:
            inp.x = 1 if (g.frames // 40) % 2 == 0 else -1
        for s in g.shots:
            if s.kind == "plasma":
                land = self._landing(s, w.floor)
                if land is not None and abs(land - p.cx) < 48:
                    inp.x = 1 if p.cx >= land else -1  # step out of the splash
        shock = any(s.kind == "shock" and abs(s.x - p.cx) < 70 and (s.vx > 0) == (p.cx > s.x) for s in g.shots)
        low_beam = w.laser in ("charge", "sweep") and not w.laser_high and (w.laser == "sweep" or w.laser_t < 6)
        high_beam = w.laser in ("charge", "sweep") and w.laser_high
        if high_beam:
            inp.x, inp.y = 0, 1
        elif (shock or low_beam or w.stomp_wind) and p.grounded and not p.jump_held:
            inp.jump = True
        elif not p.grounded and p.vy < 0:
            inp.jump = True  # hold for height
        return inp

    @staticmethod
    def _landing(s, floor: int) -> int | None:
        """Where a lobbed shot will come down (its own integer trajectory, read-only)."""
        x, y, vx, vy, rx, ry = s.x, s.y, s.vx, s.vy, s.rx, s.ry
        for _ in range(80):
            vy += s.gravity
            rx += vx
            ry += vy
            x += rx // 256
            y += ry // 256
            rx %= 256
            ry %= 256
            if y >= floor - 6:
                return x
        return None

    def _heal_detour(self) -> None:
        """Low on integrity: fetch the nearest reachable health cell first."""
        g = self.game
        p = g.player
        if self.targets and self.targets[0][0] == "heal":
            self.heal_t += 1
            if self.heal_t > 300:  # taking too long: give up on this one
                self.skip.add(self.targets.pop(0)[1:])
                self.plan, self.edge, self.replan = [], None, 0
            return
        if p.hp > 40 or not p.grounded:
            return
        here = self._node()
        best, best_d = None, 28
        for item in g.pickups:
            spot = (item.x >> SHIFT, (item.y >> SHIFT) - 1)
            if item.kind == "health" and spot not in self.skip:
                d = abs(spot[0] - here[0]) + abs(spot[1] - here[1])
                if d < best_d:
                    best, best_d = spot, d
        if best is not None:
            end = self._path(here, best)[-1]
            if abs(end[0] - best[0]) + abs(end[1] - best[1]) > 2:
                self.skip.add(best)  # not reachable from here (behind a gate, say)
                return
            self.targets.insert(0, ("heal", *best))
            self.heal_t = 0
            self.plan, self.edge, self.replan = [], None, 0

    def _combat(self):
        g = self.game
        p = g.player
        self.select = None
        if not self.fight:
            return None, False
        sx, sy = p.shoulder()
        best, best_d = None, 330
        for e in g.enemies:
            if not e.hittable() or e.kind == "target":
                continue
            d = dist(e.cx - sx, e.cy - sy)
            if e.kind == "warden" and d > 90:
                d -= 60  # a priority, unless something is chewing on you
            if d < best_d and g.grid.line_clear(sx, sy, e.cx, e.cy):
                best, best_d = e, d
        if best is None:
            if g.weapon not in (0, 1):
                self.select = 0
            return None, False
        # pick the right tool: scatter up close, rail/seekers/mortar for heavies, pulse otherwise
        want = 0
        close = best_d < 110
        if best.kind in ("strider", "warden"):
            for slot in (2, 4, 3):
                if g.owned[slot] and g.ammo[slot] > 0:
                    want = slot
                    break
        elif close and g.owned[1] and g.ammo[1] > 0:
            want = 1
        elif best.kind == "nest" and g.owned[3] and g.ammo[3] > 0:
            want = 3
        if want != g.weapon:
            self.select = want
        return (best.cx, best.cy), True
