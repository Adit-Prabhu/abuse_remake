"""The title menu, Horde's briefing, the controls screen, the upgrade cards' keys and the power
prompt: the parts of the front end that teach a new player. Headless (SDL dummy drivers)."""

import pygame
import pytest

from abuse_remake.engine.horde import ARENAS
from abuse_remake.engine.view import Inputs


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    return tmp_path


def make_app(*extra, scale="2"):
    from abuse_remake.game.app import App, parse_args

    return App(parse_args(["--frames", "1", "--no-audio", "--seed", "3", "--scale", scale, *extra]))


def key(app, k):
    return app.on_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))


# --- the title -----------------------------------------------------------------------------------
def test_the_campaign_starts_with_training_unless_a_level_is_asked_for():
    from abuse_remake.game.app import parse_args

    assert parse_args([]).menu_level == "level00"
    assert parse_args(["--level", "level02"]).menu_level == "level02"
    assert parse_args(["--skip-title"]).level == "level01"  # straight into play: Level 1, as before


def labels(app):
    from abuse_remake.game.screens import menu_items

    return [it["label"] for it in menu_items(app)]


def test_enter_on_the_title_opens_the_levels_and_enter_again_starts_training(home):
    app = make_app()
    app._to_title()
    assert app.state == "title" and app._menu_key() == "campaign" and app.level == "level00"
    key(app, pygame.K_RETURN)
    assert app.state == "title" and app.menu_page == "campaign" and app._menu_key() == "level"
    key(app, pygame.K_RETURN)
    assert app.state == "play" and app.game.level == "level00" and app.horde is False


def test_each_list_holds_only_its_own_choices(home):
    """The student, 2026-10-27: left and right on PLAY CAMPAIGN chose a level and on HORDE an
    arena, on one page, which was easy to confuse. Each now opens its own list."""
    from abuse_remake.engine import campaign

    app = make_app()
    app._to_title()
    main = labels(app)
    assert "PLAY CAMPAIGN" in main and "HORDE" in main
    assert not any(t.upper() in main for t in ("Training", "Level 1", "Level 2"))  # no level or arena
    assert not any(a.title.split(" (")[0].upper() in main for a in ARENAS.values())
    key(app, pygame.K_RETURN)
    levels = [campaign.title(n).upper() for n in campaign.playable_levels()]
    assert labels(app) == [*levels, "BACK"]  # levels only
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)
    assert app.menu_page == "horde"
    assert labels(app) == [*(a.title.split(" (")[0].upper() for a in ARENAS.values()), "BACK"]  # arenas only


def test_left_and_right_no_longer_change_the_level_or_arena_on_the_main_page(home):
    app = make_app()
    app._to_title()
    key(app, pygame.K_LEFT)
    assert app.state == "title" and app.menu_page == "main" and app.args.menu_level == "level00"
    key(app, pygame.K_RIGHT)  # right goes into the list, as the line's arrow shows
    assert app.menu_page == "campaign" and app.args.menu_level == "level00"


def test_the_lists_move_and_preview_with_the_keys(home):
    app = make_app()
    app._to_title()
    key(app, pygame.K_RETURN)
    key(app, pygame.K_DOWN)  # Level 1: the backdrop follows
    assert app.args.menu_level == "level01" and app.game.level == "level01" and not app.horde
    key(app, pygame.K_ESCAPE)  # back, not quit
    assert app.state == "title" and app.menu_page == "main" and app._menu_key() == "campaign"
    key(app, pygame.K_RETURN)  # the list opens on the level chosen last
    assert app._menu_item()["level"] == "level01"
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_DOWN)  # HORDE: the backdrop becomes its arena
    assert app._menu_key() == "horde" and app.horde and app.game.horde is not None
    key(app, pygame.K_RETURN)
    seen = {app.game.horde.state["arena"]}
    for _ in range(len(ARENAS) - 1):
        key(app, pygame.K_DOWN)
        seen.add(app.game.horde.state["arena"])
    assert seen == set(ARENAS)
    key(app, pygame.K_RETURN)
    assert app.state == "briefing"  # how Horde works, before wave 1
    key(app, pygame.K_ESCAPE)
    assert app.state == "title" and app.menu_page == "horde"  # back in the arena list
    key(app, pygame.K_DOWN)
    assert app._menu_key() == "back"
    key(app, pygame.K_RETURN)
    assert app.menu_page == "main" and app._menu_key() == "horde"
    key(app, pygame.K_UP)  # back to the campaign: a campaign game again, at the chosen start
    assert app._menu_key() == "campaign" and not app.horde and app.game.level == "level01"


