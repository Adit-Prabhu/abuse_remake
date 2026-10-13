"""Neon Protocol v2 design contracts: movement feel, enemy behaviour, weapons, objects, Horde,
training and determinism. These are design tests for an optional mode, not original-game
evidence. Most use small inline maps so each rule is checked in isolation."""

import pytest

from abuse_remake.engine.neon import LESSONS, SECTORS, WEAPONS, NeonGame, NeonInput, load_map, parse_map
from abuse_remake.engine.neon.tilemap import BREAK, EMPTY, LADDER, ONEWAY, SOLID


def world(rows: str, **kw) -> NeonGame:
    text = "title: test\n---\n" + rows.strip("\n")
    return NeonGame(seed=kw.pop("seed", 3), variant="custom", map_text=text, **kw)


def run(g: NeonGame, n: int, **inp) -> None:
    for _ in range(n):
        p = g.player
        aim = inp.pop("aim", None) if "aim" in inp else None
        sx, sy = p.shoulder()
        tx, ty = aim if aim else (sx + 200 * (p.facing or 1), sy)
        g.step(NeonInput(px=tx, py=ty, **inp))


def idle(g: NeonGame, n: int) -> None:
    for _ in range(n):
        g.step()


FLOOR = """
########################################
#......................................#
#......................................#
#......................................#
#......................................#
#......................................#
#......................................#
#.P....................................#
########################################
"""


# ---------------------------------------------------------------- map files
def test_every_sector_and_mode_map_parses_with_required_markers():
    for name in SECTORS:
        m = load_map(name)
        kinds = {e.kind for e in m.entities}
        assert {"player", "console", "exit"} <= kinds, name
        assert m.width >= 60 and m.height >= 30, name
    core = load_map("core")
    assert any(e.kind == "enemy" and e.args[0] == "warden" for e in core.entities)
    horde = load_map("horde")
    assert len(horde.entities_of("nest")) >= 4 and horde.entities_of("spawn")
    training = load_map("training")
    assert len(training.entities_of("marker")) >= 4
    assert "a" in training.doors


def test_campaign_is_vertical_and_uses_every_traversal_feature():
    """The sectors are mazes, not corridors: many floors, ladders, ledges, elevators or pads."""
    for name in SECTORS[:3]:
        m = load_map(name)
        tiles = m.tiles
        assert m.height >= 40, name
        assert tiles.count(LADDER) >= 10, name
        assert tiles.count(ONEWAY) >= 10, name
        floors = {ty for ty in range(1, m.height) for tx in range(m.width)
                  if tiles[ty * m.width + tx] in (SOLID, ONEWAY) and tiles[(ty - 1) * m.width + tx] == EMPTY}
        assert len(floors) >= 12, name
    reactor = load_map("reactor")
    assert reactor.entities_of("elevator") and reactor.entities_of("teleport")
    assert any(e.args == ("boots",) for e in reactor.entities_of("pickup"))
    assert any(BREAK in load_map(n).tiles for n in SECTORS[:3])


def test_unknown_map_characters_are_rejected():
    with pytest.raises(ValueError):
        parse_map("---\n#?#\n")


# ---------------------------------------------------------------- movement
def test_run_accelerates_and_stops_with_friction():
    g = world(FLOOR)
    x0 = g.player.x
    run(g, 1, x=1)
    first = g.player.x - x0
    run(g, 12, x=1)
    assert first < 3 and g.player.vx == 896  # 3.5 px/tick top speed
    run(g, 10)
    assert g.player.vx == 0


def test_full_jump_reaches_almost_five_tiles_and_a_tap_is_a_short_hop():
    g = world(FLOOR)
    floor = g.player.bottom
    peak = floor
    run(g, 1, jump=True)
    for _ in range(30):
        run(g, 1, jump=True)
        peak = min(peak, g.player.bottom)
    full = floor - peak
    g2 = world(FLOOR)
    run(g2, 1, jump=True)
    peak = floor
    for _ in range(30):
        run(g2, 1)
        peak = min(peak, g2.player.bottom)
    hop = floor - peak
    assert 70 <= full <= 84
    assert hop < full // 2


def test_coyote_time_allows_a_late_jump_but_not_a_very_late_one():
    ledge = """
##########################
#........................#
#........................#
#........................#
#........................#
#.P......................#
######...................#
#........................#
#........................#
##########################
"""
    for late, ok in ((3, True), (9, False)):
        g = world(ledge)
        p = g.player
        p.x = 6 * 16 - p.w - 1
        while p.grounded or p.x + p.w <= 96:
            run(g, 1, x=1)
        run(g, late - 1, x=1)
        vy_before = p.vy
        run(g, 1, x=1, jump=True)
        assert (p.vy < 0) == ok, (late, vy_before, p.vy)


def test_jump_buffer_jumps_on_landing():
    g = world(FLOOR)
    run(g, 20, jump=True)  # a full jump
    while g.player.vy <= 0 or g.player.bottom < 8 * 16 - 20:
        run(g, 1)
    run(g, 1, jump=True)  # pressed a little before touching down
    landed_and_left = False
    for _ in range(8):
        run(g, 1, jump=True)
        if g.player.vy < 0 and g.player.bottom < 8 * 16:
            landed_and_left = True
            break
    assert landed_and_left


