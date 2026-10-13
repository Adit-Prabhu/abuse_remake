"""The runner: movement feel, ladders, ledges, crouching, the dash, damage and death.

Feel constants (30 ticks a second, velocities in sub-pixels):
- run 3.5 px/tick with ground acceleration and friction, less control in the air;
- jump -9.6 px/tick (72 px, four and a half tiles); releasing the key early cuts the rise
  (a short hop); 5 ticks of coyote time after leaving a ledge; a 6-tick jump buffer;
- the double-jump boots add one air jump of about 60 px;
- ladders: up/down to climb at 2.5 px/tick (alternating 3 and 2), jump to let go;
- down + jump drops through a one-way ledge, ladder top or elevator (before any ladder grab);
- down on the ground crouches (26 px tall instead of 42) and you can crawl through vents;
- the dash: 8 ticks at 9 px/tick, invulnerable, 30-tick cooldown.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fixed import iatan2, px, sign
from .physics import GRAVITY, Body, floor_at, free_at, integrate, step_x, step_y
from .tilemap import LADDER, SHIFT

STAND_H, CROUCH_H, WIDTH = 42, 26, 16
RUN = px(3.5)
CROUCH_RUN = px(1.5)
GROUND_ACCEL, GROUND_FRICTION = px(0.55), px(0.7)
AIR_ACCEL, AIR_FRICTION = px(0.4), px(0.12)
JUMP = -px(9.6)
JUMP_CUT = -px(3.0)
AIR_JUMP = -px(8.2)
COYOTE, JUMP_BUFFER = 5, 6
DASH_TICKS, DASH_SPEED, DASH_IFRAMES, DASH_COOLDOWN = 8, px(9), 10, 30
HURT_IFRAMES, HURT_STUN = 24, 6
DYING_TICKS = 36
SHOULDER = 13  # pixels below the top of the standing box


@dataclass
class NeonInput:
    """One tick of player intent. ``px``/``py`` is the aim point in world pixels."""

    x: int = 0  # -1 left, 1 right
    y: int = 0  # -1 up (climb, or jump when not on a ladder), 1 down (crouch, climb down, interact)
    jump: bool = False
    fire: bool = False
    dash: bool = False
    interact: bool = False
    px: int = 0
    py: int = 0


@dataclass
class Player(Body):
    hp: int = 100
    max_hp: int = 100
    facing: int = 1
    aim: int = 0
    crouching: bool = False
    climbing: bool = False
    coyote: int = 0
    jump_buffer: int = 0
    jump_held: bool = False
    up_held: bool = False
    jumping: bool = False  # rising from a jump (the cut applies)
    air_jumps: int = 0
    boots: bool = False
    dash_t: int = 0
    dash_dir: int = 1
    dash_cd: int = 0
    iframes: int = 0
    stun: int = 0
    dying: int = 0
    shield: int = 0
    shield_t: int = 0
    overcharge: int = 0
    haste: int = 0
    phase: int = 0
    keys: list = field(default_factory=list)
    interact_held: bool = False
    down_held: bool = False
    dash_held: bool = False
    landed: int = 0  # ticks since the last landing (for effects)
    air_t: int = 0
    regen_t: int = 0

    # --- queries ---
    def shoulder(self) -> tuple[int, int]:
        return self.cx, self.y + (SHOULDER if not self.crouching else 9)

    def on_ladder(self, game) -> bool:
        g = game.grid
        return g.at(self.cx >> SHIFT, (self.y + self.h // 2) >> SHIFT) == LADDER or \
            g.at(self.cx >> SHIFT, (self.bottom - 2) >> SHIFT) == LADDER

    def ladder_below(self, game) -> bool:
        return game.grid.at(self.cx >> SHIFT, (self.bottom + 1) >> SHIFT) == LADDER

    @property
    def alive(self) -> bool:
        return self.hp > 0

    # --- the tick ---
    def update(self, game, inp: NeonInput) -> dict:
        """Advance one tick. Returns the edge-triggered actions taken (for the game)."""
        acts = {"jump": False, "dash": False, "interact": False, "fire": False, "drop": False}
        for name in ("dash_cd", "iframes", "stun", "shield_t", "overcharge", "haste", "phase"):
            v = getattr(self, name)
            if v > 0:
                setattr(self, name, v - 1)
        if self.shield_t == 0:
            self.shield = 0
        if self.dying:
            self.dying += 1
            self.vx = 0
            integrate(game, self)
            return acts
        self.aim = iatan2(inp.py - self.shoulder()[1], inp.px - self.shoulder()[0])
        self.facing = 1 if inp.px >= self.cx else -1
        up_press = inp.y < 0 and not self.up_held
        self.up_held = inp.y < 0
        jump_press = (inp.jump and not self.jump_held) or (up_press and not self.climbing and not self.on_ladder(game))
        self.jump_held = inp.jump
        down_press = inp.y > 0 and not self.down_held
        self.down_held = inp.y > 0
        interact_press = (inp.interact and not self.interact_held) or down_press
        self.interact_held = inp.interact
        dash_press = inp.dash and not self.dash_held
        self.dash_held = inp.dash
        acts["interact"] = interact_press
        acts["fire"] = inp.fire and not self.stun
        if jump_press:
            self.jump_buffer = JUMP_BUFFER
        elif self.jump_buffer:
            self.jump_buffer -= 1

        if dash_press and self.dash_cd == 0 and not self.climbing and not self.stun:
            self._start_dash(game, inp)
            acts["dash"] = True
        if self.dash_t:
            self.riding = -1
            self._dash_tick(game)
            return acts
        if self.jump_buffer and inp.y > 0 and self.grounded and not self.climbing and not self.stun \
                and self._on_passable_floor(game):
            # S + jump on a ledge, ladder top or elevator: drop through (before grabbing the ladder)
            self.jump_buffer = 0
            self.drop = 6
            self.y += 1
            self.grounded = False
            acts["drop"] = True
            game.emit("drop", self.cx, self.bottom)
            integrate(game, self, GRAVITY)
            return acts
        if self.climbing or (inp.y != 0 and not self.stun and self._try_grab(game, inp)):
            self.riding = -1
            self._climb(game, inp, acts)
            return acts
        self._crouch(game, inp)
        self._run(game, inp)
        self._jump(game, inp, acts)
        was_grounded = self.grounded
        vy_before = self.vy
        integrate(game, self, GRAVITY)
        if self.grounded:
            if not was_grounded:
                self.landed = 0
                game.emit("land", self.cx, self.bottom, speed=vy_before)
            self.coyote = COYOTE
            self.air_jumps = 1 if self.boots else 0
            self.jumping = False
            self.air_t = 0
        else:
            self.coyote = max(0, self.coyote - 1)
            self.air_t += 1
        self.landed += 1
        return acts

    def _start_dash(self, game, inp):
        self.dash_dir = sign(inp.x) or self.facing
        self.dash_t = DASH_TICKS
        cool = DASH_COOLDOWN * (60 if self.phase else 100) // 100
        self.dash_cd = cool * game.upgrade_pct("dash_cd") // 100
        self.iframes = max(self.iframes, DASH_IFRAMES + (6 if self.phase else 0))
        self.vy = 0
        self.ry = 0
        if self.crouching:
            self._stand(game)
        game.emit("dash", self.cx, self.cy, direction=self.dash_dir)
        game.dashes += 1

    def _dash_tick(self, game):
        self.dash_t -= 1
        self.vx = self.dash_dir * DASH_SPEED
        hit = step_x(game, self, DASH_SPEED * self.dash_dir // 256)
        if hit or self.dash_t == 0:
            self.dash_t = 0
            self.vx = self.dash_dir * RUN
        self.grounded = floor_at(game, self, self.y + 1, True)

    def _try_grab(self, game, inp) -> bool:
        if inp.y < 0 and self.on_ladder(game):
            return True
        return inp.y > 0 and self.grounded and self.ladder_below(game)

    def _climb(self, game, inp, acts):
        if not self.climbing:
            self.climbing = True
            self.vx = self.vy = self.rx = self.ry = 0
            if self.crouching:
                self._stand(game)
            target = ((self.cx >> SHIFT) << SHIFT) + 8 - self.w // 2
            if free_at(game, self, target, self.y):
                self.x = target
            if inp.y > 0 and self.grounded:
                self.drop = 4  # step down through the ladder top
        if self.jump_buffer:
            self.jump_buffer = 0
            self.climbing = False
            self.vy = JUMP * 3 // 4
            self.vx = sign(inp.x) * RUN
            self.jumping = True
            acts["jump"] = True
            game.emit("jump", self.cx, self.bottom)
            return
        if inp.x and not inp.y:
            self.climbing = False
            return
        dy = inp.y * (3 if game.frames % 2 else 2)  # 2.5 px/tick on average, the same both ways
        if dy:
            self.drop = 2 if dy > 0 else self.drop
            blocked = step_y(game, self, dy, oneway=dy > 0 and not self.on_ladder(game))
            if blocked and dy > 0:
                self.climbing = False
        if not self.on_ladder(game):
            # climbed off the top or the bottom
            self.climbing = False
            if dy < 0:
                # finish on top of the ladder: lift the feet onto the ladder-top platform
                while not floor_at(game, self, self.y + 1, True) and self.bottom & 15:
                    self.y -= 1
        self.grounded = floor_at(game, self, self.y + 1, True)
        self.vy = 0

    def _crouch(self, game, inp):
        want = inp.y > 0 and self.grounded and not self.stun
        if want and not self.crouching:
            self.crouching = True
            self.y += STAND_H - CROUCH_H
            self.h = CROUCH_H
        elif not want and self.crouching:
            self._stand(game)

    def _stand(self, game) -> bool:
        if free_at(game, self, self.x, self.y - (STAND_H - CROUCH_H), STAND_H):
            self.y -= STAND_H - CROUCH_H
            self.h = STAND_H
            self.crouching = False
            return True
        return False

    def _run(self, game, inp):
        if self.stun:
            self.vx = self.vx * 9 // 10
            return
        top = (CROUCH_RUN if self.crouching else RUN) * (140 if self.haste else 100) // 100
        want = sign(inp.x) * top
        if self.grounded:
            step = GROUND_ACCEL if inp.x and sign(inp.x) == sign(self.vx) or self.vx == 0 else GROUND_FRICTION
            if not inp.x:
                step = GROUND_FRICTION
        else:
            step = AIR_ACCEL if inp.x else AIR_FRICTION
        if self.vx < want:
            self.vx = min(want, self.vx + step)
        elif self.vx > want:
            self.vx = max(want, self.vx - step)

    def _jump(self, game, inp, acts):
        if self.stun:
            return
        held = inp.jump or inp.y < 0
        if self.jumping and not held and self.vy < JUMP_CUT:
            self.vy = JUMP_CUT  # released early: a short hop
        if not self.jump_buffer:
            return
        if inp.y > 0 and self.grounded and self._on_passable_floor(game):
            self.jump_buffer = 0
            self.drop = 6
            self.y += 1
            acts["drop"] = True
            game.emit("drop", self.cx, self.bottom)
            return
        if self.crouching and not self._stand(game):
            return
        if self.grounded or self.coyote:
            self.vy = JUMP
        elif self.air_jumps:
            self.air_jumps -= 1
            self.vy = AIR_JUMP
            game.emit("air_jump", self.cx, self.bottom)
        else:
            return
        self.ry = 0
        self.jump_buffer = 0
        self.coyote = 0
        self.jumping = True
        self.grounded = False
        acts["jump"] = True
        game.emit("jump", self.cx, self.bottom)

    def _on_passable_floor(self, game) -> bool:
        """Standing on something one can drop through (a ledge, ladder top or elevator)."""
        saved = self.drop
        self.drop = 0
        solid_below = floor_at(game, self, self.y + 1, True, oneway=False)
        self.drop = saved
        return not solid_below

    def hurt(self, game, damage: int, from_x: int, kind: str = "hit") -> int:
        """Apply damage after difficulty, shields and invulnerability. Returns damage taken."""
        if self.dying or self.iframes or self.dash_t or game.variant == "training" or game.transition:
            return 0
        damage = max(1, damage * game.damage_scale * game.wave_damage_pct() // 10000)
        absorbed = min(self.shield, damage)
        self.shield -= absorbed
        damage -= absorbed
        if absorbed:
            game.emit("shield_hit", self.cx, self.cy, absorbed=absorbed)
        if damage <= 0:
            self.iframes = 8
            return 0
        self.hp = max(0, self.hp - damage)
        game.damage_taken += damage
        self.iframes = HURT_IFRAMES
        self.stun = HURT_STUN
        self.climbing = False
        d = 1 if self.cx >= from_x else -1
        self.vx = d * px(3)
        if self.grounded:
            self.vy = -px(3.5)
        game.emit("hurt", self.cx, self.cy, damage=damage, cause=kind)
        if self.hp <= 0:
            self.dying = 1
            self.dash_t = 0
            if self.crouching:
                self._stand(game)
            game.emit("player_death", self.cx, self.cy)
        return damage
