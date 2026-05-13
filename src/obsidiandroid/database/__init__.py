"""Canonical database import surface (Passes 38–43).

All façade-listed modules are implemented under ``src/obsidiandroid/database/``.
Repo-root ``database/<name>.py`` files are **thin identity shims** (except
``split_db_health``, which also wires ``python -m database.split_db_health``).

Each shim registers the same :class:`types.ModuleType` as
``obsidiandroid.database.<name>`` so ``import database.<name>`` and
``import obsidiandroid.database.<name>`` resolve to identical objects.

Prefer::

    import obsidiandroid.database as obsdb
    obsdb.settings.load_connection_settings()

or::

    from obsidiandroid.database import db_engine

Optional ``database.*`` helpers (timelines, AV disagreement, label keywords, …)
also live under ``src/obsidiandroid/database/`` with repo-root identity shims;
they are not re-exported from this package's ``__all__`` unless the façade widens.
The ordered façade export names (and optional legacy-only shim names for CI) are
defined in :mod:`obsidiandroid.database.facade_manifest`.
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
