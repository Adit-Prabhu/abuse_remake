"""Registry mapping each original Lisp function name to its Python port."""

from __future__ import annotations

from collections.abc import Callable

REGISTRY: dict[str, Callable] = {}


def lisp(name: str):
    """Register ``fn`` as the port of the Lisp (or compiled C) function ``name``."""

    def deco(fn):
        if name in REGISTRY:
            raise ValueError(f"{name} registered twice")
        REGISTRY[name] = fn
        return fn

    return deco


def registry() -> dict[str, Callable]:
    # Importing the modules fills REGISTRY.
    from . import enemies, logic, player, weapons, world_objects  # noqa: F401

    return REGISTRY
