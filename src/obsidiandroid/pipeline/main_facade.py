"""Compatibility wrapper for the repo-root ``main`` monkeypatch bridge.

Canonical code uses :mod:`obsidiandroid.cli.main_override_bridge`. This small
facade preserves the established runner call site while repo-root ``main``
remains a temporary test/operator entry surface.
"""

from __future__ import annotations

from typing import TypeVar

from obsidiandroid.cli.main_override_bridge import resolve_main_override

__all__ = ["from_main_or"]

_T = TypeVar("_T")


def from_main_or(attr: str, default: _T) -> _T:
    """Compatibility alias for :func:`obsidiandroid.cli.main_override_bridge.resolve_main_override`."""
    return resolve_main_override(attr, default)
