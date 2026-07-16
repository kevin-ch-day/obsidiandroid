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

import importlib
import sys

from .facade_manifest import FACADE_EXPORT_NAMES as _FACADE_EXPORT_NAMES

for _name in _FACADE_EXPORT_NAMES:
    _canon = importlib.import_module(f"obsidiandroid.database.{_name}")
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.database.{_name}", _canon)

__all__ = list(_FACADE_EXPORT_NAMES)

del _FACADE_EXPORT_NAMES, _name, _canon