def test_ladders_climb_both_ways_and_top_is_standable():
    tower = """
################
#..............#
#..............#
#..............#
#######H########
#......H.......#
#......H.......#
#......H.......#
#......H.......#
#.P....H.......#
################
"""
    g = world(tower)
    p = g.player
    while abs(p.cx - (7 * 16 + 8)) > 4:
        run(g, 1, x=1)
    run(g, 6)
    for _ in range(60):
        run(g, 1, y=-1)
        if not p.climbing and p.grounded:
            break
    assert p.bottom == 4 * 16 and p.grounded and not p.climbing  # standing on the ladder top
    for _ in range(80):
        run(g, 1, y=1)
    assert p.bottom == 10 * 16  # climbed back down to the floor


def test_one_way_ledges_hold_from_above_and_drop_through_with_down_and_jump():
    g = world("""
####################
#..................#
#..................#
#..................#
#..................#
#.P..======........#
#..................#
#..................#
#..................#
####################
""")
    p = g.player
    # put the runner on the grating (row 5)
    p.x, p.y = 6 * 16, 5 * 16 - p.h - 30
    run(g, 20)
    assert p.grounded and p.bottom == 5 * 16
    run(g, 2, y=1)
    run(g, 1, y=1, jump=True)
    run(g, 20)
    assert p.bottom == 9 * 16
    # and from below, a jump passes up through it
    run(g, 1, jump=True)
    tops = []
    for _ in range(18):
        run(g, 1, jump=True)
        tops.append(p.bottom)
    run(g, 30)
    assert p.bottom == 5 * 16


def test_crouch_shrinks_and_crawls_through_a_vent():
    g = world("""
####################
#........###########
#........###########
#..................#
#.P................#
####################
""")
    p = g.player
    run(g, 20, x=1)
    assert p.x + p.w <= 9 * 16  # a standing runner cannot enter the 2-tile vent
    run(g, 2, y=1)
    assert p.crouching and p.h == 26
    run(g, 90, x=1, y=1)
    assert p.x > 12 * 16


def test_dash_is_fast_invulnerable_and_never_passes_walls():
    g = world("""
####################
#..........#.......#
#..........#.......#
#..........#.......#
#.P........#.......#
####################
""")
    p = g.player
    p.x = 11 * 16 - p.w - 40  # 40 px from the wall: the dash alone would carry it 72 px
    run(g, 1, dash=True, x=1)
    assert p.iframes > 0 and p.dash_t
    for _ in range(8):
        run(g, 1, x=1)
        assert p.x + p.w <= 11 * 16
    assert p.x + p.w == 11 * 16  # stopped flush against the wall, not inside or past it
    assert p.dash_t == 0
    cd = p.dash_cd
    run(g, 1, dash=True, x=-1)
    assert cd > 0 and p.dash_t == 0  # refused while cooling down


def test_double_jump_needs_the_boots():
    g = world(FLOOR)
    run(g, 1, jump=True)
    run(g, 8, jump=True)
    run(g, 1)
    run(g, 1, jump=True)
    assert not any(e["kind"] == "air_jump" for e in g.events)
    g2 = world(FLOOR)
    g2.player.boots = True
    run(g2, 1, jump=True)
    run(g2, 8, jump=True)
    run(g2, 1)
    run(g2, 1, jump=True)
    assert any(e["kind"] == "air_jump" for e in g2.events) and g2.player.vy < -1800


def test_elevator_carries_the_runner_to_the_other_end():
    g = world("""
##########
#........#
#........#
#........#
#...|....#
#...|....#
#...|....#
#...|....#
#...|....#
#...|....#
#.P.L....#
##########
""")
    el = g.elevators[0]
    assert el.top == 5 * 16 and el.bottom == 11 * 16 == el.y  # resting flush with the floor
    p = g.player
    p.x = el.x + 16
    run(g, 2)
    assert p.bottom == el.y
    run(g, 80)
    assert el.y == el.top and p.bottom == el.top


# ---------------------------------------------------------------- enemies
def test_ceiling_crawler_drops_only_when_the_runner_passes_below_in_sight():
    g = world("""
##############################
#.......x....................#
#............................#
#............................#
#............................#
#............................#
#.P..........................#
##############################
""")
    c = next(e for e in g.enemies if e.kind == "crawler")
    assert c.surface == "ceil" and c.state == "hang"
    run(g, 1)
    assert c.surface == "ceil"
    for _ in range(60):
        run(g, 1, x=1)
        if c.surface == "floor":
            break
    assert c.surface == "floor"
    # behind a wall it never notices
    g = world("""
##############################
#.......x...#................#
#...........#................#
#...........#................#
#############................#
#............................#
#.P..........................#
##############################
""")
    c = next(e for e in g.enemies if e.kind == "crawler")
    run(g, 40, x=1)
    assert c.state == "hang" and not c.alerted


