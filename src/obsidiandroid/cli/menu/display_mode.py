"""Shared operator display-mode resolution for menu surfaces."""

from __future__ import annotations

import os
from typing import Literal

from config import app_config

DisplayMode = Literal["compact", "detailed", "debug"]

_VALID_DISPLAY_MODES = {"compact", "detailed", "debug"}


def resolve_display_mode(explicit: str | None = None) -> DisplayMode:
    """Resolve the current operator display mode."""
    for raw in (explicit, os.getenv("OBSIDIANDROID_DISPLAY_MODE")):
        token = str(raw or "").strip().lower()
        if token in _VALID_DISPLAY_MODES:
            return token  # type: ignore[return-value]
    if bool(getattr(app_config, "DEBUG_MODE", False)):
        return "debug"
    return "compact"


def is_compact_mode(mode: str | None = None) -> bool:
    """Return whether the effective mode is compact."""
    return resolve_display_mode(mode) == "compact"


def is_detailed_mode(mode: str | None = None) -> bool:
    """Return whether the effective mode is detailed."""
    return resolve_display_mode(mode) == "detailed"


def is_debug_mode(mode: str | None = None) -> bool:
    """Return whether the effective mode is debug."""
    return resolve_display_mode(mode) == "debug"


def mode_max_rows(
    *,
    compact: int,
    detailed: int,
    debug: int | None = None,
    mode: str | None = None,
) -> int:
    """Return a mode-aware row cap for compact/detail/debug menu tables."""
    resolved = resolve_display_mode(mode)
    if resolved == "compact":
        return compact
    if resolved == "detailed":
        return detailed
    return debug if debug is not None else detailed


__all__ = [
    "DisplayMode",
    "is_compact_mode",
    "is_debug_mode",
    "is_detailed_mode",
    "mode_max_rows",
    "resolve_display_mode",
]
