"""Neon design contracts, authored before the separate optional simulation."""

import pytest

from abuse_remake.engine.neon import NeonGame, Pickup
from abuse_remake.engine.view import Inputs


def quiet(variant="campaign"):
    g = NeonGame(seed=7, variant=variant)
    g.enemies.clear()
    g.hazards.clear()
    return g


def test_neon_has_a_new_campaign_and_independent_horde_map():
    campaign, horde = NeonGame(), NeonGame(variant="horde")
    assert campaign.width > horde.width
    assert len(campaign.relays) == 3
    assert {e.kind for e in campaign.enemies} == {"drone", "stalker", "sentry", "titan"}
    assert horde.relays == []
    with pytest.raises(ValueError):
        NeonGame(variant="unknown")


def test_dash_stops_at_locked_door_and_cannot_be_spammed():
    g = quiet()
    door = g.doors[0]
    g.player.x = door[0] - g.player.w - 2
    assert g.request_dash(1)
    assert not g.request_dash(1)
    for _ in range(5):
        g.step(Inputs(x=1))
    assert g.player.x + g.player.w <= door[0]
    assert not g.request_dash(1)


def test_jump_lands_and_floor_never_tunnels():
    g = quiet()
    initial = g.player.y
    g.step(Inputs(y=-1))
    assert g.player.y < initial and not g.player.grounded
    for _ in range(40):
        g.step()
    assert g.player.y == initial and g.player.grounded


def test_first_platform_is_reachable_by_a_normal_jump():
    g = quiet()
    g.player.x = 280
    g.step(Inputs(y=-1))
    for _ in range(6):
        g.step()
    lowest_feet = g.player.y + g.player.h
    for _ in range(20):
        g.step(Inputs(x=1))
        lowest_feet = min(lowest_feet, g.player.y + g.player.h)
        if g.player.grounded:
            break
    assert lowest_feet <= 425
    assert g.player.grounded and g.player.y + g.player.h == 425


def test_lethal_hit_cannot_be_healed_or_saved_in_the_same_tick():
    from abuse_remake.engine.neon import Shot

    g = quiet()
    p = g.player
    p.hp = 5
    p.x = g.relays[0].x - 10
    g.pickups = [Pickup("health", p.x, p.y)]
    g.shots = [Shot(p.x, p.y + 15, 1, 0, 0, 20, True)]
    g.step(Inputs(y=1))
    assert p.hp == 0 and g.status == "dead"
    assert not g.relays[0].active and len(g.pickups) == 1


def test_dash_protects_six_ticks_then_damage_resumes():
    g = quiet()
    assert g.request_dash(1)
    for _ in range(6):
        # Damage occurs in the enemies phase, before end-of-tick decay.
        g._enemies = lambda: g.hurt_player(20)
        g.step()
        assert g.player.hp == 100
    g.step()
    assert g.player.hp == 80


def test_airborne_player_above_hazard_is_safe():
    g = quiet()
    g.hazards = [(100, 200)]
    g.frames = 60
    g.player.y = 474
    g.player.vy = -5
    g.player.grounded = False
    g.step()
    assert g.player.hp == 100


def test_relays_require_proximity_action_and_security_clearance():
    g = quiet()
    g.step(Inputs(y=1))
    assert not g.relays[0].active
    relay = g.relays[0]
    g.player.x = relay.x - 10
    e = g.spawn_enemy("sentry", relay.x + 100, 480)
    g.step()
    g.step(Inputs(y=1))
    assert not relay.active
    g.enemies.remove(e)
    g.step()
    g.step(Inputs(y=1))
    assert relay.active and not g.door_locked(0)
    assert any(e["kind"] == "checkpoint" for e in g.events)
    # Held action does not repeatedly save.
    g.step(Inputs(y=1))
    assert not any(e["kind"] == "checkpoint" for e in g.events)


def test_relay_clearance_ignores_enemies_behind_the_next_locked_door():
    g = quiet()
    r = g.relays[0]
    g.spawn_enemy("drone", g.doors[0][0] + 50, 260)
    g.player.x = r.x - 10
    assert g.relay_secure(r)
    g.step(Inputs(y=1))
    assert r.active


def test_projectiles_cannot_hit_through_locked_doors():
    g = quiet()
    g.player.x = 1350
    e = g.spawn_enemy("dummy", 1470, 480)
    g.step(Inputs(b2=1, pointer_x=1700, pointer_y=495), select=1)
    for _ in range(8):
        g.step()
    assert e.hp == 120


def test_sentry_shields_face_player_but_rail_bypasses_them():
    g = quiet()
    e = g.spawn_enemy("sentry", 300, 480)
    g._hurt_enemy(e, 12, 0, 100)
    assert e.hp == 76
    g._hurt_enemy(e, 12, 0, 500)
    assert e.hp == 64
    g._hurt_enemy(e, 40, 1, 100)
    assert e.hp == 24


