"""Canonical database import surface.

All façade-listed modules are implemented under ``src/obsidiandroid/database/``.
The repository-root ``database/`` directory contains SQL assets only; Python
callers use this package.

Prefer::

    import obsidiandroid.database as obsdb
    obsdb.settings.load_connection_settings()

or::

    from obsidiandroid.database import db_engine

Timeline / AV-stats / label-keyword helpers are on the same façade list as the
core DB modules (see :mod:`obsidiandroid.database.facade_manifest`).
"""

from __future__ import annotations

from importlib import import_module

from .facade_manifest import FACADE_EXPORT_NAMES

__all__ = list(FACADE_EXPORT_NAMES)


def __getattr__(name: str):
    if name in __all__:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