def test_a_scream_alerts_neighbours_but_not_distant_crawlers():
    g = world("""
##########################################################
#........................................................#
#........................................................#
#........................................................#
#.P..........................x....x..........x...........#
##########################################################
""")
    near_a, near_b, far = sorted((e for e in g.enemies), key=lambda e: e.x)
    # nobody can see the runner (more than 250 px away), the far one is beyond the 170 px scream
    assert min(e.cx for e in g.enemies) - g.player.cx > 400
    assert near_b.cx - near_a.cx < 170 < far.cx - near_a.cx
    idle(g, 30)
    assert not any(e.alerted for e in g.enemies)
    near_a.alert(g)
    idle(g, 3)
    assert not near_b.alerted  # the scream reaches the others a few ticks later
    idle(g, 10)
    assert near_b.alerted and not far.alerted


def test_crawlers_pounce_and_damage_interrupts_the_pounce():
    g = world("""
##############################
#............................#
#............................#
#............................#
#.P.........x................#
##############################
""")
    c = g.enemies[0]
    c.alert(g)
    c.state = "chase"
    seen = set()
    for _ in range(40):
        run(g, 1)
        seen.add(c.state)
        if c.state == "pounce":
            break
    assert "crouch" in seen and c.state == "pounce"
    c.damage(g, 7, "pulse", g.player.cx, g.player.cy)
    assert c.flinch and c.state == "chase"


def test_crawler_climbs_the_wall_toward_a_runner_above():
    g = world("""
##########################
#........................#
#.P......................#
#####....................#
#...#....................#
#...#....................#
#...#....................#
#...#....................#
#...#........x...........#
##########################
""")
    c = g.enemies[0]
    c.alert(g)
    c.state = "chase"
    seen = set()
    for _ in range(200):
        idle(g, 1)
        seen.add(c.state)
    assert "climb" in seen


def test_sentry_is_armoured_while_retracted():
    g = world("""
##########################
#.............s..........#
#........................#
#........................#
#........................#
#####.....................
#........................#
#.P......................#
##########################
""")
    s = g.enemies[0]
    s.x = 300
    assert s.mount == "ceil" and not s.hittable()
    assert s.damage(g, 50, "rail", 0, 0) == 0
    s.out = 8
    assert s.damage(g, 10, "pulse", 0, 0) == 10


def test_strider_shield_blocks_frontal_pulse_but_not_the_rail_or_a_hit_in_the_back():
    g = world(FLOOR)
    g.enemies.clear()
    s = g.spawn_enemy("strider", 400, 8 * 16)
    s.facing = -1
    hp = s.hp
    assert s.damage(g, 7, "pulse", s.cx - 100, s.cy) == 0 and s.hp == hp
    assert s.damage(g, 48, "rail", s.cx - 100, s.cy) == 48
    assert s.damage(g, 10, "pulse", s.cx + 100, s.cy) == 15


def test_drone_alarm_opens_nests_and_nests_release_crawlers():
    g = world("""
##############################################
#............................................#
#.........o..................................#
#............................................#
#............................................#
#............................................#
#............................................#
#.P..............................n...........#
##############################################
""")
    drone = next(e for e in g.enemies if e.kind == "drone")
    nest = next(e for e in g.enemies if e.kind == "nest")
    drone.damage(g, 1, "pulse", 0, 0)
    assert drone.alarmed and nest.active
    idle(g, 40)
    assert any(e.kind == "crawler" and e.owner == nest.uid for e in g.enemies)


def test_warden_changes_phase_at_thresholds_and_vents_take_double_damage():
    g = NeonGame(seed=1, variant="campaign", sector=3)
    w = next(e for e in g.enemies if e.kind == "warden")
    w.hp = w.max_hp * 60 // 100
    w.alerted = True
    w.update(g)
    assert w.phase == 2 and w.roar and not w.hittable()
    w.roar = 0
    w.hp = w.max_hp * 30 // 100
    w.update(g)
    assert w.phase == 3
    w.roar = 0
    w.laser = "vent"
    assert w.damage(g, 10, "pulse", w.cx, w.cy) == 20


# ---------------------------------------------------------------- weapons
def own_all(g):
    g.owned = [True] * 5
    g.ammo = [-1, 20, 10, 10, 10]


def test_rail_pierces_a_line_of_enemies_and_stops_at_walls():
    g = world("""
##############################################
#............................................#
#............................................#
#............................................#
#.P.........x....x....#.....x................#
##############################################
""")
    own_all(g)
    g.weapon = 2
    for e in g.enemies:
        e.state, e.surface = "idle", "floor"
    a, b, c = sorted(g.enemies, key=lambda e: e.x)
    target = (b.cx, b.cy)
    run(g, 1, fire=True, aim=target)
    assert a.hp < a.max_hp and b.hp < b.max_hp and c.hp == c.max_hp


