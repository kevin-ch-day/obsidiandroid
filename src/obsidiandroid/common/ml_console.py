"""Console verbosity helpers for ML pipeline terminal output."""

from __future__ import annotations

from config import app_config

_VALID_MODES = {"minimal", "research", "debug"}


def get_mode() -> str:
    """Return normalized ML console mode."""
    raw = str(getattr(app_config, "ML_CONSOLE_MODE", "research")).strip().lower()
    if raw not in _VALID_MODES:
        return "research"
    return raw


def is_minimal() -> bool:
    """Return True when minimal terminal output is requested."""
    return get_mode() == "minimal"


def is_research() -> bool:
    """Return True when research-mode terminal output is requested."""
    return get_mode() == "research"


def is_debug() -> bool:
    """Return True when debug-level terminal output is requested."""
    return get_mode() == "debug"


def is_compact() -> bool:
    """Return True when terminal output should prefer compact operator summaries."""
    if is_debug():
        return False
    return bool(getattr(app_config, "ML_TERMINAL_COMPACT", True))


def show_debug_tables(default: bool = False) -> bool:
    """Gate noisy tabular terminal output."""
    if is_debug():
        return True
    return bool(default)