def test_extraction_requires_all_relays_and_action():
    g = quiet()
    g.player.x = g.exit_x
    g.step(Inputs(y=1))
    assert g.status == "running"
    for r in g.relays:
        r.active = True
    g.step()
    assert g.status == "running"
    g.step(Inputs(y=1))
    assert g.status == "won"
    before = g.state_hash()
    g.step(Inputs(x=1, b2=1))
    assert g.state_hash() == before


def test_powerups_expire_and_shield_absorbs_damage():
    g = quiet()
    p = g.player
    g.pickups = [Pickup("shield", p.x, p.y), Pickup("overcharge", p.x, p.y), Pickup("speed", p.x, p.y)]
    g.step()
    assert p.shield == 60 and p.overcharge > 0 and p.speed > 0
    g.hurt_player(20)
    assert p.hp == 100 and p.shield == 40
    for _ in range(151):
        g.step()
    assert p.shield == p.overcharge == p.speed == 0


def test_rail_pierces_targets_pulse_does_not_and_ammo_refuses():
    def shoot(slot):
        g = quiet()
        g.spawn_enemy("dummy", 230, 480)
        g.spawn_enemy("dummy", 300, 480)
        g.step(Inputs(b2=1, pointer_x=500, pointer_y=495), select=slot)
        for _ in range(10):
            g.step()
        return g
    pulse, rail = shoot(0), shoot(1)
    assert sum(e.hp < 120 for e in pulse.enemies) == 1
    assert sum(e.hp < 120 for e in rail.enemies) == 2
    assert rail.ammo[1] == 23
    rail.ammo[1] = 0
    rail.step(Inputs(b2=1, pointer_x=500, pointer_y=495))
    assert not any(e["kind"] == "shot" for e in rail.events)
    rail.step(select=99)
    assert rail.weapon == 1


def test_vortex_creates_lingering_area_damage():
    g = quiet()
    target = g.spawn_enemy("dummy", 230, 480)
    g.step(Inputs(b2=1, pointer_x=500, pointer_y=495), select=2)
    for _ in range(10):
        g.step()
    assert g.fields and target.hp < 120


def test_horde_wave_clears_drops_supplies_and_escalates():
    g = NeonGame(seed=3, variant="horde")
    for _ in range(50):
        g.step()
    assert g.wave == 1 and len(g.enemies) == 4
    g.enemies.clear()
    g.step()
    assert g.cleared == 1 and len(g.pickups) >= 3
    for _ in range(76):
        g.step()
    assert g.wave == 2 and len(g.enemies) == 6
    g.player.hp = 0
    g.step()
    assert g.status == "dead"


def test_late_horde_waves_keep_every_enemy_inside_the_arena():
    g = NeonGame(seed=0, variant="horde")
    g.wave, g.break_ticks = 39, 1
    g.step()
    assert len(g.enemies) == 82
    assert all(0 <= e.x and e.x + e.w <= g.width for e in g.enemies)


@pytest.mark.parametrize("variant", ["campaign", "horde", "tutorial"])
def test_determinism_and_repeated_snapshot_restore(variant):
    a, b = NeonGame(seed=4, variant=variant), NeonGame(seed=4, variant=variant)
    for i in range(150):
        inp = Inputs(x=1 if i % 40 < 25 else -1, b2=i % 3 == 0, pointer_x=600, pointer_y=460)
        a.step(inp)
        b.step(inp)
    assert a.state_hash() == b.state_hash()
    snap = a.snapshot()
    expected = a.state_hash()
    for _ in range(3):
        a.step(Inputs(x=1))
        a.restore(snap)
        assert a.state_hash() == expected


def test_tutorial_requires_performed_actions_and_has_no_hostile_enemies():
    g = NeonGame(variant="tutorial")
    for _ in range(30):
        g.step()
    assert g.lesson == 0 and g.player.hp == 100
    for _ in range(12):
        g.step(Inputs(x=1))
    assert g.lesson == 1
    g.step(Inputs(y=-1))
    assert g.lesson == 2


def test_tutorial_can_be_finished_with_real_controls():
    g = NeonGame(variant="tutorial")
    for _ in range(12):
        g.step(Inputs(x=1))
    g.step(Inputs(y=-1))
    for _ in range(80):
        g.step(Inputs(b2=1, pointer_x=565, pointer_y=498))
        if g.lesson == 3:
            break
    assert g.lesson == 3
    g.step(select=1)
    assert g.lesson == 4
    assert g.request_dash(1)
    for _ in range(90):
        g.step(Inputs(x=1))
    assert g.lesson == 6
    for _ in range(100):
        g.step(Inputs(x=-1 if g.player.x > 940 else 1, y=1))
        if g.status == "won":
            break
        g.step()  # release action between attempts
    assert g.status == "won"


def test_neon_is_not_available_to_classic_agent_episodes():
    from abuse_remake.agent.interface import AbuseEpisode

    ep = AbuseEpisode("level01", seed=0)
    assert ep._game.__class__.__name__ == "Game"
    assert ep._game.remastered is None