def test_scatter_fires_a_five_way_fan_and_ammo_runs_out():
    g = world(FLOOR)
    own_all(g)
    g.weapon = 1
    g.ammo[1] = 1
    run(g, 1, fire=True)
    pellets = [s for s in g.shots if s.kind == "pellet"]
    assert len(pellets) == 5 and len({s.angle for s in pellets}) == 5
    run(g, 30, fire=True)
    assert g.ammo[1] == 0 and len([s for s in g.shots if s.kind == "pellet"]) == 0


def test_mortar_bounces_then_bursts_and_breaks_cracked_walls():
    g = world("""
##############################
#............................#
#............................#
#..........%%................#
#.P........%%................#
##############################
""")
    own_all(g)
    g.weapon = 3
    # lobbed at the floor short of the wall: it bounces on the floor first, then the blast cracks the wall
    run(g, 1, fire=True, aim=(g.player.cx + 40, g.player.cy + 60))
    bounced = broken = False
    for _ in range(90):
        run(g, 1)
        bounced |= any(e["kind"] == "bounce" for e in g.events)
        broken |= any(e["kind"] == "break" for e in g.events)
    assert bounced and broken and g.secrets > 0
    assert g.grid.at(11, 4) == EMPTY or g.grid.at(11, 3) == EMPTY


def test_a_mortar_hitting_a_cracked_wall_bursts_without_bouncing():
    g = world("""
##############################
#............................#
#............................#
#..........%%................#
#.P........%%................#
##############################
""")
    from abuse_remake.engine.neon.weapons import Shot

    g.shots.append(Shot("mortar", 160, 60, 8 * 256, 0, 55, life=60, gravity=0, bounces=2, radius=46))
    events = []
    for _ in range(5):
        run(g, 1)
        events += [e["kind"] for e in g.events]
    assert "break" in events and "bounce" not in events


def test_seekers_turn_toward_a_target_off_their_line():
    g = world(FLOOR.replace("#.P....", "#.P....").replace(
        "#......................................#\n#.P", "#.....................x................#\n#.P", 1))
    own_all(g)
    g.weapon = 4
    target = g.enemies[0]
    target.state, target.surface = "idle", "floor"
    target.y = 2 * 16
    run(g, 1, fire=True)
    ys = [s.y for s in g.shots if s.kind == "seeker"]
    run(g, 10)
    ys2 = [s.y for s in g.shots if s.kind == "seeker"]
    assert ys2 and min(ys2) < min(ys)


# ---------------------------------------------------------------- objects
def test_console_saves_and_restore_is_exact():
    g = world(FLOOR.replace("#.P...", "#.PS.."))
    run(g, 6, x=1)
    run(g, 1, interact=True)
    assert any(e["kind"] == "checkpoint" for e in g.events)
    snap = g.snapshot()
    h = g.state_hash()
    for _ in range(3):
        run(g, 20, x=1, fire=True)
        g.restore(snap)
        assert g.state_hash() == h


def test_switch_opens_its_door_and_key_gates_need_the_key():
    g = world("""
##############################
#............a.......R.......#
#............a.......R.......#
#............a.......R.......#
#.P.A........a.......R.......#
##############################
""")
    p = g.player
    run(g, 40, x=1)
    assert p.x + p.w <= 13 * 16
    p.x = 4 * 16
    run(g, 1, interact=True)
    run(g, 60, x=1)
    assert 13 * 16 < p.x < 21 * 16  # through the door, stopped by the red gate
    p.keys.append("red")
    run(g, 40, x=1)
    assert p.x > 21 * 16


def test_teleport_pads_link_in_pairs():
    g = world("""
##############################
#............................#
#............................#
#.P.T....................V...#
##############################
""")
    run(g, 30, x=1)
    assert any(e["kind"] == "teleport" for e in [*g.events]) or g.player.x > 20 * 16
    assert g.player.x > 20 * 16


# ---------------------------------------------------------------- modes
def test_horde_waves_grow_and_offer_upgrades():
    g = NeonGame(seed=5, variant="horde")
    assert g.owned[1]
    idle(g, 95)
    assert g.horde.wave == 1 and g.horde.queue
    size1 = len(g.horde.queue) + sum(1 for e in g.enemies if e.kind != "nest")
    for e in g.enemies:
        if e.kind != "nest":
            e.dead = True
    g.horde.queue.clear()
    idle(g, 2)
    assert g.horde.cleared == 1 and len(g.horde.offer) == 2
    hp = g.player.max_hp
    choice = g.horde.offer[0]
    g.step(upgrade=0)
    assert choice in g.horde.taken and not g.horde.offer
    if choice == "vitality":
        assert g.player.max_hp == hp + 25
    idle(g, 160)
    assert g.horde.wave == 2
    assert len(g.horde.queue) + sum(1 for e in g.enemies if e.kind != "nest") > size1


def test_horde_is_deterministic_per_seed():
    def play(seed):
        g = NeonGame(seed=seed, variant="horde")
        for t in range(400):
            p = g.player
            g.step(NeonInput(x=1 if t % 80 < 40 else -1, jump=t % 37 == 0, fire=True, px=p.cx + 150, py=p.cy - 40))
        return g.state_hash()

    assert play(4) == play(4)
    assert play(4) != play(5)


