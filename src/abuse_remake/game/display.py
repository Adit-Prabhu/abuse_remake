"""The window and the surfaces frames are drawn on. Presentation only.

Frames are drawn on opaque surfaces (no alpha channel), then copied to the window. A macOS window
surface is ARGB: drawn straight onto it, the level's tiles left its alpha at 0, and pygame-ce then
filled each text box and the ghost's whole rectangle with colour. The dummy driver used by tests
has no alpha channel, so the fault never showed there; ``tests/test_display.py`` stands in for the
macOS format.

The window is resizable and scaled (``pygame.SCALED``): the frame keeps its size and SDL scales it
to the window, letterboxed, so the mouse still maps to frame pixels. F11, Alt+Enter and Cmd+F (or
Ctrl+Cmd+F, the macOS shortcut) toggle full screen.
"""

from __future__ import annotations

import pygame

OPAQUE_MASKS = (0xFF0000, 0xFF00, 0xFF, 0)


def opaque_surface(size: tuple[int, int]) -> pygame.Surface:
    """A 32-bit surface with no alpha channel, whatever the display's format."""
    return pygame.Surface(size, 0, 32, OPAQUE_MASKS)


def window_flags(args) -> int:
    """Resizable and scaled, or full screen; a plain surface for headless runs (``--frames``)."""
    if getattr(args, "frames", 0):
        return 0
    flags = pygame.SCALED | pygame.RESIZABLE
    if getattr(args, "fullscreen", False):
        flags |= pygame.FULLSCREEN
    return flags


def is_fullscreen_key(key: int, mod: int) -> bool:
    if key == pygame.K_F11:
        return True
    if key in (pygame.K_RETURN, pygame.K_KP_ENTER) and mod & pygame.KMOD_ALT:
        return True
    return key == pygame.K_f and bool(mod & pygame.KMOD_META)