def test_leaving_a_run_returns_to_the_main_page_on_its_line(home):
    app = make_app()
    app._to_title()
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)
    key(app, pygame.K_DOWN)  # the second arena
    key(app, pygame.K_RETURN)
    key(app, pygame.K_RETURN)
    assert app.state == "play" and app.horde
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_t)
    assert app.state == "title" and app.menu_page == "main" and app._menu_key() == "horde"


def test_the_menu_works_with_the_mouse(home):
    app = make_app()
    app._to_title()
    app.draw()  # lays the rows out

    def move(i):
        app.on_event(pygame.event.Event(pygame.MOUSEMOTION, pos=app.screens.rows[i][0].center, rel=(0, 0),
                                        buttons=(0, 0, 0)))

    def click(pos):
        app.on_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        app.draw()

    move(1)
    assert app._menu_key() == "horde" and app.horde
    click(app.screens.rows[1][0].center)
    assert app.menu_page == "horde" and app.state == "title"
    move(2)
    assert app.arena == list(ARENAS)[2] and app.game.horde.state["arena"] == app.arena
    click(app.screens.rows[2][0].center)
    assert app.state == "briefing"
    click((5, 5))
    assert app.state == "play"


def test_a_gamepad_drives_the_menus(home):
    app = make_app()
    app._to_title()

    def pad(button):
        app.on_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=button, joy=0, instance_id=0))

    app.on_event(pygame.event.Event(pygame.JOYHATMOTION, value=(0, -1), joy=0, instance_id=0, hat=0))
    assert app._menu_key() == "horde"
    pad(0)
    assert app.menu_page == "horde"
    pad(0)
    assert app.state == "briefing"
    pad(1)
    assert app.state == "title" and app.menu_page == "horde"
    pad(1)
    assert app.state == "title" and app.menu_page == "main"
    pad(1)
    assert app.state == "title"  # B never quits from the title


def test_switching_mode_keeps_the_menu_on_the_mode_line(home):
    app = make_app()
    app._to_title()
    while app._menu_key() != "mode":
        key(app, pygame.K_DOWN)
    key(app, pygame.K_RIGHT)
    assert not app.modern and app.state == "title" and app._menu_key() == "mode"
    key(app, pygame.K_RETURN)
    assert app.modern and app._menu_key() == "mode"


def test_the_old_title_letters_still_work(home):
    app = make_app()
    app._to_title()
    key(app, pygame.K_h)
    assert app.horde and app._menu_key() == "horde"
    key(app, pygame.K_a)
    assert app.game.horde.state["arena"] != "prison"


# --- help, briefing, pause -------------------------------------------------------------------------
def test_f1_shows_the_controls_from_play_and_the_game_waits(home):
    app = make_app()
    app.state = "play"
    frames = app.game.frames
    key(app, pygame.K_F1)
    assert app.state == "help"
    app.advance(1.0)
    assert app.game.frames == frames  # nothing ran behind the help screen
    key(app, pygame.K_F1)
    assert app.state == "paused"  # back to the game, paused, so nothing hits you as it closes


def test_r_never_ends_a_horde_run_by_accident(home):
    app = make_app("--horde")
    app.state = "play"
    for i in range(30):
        app.tick(i)
    frames = app.game.frames
    key(app, pygame.K_r)
    assert app.game.frames == frames and app.state == "play"  # no consoles in Horde: R does nothing
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_r)  # the pause screen's R restarts the run on purpose
    assert app.state == "play" and app.game.frames == 0