def test_training_lessons_advance_only_by_doing_them():
    g = NeonGame(seed=1, variant="training")
    assert g.lesson == 0
    idle(g, 30)
    assert g.lesson == 0
    mx, my = g.markers[0]
    g.player.x, g.player.y = mx - g.player.w // 2, my - g.player.h
    idle(g, 1)
    assert g.lesson == 1
    assert len(LESSONS) == 10
    g.player.hurt(g, 50, 0)
    assert g.player.hp == 100  # training never hurts


def test_campaign_exit_moves_to_the_next_sector_and_keeps_the_arsenal():
    g = NeonGame(seed=2, variant="campaign")
    g.owned[2] = True
    g.ammo[2] = 7
    ex, ey = g.exit
    p = g.player
    p.x, p.y = ex - p.w // 2, ey - p.h
    g.step(NeonInput(interact=True, px=p.cx + 50, py=p.cy))
    assert g.transition
    idle(g, 60)
    assert g.sector == 1 and g.map.name == "reactor" and g.owned[2] and g.ammo[2] == 7


def test_final_exit_is_locked_until_the_warden_falls():
    g = NeonGame(seed=2, variant="campaign", sector=3)
    ex, ey = g.exit
    p = g.player
    p.x, p.y = ex - p.w // 2, ey - p.h
    g.step(NeonInput(interact=True, px=p.cx + 50, py=p.cy))
    assert g.status == "running" and any(e["kind"] == "locked" for e in g.events)
    g.boss_dead = True
    g.step(NeonInput(px=p.cx + 50, py=p.cy))
    g.step(NeonInput(interact=True, px=p.cx + 50, py=p.cy))
    assert g.status == "won"


def test_difficulty_scales_incoming_damage():
    hits = {}
    for d in ("easy", "hard", "extreme"):
        g = NeonGame(seed=1, variant="custom", difficulty=d, map_text="---\n" + FLOOR.strip("\n"))
        hits[d] = g.player.hurt(g, 20, 0)
    assert hits["easy"] < hits["hard"] < hits["extreme"]


def test_same_inputs_give_the_same_state_and_snapshots_repeat():
    def play():
        g = NeonGame(seed=9, variant="campaign")
        for t in range(300):
            p = g.player
            g.step(NeonInput(x=1, jump=t % 25 == 0, fire=t % 3 == 0, px=p.cx + 120, py=p.cy - 30))
        return g

    a, b = play(), play()
    assert a.state_hash() == b.state_hash()


def test_restore_then_the_same_inputs_reproduce_the_uninterrupted_run():
    """The property checkpoints and replays depend on, with enemies and the RNG in play."""
    def inputs(t, p):
        return NeonInput(x=1 if t % 90 < 60 else -1, jump=t % 25 == 0, fire=t % 3 == 0, dash=t % 70 == 0,
                         px=p.cx + 120, py=p.cy - 30)

    g = NeonGame(seed=9, variant="campaign")
    for t in range(200):
        g.step(inputs(t, g.player))
    snap = g.snapshot()
    rng_before = g.rng.getstate()
    for t in range(200, 500):
        g.step(inputs(t, g.player))
    straight = g.state_hash()
    assert g.rng.getstate() != rng_before  # enemies and drops really used the RNG
    for _ in range(2):
        g.restore(snap)
        for t in range(200, 500):
            g.step(inputs(t, g.player))
        assert g.state_hash() == straight


def test_dying_ends_the_run_after_the_death_animation():
    g = world(FLOOR)
    g.player.hurt(g, 500, 0)
    assert g.player.dying and g.status == "running"
    idle(g, 40)
    assert g.status == "dead"


def test_weapon_switching_only_selects_owned_weapons():
    g = world(FLOOR)
    g.step(select=3)
    assert g.weapon == 0
    g.owned[3] = True
    g.step(select=3)
    assert g.weapon == 3
    g.step(cycle=1)
    assert g.weapon == 0
    assert len(WEAPONS) == 5


