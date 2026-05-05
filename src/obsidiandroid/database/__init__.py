"""Canonical database import surface (Passes 38–43).

Implementation remains under repo-root ``database/*.py``. This package re-exports
the **same** :class:`types.ModuleType` objects as ``database.<name>`` and
registers matching ``sys.modules`` keys so ``import obsidiandroid.database.<name>``
preserves identity (critical for Primary vs Permission Intel semantics).

**Tier D (Pass 43):** narrow AV / scoring query modules used by pipeline and
evaluation are included on the same thin re-export model as Tiers A–C.

Prefer::

    import obsidiandroid.database as obsdb
    obsdb.settings.load_connection_settings()

or::

    from obsidiandroid.database import db_engine

Legacy ``from database …`` imports remain supported until an explicit sunset.
"""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = (
    "cohort_sql_fragments",
    "db_config",
    "db_engine",
    "db_errors",
    "db_av_engine_detection_totals",
    "db_av_engine_verdicts",
    "db_fetch_av_engine_raw_results",
    "db_permission_analysis_queries",
    "db_sample_metadata_contracts",
    "db_sample_metadata_fetchers",
    "db_sample_metadata_queries",
    "db_sample_malicious_scoring",
    "db_utils",
    "schema_map",
    "settings",
    "split_db_health",
)

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(f"database.{_name}")
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.database.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _name, _canon