def test_t_on_the_pause_screen_goes_back_to_the_title(home):
    app = make_app()
    app.state = "play"
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_t)
    assert app.state == "title"


# --- the upgrade cards -----------------------------------------------------------------------------
def test_arrows_and_enter_choose_a_card_and_nothing_moves_meanwhile(home):
    app = make_app("--horde")
    app.state = "play"
    st = app.game.horde.state
    st["cards"] = ["rockets", "medkit", "ammo"]
    x = app.game.player.x
    app.scripted_inputs = lambda tick: Inputs(x=1, b2=1, pointer_x=app.game.player.x + 50,
                                              pointer_y=app.game.player.y - 20)
    for i in range(6):
        app.tick(i)
    assert app.game.player.x == x  # the cards hold the player still: arrows choose, not walk
    app.game.player.set_hp(40)
    key(app, pygame.K_RIGHT)
    key(app, pygame.K_RIGHT)
    assert app.card_focus == 2
    key(app, pygame.K_LEFT)
    key(app, pygame.K_RETURN)
    app.tick(6)
    assert not st["cards"] and app.game.player.hp == 100  # the middle card: the medkit
    assert any("MEDKIT" in m[0] for m in app.hud.messages)


def test_a_power_card_shows_how_to_use_it_until_it_is_used(home):
    from abuse_remake.engine.behaviors.player import FLY_POWER

    app = make_app("--horde")
    app.state = "play"
    st = app.game.horde.state
    st["cards"] = ["flight", "medkit", "ammo"]
    p = app.game.player
    app.scripted_inputs = lambda tick: Inputs(pointer_x=p.x + 50, pointer_y=p.y - 20)
    key(app, pygame.K_1)
    app.tick(0)
    assert app.game.player.lvars["special_power"] == FLY_POWER
    assert app.mhud.banner is not None and app.mhud.banner["power"] == FLY_POWER
    assert app.power_used is False  # the HUD's power slot keeps pulsing
    app.scripted_inputs = lambda tick: Inputs(b1=1, pointer_x=p.x + 50, pointer_y=p.y - 20)
    app.tick(1)
    assert app.power_used is True


def test_the_cleared_wave_reports_its_bonuses_to_the_cards(home):
    app = make_app("--horde")
    app.state = "play"
    st = app.game.horde.state
    st.update(wave=3, cleared=2, to_spawn=[], alive=[], wave_hp_lost=0)
    st["break"] = False  # wave 3 is on, and nothing of it is left: the next tick clears it
    app.tick(0)
    assert st["cards"] and app.last_clear == {"bonus": 600, "clean": 900} and app.card_focus == 0


# --- every screen draws -----------------------------------------------------------------------------
@pytest.mark.parametrize("scale", ["1", "2", "3"])
@pytest.mark.parametrize("mode", ["remastered", "classic"])
def test_every_screen_draws_at_every_scale(home, scale, mode):
    app = make_app("--mode", mode, scale=scale)
    states = ["title", "help", "play", "paused", "dead", "complete"]
    if mode == "remastered":
        states += ["briefing"]
    for state in states:
        app.state = state
        app.help_return = "title"
        app.draw()
    if mode == "remastered":
        app.state = "title"
        app.best_time = lambda level: "12:34.56"  # the widest notes the lists show
        app.best_score = lambda arena: 1234567
        for page in ("campaign", "horde"):
            app._open_page(page)
            app.draw()
        h = make_app("--horde", "--arena", "pit", scale=scale)
        h.state = "play"
        h.game.horde.state["cards"] = ["speed", "dash", "ultra_health"]
        h.last_clear = {"bonus": 200, "clean": 300}
        h.draw()
        h.game.horde.state["cards"] = []
        h.mhud.show_power(2)
        h.draw()
        h.state = "horde_over"
        h.finish = {"rank": 1, "top": [{"score": 10, "cleared": 1, "kills": 2}]}
        h.draw()
