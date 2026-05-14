# Filename: src/obsidiandroid/legacy_shim_lazy.py
"""Shared :func:`lazy_legacy_submodule` helper for repo-root lazy package facades."""

from __future__ import annotations

import importlib
from typing import Any


def lazy_legacy_submodule(name: str, legacy_pkg_qual: str, allowed: frozenset[str]) -> Any:
    """Resolve ``legacy_pkg_qual.<name>`` via :mod:`importlib` (thin leaf shims)."""
    if name not in allowed:
        raise AttributeError(f"module {legacy_pkg_qual!r} has no attribute {name!r}")
    return importlib.import_module(f"{legacy_pkg_qual}.{name}")


__all__ = ("lazy_legacy_submodule",)
