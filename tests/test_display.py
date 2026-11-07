"""What reaches a real display: every frame is drawn on opaque surfaces whatever the display's
pixel format, and the window can be resized and put into full screen. Headless (SDL dummy
drivers); the macOS window format is stood in for by an ARGB surface."""

import numpy as np
import pygame
import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUSE_REMAKE_HOME", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    return tmp_path


def make_app(*extra):
    from abuse_remake.game.app import App, parse_args

    return App(parse_args(["--frames", "1", "--no-audio", "--seed", "1", "--scale", "2", *extra]))


def rgba(surf):
    w, h = surf.get_size()
    return np.frombuffer(pygame.image.tobytes(surf, "RGBA"), np.uint8).reshape(h, w, 4)


# --- opaque frames -------------------------------------------------------------------------------
@pytest.mark.parametrize("extra", [(), ("--mode", "classic"), ("--horde", "--arena", "rooftop")])
def test_frames_are_drawn_on_surfaces_without_an_alpha_channel(home, extra):
    """A macOS window surface is ARGB. Drawn straight onto it, the level's tiles left its alpha
    at 0, and pygame-ce then filled every text box and the ghost's whole rectangle with colour:
    the HUD's text showed as white bars and the ghost had a black box."""
    app = make_app(*extra)
    assert app.screen.get_masks()[3] == 0
    assert app.renderer.surface.get_masks()[3] == 0


def test_a_display_with_an_alpha_channel_shows_exactly_the_drawn_frame(home):
    app = make_app()
    app.state = "play"
    app.hud.say("Station secured!")
    window = pygame.Surface(app.screen.get_size(), pygame.SRCALPHA, 32)  # like the Cocoa window
    window.fill((0, 0, 0, 0))
    app.window = window
    app.draw()
    shown, drawn = rgba(window), rgba(app.screen)
    assert shown[..., 3].min() == 255
    assert np.array_equal(shown[..., :3], drawn[..., :3])


def test_text_on_the_frame_keeps_the_background_between_its_letters(home):
    app = make_app()
    app.state = "play"
    app.draw()
    before = rgba(app.screen).copy()
    label = app.hud.font.render("|  |", True, (255, 255, 255))
    app.screen.blit(label, (40, 40))
    after = rgba(app.screen)
    w, h = label.get_size()
    gap = (40 + w // 2, 40 + h // 2)  # between the bars: no glyph there
    assert tuple(after[gap[1], gap[0], :3]) == tuple(before[gap[1], gap[0], :3])


def test_the_ghost_is_see_through_with_no_box_around_it(home):
    from abuse_remake.game.remaster import GhostPainter

    app = make_app("--level", "level00")
    painter = GhostPainter(pygame, app.sprites)
    fig = app.game.world.types["DARNEL"].sequences["running"][0]
    img = painter._image(fig, 1)
    assert img.get_alpha() in (None, 255)  # see-through in its pixels, not by a surface alpha
    # the old frame surface on macOS: an alpha channel (no blending flag) that the tiles left at
    # 0; a sprite with a surface alpha drawn onto it painted its whole rectangle
    back = pygame.Surface((img.get_width() + 4, img.get_height() + 4), 0, 32,
                          (0xFF0000, 0xFF00, 0xFF, 0xFF000000))
    back.fill((40, 80, 120, 0))
    back.blit(img, (2, 2))
    h, w = img.get_height(), img.get_width()
    shown = rgba(back)[2:2 + h, 2:2 + w, :3]
    alpha = rgba(img)[..., 3]
    clear = alpha == 0
    assert clear.sum() > 100  # the sprite's own background
    assert (shown[clear] == (40, 80, 120)).all()  # left exactly as it was: no box
    assert 0 < alpha.max() < 255  # translucent, not invisible


# --- the window ----------------------------------------------------------------------------------
def test_the_window_is_resizable_and_scales_the_frame(home):
    from abuse_remake.game.display import window_flags

    class Args:
        frames = 0
        fullscreen = False

    flags = window_flags(Args())
    assert flags & pygame.RESIZABLE and flags & pygame.SCALED
    assert not flags & pygame.FULLSCREEN
    Args.fullscreen = True
    assert window_flags(Args()) & pygame.FULLSCREEN
    Args.frames = 5  # headless runs keep a plain surface
    assert window_flags(Args()) == 0


@pytest.mark.parametrize("key,mod", [(pygame.K_F11, 0), (pygame.K_RETURN, pygame.KMOD_LALT),
                                     (pygame.K_f, pygame.KMOD_LMETA),
                                     (pygame.K_f, pygame.KMOD_LMETA | pygame.KMOD_LCTRL)])
def test_full_screen_keys_toggle_in_every_state_and_do_nothing_else(home, monkeypatch, key, mod):
    from abuse_remake.game.display import is_fullscreen_key

    assert is_fullscreen_key(key, mod)
    app = make_app()
    app.args.frames = 0  # behave as with a real window
    calls = []
    monkeypatch.setattr(pygame.display, "toggle_fullscreen", lambda: calls.append(1) or 1)
    for state in ("title", "play", "paused"):
        app.state = state
        app.pending_dash = False
        app.on_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))
        assert app.state == state  # Alt+Enter does not also start the game, Cmd+F does not dash
        assert not app.pending_dash
    assert len(calls) == 3
    assert app.args.fullscreen is True  # three toggles: on, off, on


def test_plain_keys_are_not_full_screen_keys():
    from abuse_remake.game.display import is_fullscreen_key

    assert not is_fullscreen_key(pygame.K_f, 0)  # the dash
    assert not is_fullscreen_key(pygame.K_RETURN, 0)  # start, continue