def test_classic_agent_episodes_never_load_neon():
    import subprocess
    import sys

    code = ("import sys; from abuse_remake.agent.interface import AbuseEpisode; "
            "env = AbuseEpisode(seed=0); env.reset(); "
            "print(any(m.startswith('abuse_remake.engine.neon') for m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ---------------------------------------------------------------- map reachability (tile-graph model)
@pytest.mark.parametrize("name", [*SECTORS, "horde", "training"])
def test_every_console_exit_switch_and_weapon_is_reachable(name):
    from abuse_remake.engine.neon import nav

    m = load_map(name)
    seen, _, _ = nav.solve(m)
    targets = m.entities_of("console") + m.entities_of("exit") + m.entities_of("switch") + [
        e for e in m.entities_of("pickup") if e.args[0].startswith(("weapon", "boots", "key_"))]
    missing = [(e.char, e.tx, e.ty) for e in targets if not nav.near(seen, e.tx, e.ty)]
    assert not missing


def test_reactor_red_key_needs_the_boots_and_secrets_need_explosives():
    from abuse_remake.engine.neon import nav

    m = load_map("reactor")
    key = next(e for e in m.entities_of("pickup") if e.args[0] == "key_red")
    assert not nav.near(nav.explore(m), key.tx, key.ty)
    assert nav.near(nav.explore(m, boots=True), key.tx, key.ty)
    stash = next(e for e in m.entities_of("pickup") if e.args[0] == "phase")
    assert not nav.near(nav.solve(m)[0], stash.tx, stash.ty)


# ---------------------------------------------------------------- whole-campaign and balance checks
@pytest.mark.parametrize("difficulty", ["easy", "hard"])
def test_development_autopilot_finishes_the_campaign_with_real_physics(difficulty):
    """Full-map-access dev controller (not a playing agent): every sector, the boss and the exit are
    reachable with the real movement, and checkpoints restore cleanly when it dies."""
    from abuse_remake.engine.neon.autopilot import Autopilot

    g = NeonGame(seed=1, variant="campaign", difficulty=difficulty)
    bot = Autopilot(g)
    checkpoint, deaths = g.snapshot(), 0
    for _ in range(20000):
        g.step(bot.step(), bot.select)
        if any(e["kind"] in ("checkpoint", "sector_start") for e in g.events):
            checkpoint = g.snapshot()
        if g.status == "dead":
            deaths += 1
            g.restore(checkpoint)
            bot = Autopilot(g, patience=deaths * 37 % 90)
        if g.status == "won" or deaths > 10:
            break
    assert g.status == "won" and g.boss_dead and g.sector == 3
    assert deaths <= 3


def test_warden_telegraphs_its_stomp():
    g = NeonGame(seed=1, variant="campaign", sector=3)
    w = next(e for e in g.enemies if e.kind == "warden")
    w.alerted = True
    p = g.player
    p.x, p.y = w.cx + 60, w.floor - p.h
    w.cd2 = 0
    w.update(g)
    assert w.stomp_wind and not any(s.kind == "shock" for s in g.shots)
    assert any(e["kind"] == "stomp_wind" for e in g.events)
    for _ in range(20):
        w.update(g)
    assert any(s.kind == "shock" for s in g.shots)


def test_horde_scales_up_and_caps_upgrade_stacks():
    from abuse_remake.engine.neon import horde

    assert horde.hp_pct(1) == 100 and horde.hp_pct(11) == 160
    assert horde.damage_pct(21) == 160
    g = NeonGame(seed=2, variant="horde")
    g.horde.taken = ["amp"] * 3
    assert "amp" not in horde.eligible(g)
    g.horde.wave = 10
    g.player.hurt(g, 20, 0)
    assert g.player.hp == 100 - 20 * 127 // 100


def test_horde_moves_a_stuck_hostile_back_to_a_vent():
    from abuse_remake.engine.neon import horde

    g = NeonGame(seed=2, variant="horde")
    e = g.spawn_enemy("strider", 31 * 16, 28 * 16)
    e.x, e.y = 5000, 5000  # far away and never moving
    for _ in range(horde.STUCK_TICKS + 2):
        horde._unstick(g, [e])
    assert e.x < 2000


# ---------------------------------------------------------------- review follow-ups: boundaries
def test_upgrade_choice_is_refused_without_an_offer_or_with_a_bad_index():
    from abuse_remake.engine.neon import horde

    g = NeonGame(seed=2, variant="horde")
    h0 = g.state_hash()
    assert not horde.choose(g, 0)  # nothing offered yet
    g.horde.offer = ["amp", "rapid"]
    assert not horde.choose(g, 2) and not horde.choose(g, -1)
    assert g.horde.offer == ["amp", "rapid"] and not g.horde.taken
    assert horde.choose(g, 1) and g.horde.taken == ["rapid"]
    assert h0 != g.state_hash()


def test_timed_door_closes_and_waits_while_something_stands_in_it():
    g = world("""
####################
#..........a.......#
#..........a.......#
#..........a.......#
#.P.A......a.......#
####################
""".replace("A", "A"), seed=1)
    door = g.doors[0]
    g.switches[0].timer = 30
    p = g.player
    p.x = 4 * 16 + 8 - p.w // 2
    run(g, 1, interact=True)
    assert door.open
    p.x = 11 * 16  # standing in the doorway
    idle(g, 40)
    assert door.open  # never closes on the runner
    p.x = 4 * 16
    idle(g, 15)
    assert not door.open and g.grid.at(11, 3) != EMPTY


def test_energy_floor_hurts_only_while_live():
    g = world("""
####################
#..................#
#..................#
#..................#
#.P....^^^^........#
####################
""", difficulty="hard")
    from abuse_remake.engine.neon.objects import hazard_live

    p = g.player
    p.x = 8 * 16
    hp = p.hp
    for _ in range(140):
        g.step(NeonInput(px=p.cx + 50, py=p.cy))
        if not hazard_live(g):
            assert p.hp == hp or p.iframes  # no damage while safe (except the previous hit's protection)
        else:
            hp = p.hp
    assert p.hp < 100


def test_power_ups_shield_overcharge_haste_and_phase_do_what_they_say():
    from abuse_remake.engine.neon.objects import Pickup
    from abuse_remake.engine.neon.player import DASH_COOLDOWN, RUN

    g = world(FLOOR, difficulty="hard")
    p = g.player
    for kind in ("shield", "overcharge", "haste", "phase"):
        assert g.collect(Pickup(kind, 0, 0))
    assert p.hurt(g, 30, 0) == 0 and p.shield == 20  # the shield soaks the first 50
    assert g.player_damage(7) == 14
    run(g, 20, x=1)
    assert p.vx > RUN
    p.iframes = 0
    run(g, 1, dash=True, x=1)
    assert p.dash_cd < DASH_COOLDOWN
    assert not g.collect(Pickup("health", 0, 0))  # full integrity: left on the floor


def test_elevator_can_be_called_and_stops_rather_than_crush_a_rider():
    g = world("""
##########
#........#
#........#
#........#
#...|....#
#...|....#
#...|....#
#...|....#
#...|....#
#...|....#
#.P.L....#
##########
""")
    el = g.elevators[0]
    el.y = el.top  # parked at the top
    p = g.player
    p.x = el.x - p.w - 2  # beside the shaft, not under the platform
    run(g, 1, interact=True)
    assert el.target == el.bottom
    run(g, 80)
    assert el.y == el.bottom and el.target == -1  # arrived and waits for a rider
    # a low ceiling over the top stop: it must halt, not push the rider into the roof
    g2 = world("""
##########
#........#
#...|....#
#...|....#
#...|....#
#...|....#
#...|....#
#.P.L....#
##########
""")
    el2 = g2.elevators[0]
    p2 = g2.player
    p2.x, p2.y = el2.x + 16, el2.y - p2.h
    run(g2, 120)
    assert p2.y >= 16 and el2.y > el2.top and el2.target == -1


def test_warden_low_laser_can_be_jumped_and_the_high_one_crouched_under():
    from abuse_remake.engine.neon.player import NeonInput as In

    def sweep(high: bool, action) -> int:
        g = NeonGame(seed=1, variant="campaign", sector=3)
        w = next(e for e in g.enemies if e.kind == "warden")
        g.enemies = [w]
        w.alerted, w.phase, w.cd, w.cd2 = True, 3, 9999, 9999
        p = g.player
        p.x, p.y = w.left - 20, w.floor - p.h
        w.laser, w.laser_t, w.laser_high, w.laser_hit = "charge", 1, high, False
        hp = p.hp
        for _ in range(45):
            g.step(action(g, w))
        return hp - p.hp

    def stand(g, w):
        return In(px=g.player.cx + 50, py=g.player.cy)

    def jump_when_close(g, w):
        p = g.player
        near = w.laser == "sweep" and abs(w.sweep_x - p.cx) < 140  # about six ticks ahead of the beam
        return In(jump=near, px=p.cx + 50, py=p.cy)  # held for a full jump while it passes

    def crouch(g, w):
        return In(y=1, px=g.player.cx + 50, py=g.player.cy)

    assert sweep(False, stand) > 0 and sweep(False, jump_when_close) == 0
    assert sweep(True, stand) > 0 and sweep(True, crouch) == 0


def test_warden_stays_dormant_until_the_runner_comes_close():
    g = NeonGame(seed=1, variant="campaign", sector=3)
    w = next(e for e in g.enemies if e.kind == "warden")
    for _ in range(60):
        g.step()
    assert not w.alerted and not [s for s in g.shots if s.hostile]
    p = g.player
    p.x = w.x - 300
    for _ in range(3):
        g.step()
    assert w.alerted


def test_climbing_is_the_same_speed_both_ways_and_down_jump_drops_off_a_ladder_top():
    g = world("""
################
#..............#
#..............#
#..............#
#######H########
#......H.......#
#......H.......#
#......H.......#
#......H.......#
#.P....H.......#
################
""")
    p = g.player
    p.x = 7 * 16 + 8 - p.w // 2
    y0 = p.y
    run(g, 20, y=-1)
    up = y0 - p.y
    y1 = p.y
    run(g, 20, y=1)
    down = p.y - y1
    assert up == down == 50
    # stand on the ladder top, then S + Space drops straight through it
    p.x, p.y = 7 * 16 + 8 - p.w // 2, 4 * 16 - p.h
    p.climbing, p.drop, p.vy = False, 0, 0
    run(g, 3)
    assert p.grounded and not p.climbing
    run(g, 2, y=1, jump=True)
    run(g, 10)
    assert p.bottom > 4 * 16 + 8 and not p.climbing


def test_dash_off_an_elevator_does_not_keep_riding_it():
    g = world("""
##############
#............#
#............#
#............#
#...|........#
#...|........#
#...|........#
#...|........#
#.P.L........#
##############
""")
    el = g.elevators[0]
    p = g.player
    p.x = el.x + 16
    run(g, 12)  # boards; the ride starts
    assert el.moving
    run(g, 1, dash=True, x=1)  # the press tick: still standing on it while it moves
    y = p.y
    run(g, 6, x=1)
    assert p.x > el.x + el.w  # off the platform
    assert p.y >= y  # not lifted with the elevator once dashing


def test_neon_inputs_are_normalised_so_truthy_values_hash_the_same():
    a = world(FLOOR)
    b = world(FLOOR)
    for t in range(30):
        a.step(NeonInput(x=1, jump=t % 9 == 0, fire=True, px=300, py=60))
        b.step(NeonInput(x=1, jump=1 if t % 9 == 0 else 0, fire=1, px=300, py=60))
    assert a.state_hash() == b.state_hash()


def test_training_targets_float_at_their_tile():
    g = NeonGame(seed=1, variant="training")
    m = g.map
    tgt = next(e for e in g.enemies if e.kind == "target")
    ent = next(e for e in m.entities if e.kind == "enemy" and e.args[0] == "target" and abs(e.tx * 16 + 8 - tgt.cx) < 2)
    idle(g, 5)
    assert abs(tgt.cy - (ent.ty * 16 + 8)) <= 6


def test_horde_unsticks_stingers_too_and_always_updates_hostiles():
    from abuse_remake.engine.neon import horde

    g = NeonGame(seed=2, variant="horde")
    s = g.spawn_enemy("stinger", 40 * 16, 10 * 16)
    s.x, s.y = 9000, 9000
    for _ in range(horde.STUCK_TICKS + 2):
        horde._unstick(g, [s])
    assert s.x < 2000
    far = g.spawn_enemy("crawler", 60 * 16, 28 * 16)
    g.player.x = 3 * 16
    far.alerted, far.state = False, "idle"
    x = far.x
    for _ in range(10):
        g.step()
    assert far.x != x  # updated even though it is far from the runner


def test_horde_heavy_spawns_use_floor_vents():
    from abuse_remake.engine.neon import horde

    g = NeonGame(seed=3, variant="horde")
    for _ in range(20):
        horde._spawn(g, "strider")
    for e in g.enemies:
        if e.kind == "strider":
            assert not g.grid.rect_hits(e.x, e.y, e.w, e.h, (1,)), (e.x, e.y)


def test_nano_repair_stacks():
    g = NeonGame(seed=2, variant="horde")
    p = g.player
    p.hp = 50
    g.upgrades["nano"] = 1
    for _ in range(120):
        g.step()
    one = p.hp - 50
    p.hp = 50
    g.upgrades["nano"] = 3
    for _ in range(120):
        g.step()
    assert p.hp - 50 > one >= 1


def test_v1_neon_traces_are_refused_clearly(tmp_path):
    import json

    from abuse_remake.game.human_replay import replay_human

    v1 = tmp_path / "v1.jsonl"
    v1.write_text(json.dumps({"kind": "header", "format": "neon-trace-1"}) + "\n")
    with pytest.raises(SystemExit, match="v1"):
        replay_human(v1)
    mixed = tmp_path / "mixed.jsonl"
    mixed.write_text("\n".join(json.dumps(r) for r in (
        {"kind": "header", "format": "human-trace-1"},
        {"kind": "new_game", "rules": "neon", "seed": 1, "variant": "tutorial", "difficulty": "hard"})) + "\n")
    with pytest.raises(SystemExit, match="v1"):
        replay_human(mixed)


def test_replay_restart_sector_returns_to_the_start_of_the_current_sector():
    from abuse_remake.game.human_replay import _NeonSession

    s = _NeonSession({"seed": 2, "variant": "campaign", "difficulty": "hard", "sector": 0})
    g = s.game
    ex, ey = g.exit
    p = g.player
    p.x, p.y = ex - p.w // 2, ey - p.h
    s.step({"x": 0, "y": 0, "interact": 1, "px": p.cx + 50, "py": p.cy})
    for _ in range(60):
        s.step({"x": 0, "y": 0, "px": 0, "py": 0})
    assert g.sector == 1
    for _ in range(30):
        s.step({"x": 1, "y": 0, "px": 0, "py": 0})
    s.restore("level_start")
    assert s.game.sector == 1 and s.game.frames < g.frames + 1


def test_campaign_elevators_stop_flush_with_the_floors_they_serve():
    from abuse_remake.engine.neon.tilemap import SOLID as WALL

    for sector in range(4):
        g = NeonGame(seed=1, variant="campaign", sector=sector)
        for el in g.elevators:
            left, right = (el.x >> 4) - 1, (el.x + el.w) >> 4
            for stop in (el.top, el.bottom):
                assert stop % 16 == 0
                beside = {g.grid.at(left, stop >> 4), g.grid.at(right, stop >> 4)}
                under = g.grid.at((el.x + el.w // 2) >> 4, stop >> 4)
                assert WALL in beside or under == WALL, (g.map.name, stop)
