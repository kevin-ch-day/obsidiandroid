"""Compatibility wrapper for the repo-root ``main`` monkeypatch bridge.

Canonical code now uses :mod:`obsidiandroid.cli.main_override_bridge`. This module
is retained so older imports, tests, and ``analysis.pipeline.main_facade`` shims
continue to resolve the same behavior while the migration completes.
"""

from __future__ import annotations

from typing import TypeVar

from obsidiandroid.cli.main_override_bridge import resolve_main_override

__all__ = ["from_main_or"]

_T = TypeVar("_T")


def from_main_or(attr: str, default: _T) -> _T:
    """Compatibility alias for :func:`obsidiandroid.cli.main_override_bridge.resolve_main_override`."""
    return resolve_main_override(attr, default)
