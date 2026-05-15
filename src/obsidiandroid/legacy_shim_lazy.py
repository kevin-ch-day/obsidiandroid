# Filename: src/obsidiandroid/legacy_shim_lazy.py
"""Shared helpers for repo-root legacy compatibility shims and lazy package facades."""

from __future__ import annotations

import importlib
import os
import warnings
from types import ModuleType
from typing import Any


def _legacy_shim_warnings_enabled() -> bool:
    """Return whether legacy-shim deprecation warnings should be emitted."""
    raw = os.getenv("OBSIDIANDROID_WARN_LEGACY_SHIMS", "")
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def _warn_legacy_shim(legacy_qual: str, canonical_qual: str) -> None:
    """Warn once when an opt-in legacy compatibility shim is imported."""
    if not _legacy_shim_warnings_enabled():
        return
    warnings.warn(
        f"{legacy_qual} is a legacy compatibility shim; import {canonical_qual} instead. "
        "This shim is in a ready-to-retire compatibility batch.",
        FutureWarning,
        stacklevel=3,
    )


def import_legacy_shim(
    canonical_qual: str,
    legacy_qual: str,
    *,
    warn: bool = False,
) -> ModuleType:
    """Import the canonical module for one legacy shim and optionally warn."""
    if warn:
        _warn_legacy_shim(legacy_qual, canonical_qual)
    return importlib.import_module(canonical_qual)


def lazy_legacy_submodule(
    name: str,
    legacy_pkg_qual: str,
    allowed: frozenset[str],
    *,
    canonical_pkg_qual: str | None = None,
    warn: bool = False,
) -> Any:
    """Resolve ``legacy_pkg_qual.<name>`` via :mod:`importlib` (thin leaf shims)."""
    if name not in allowed:
        raise AttributeError(f"module {legacy_pkg_qual!r} has no attribute {name!r}")
    canonical_qual = f"{canonical_pkg_qual}.{name}" if canonical_pkg_qual else f"{legacy_pkg_qual}.{name}"
    return import_legacy_shim(canonical_qual, f"{legacy_pkg_qual}.{name}", warn=warn)


__all__ = ("import_legacy_shim", "lazy_legacy_submodule")
