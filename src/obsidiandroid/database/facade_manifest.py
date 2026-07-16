# Filename: src/obsidiandroid/database/facade_manifest.py
"""Single source for canonical ``obsidiandroid.database`` façade names.

``obsidiandroid.database`` :mod:`__init__` uses :data:`FACADE_EXPORT_NAMES` for eager
submodule registration order. Import-surface checks and tests use the derived pair
tuples so CI stays aligned with the package bootstrap order.

Bootstrap note: ``db_sample_malicious_scoring`` must appear before
``db_av_engine_detection_totals`` (the totals module imports the scoring module).

The repository-root ``database/`` directory is reserved for versioned SQL
assets. Python callers use this canonical package exclusively.
"""

from __future__ import annotations

FACADE_EXPORT_NAMES: tuple[str, ...] = (
    "cohort_sql_fragments",
    "db_config",
    "db_errors",
    "schema_map",
    "settings",
    "db_engine",
    "db_sample_malicious_scoring",
    "db_sample_metadata_contracts",
    "db_sample_metadata_fetchers",
    "db_sample_metadata_queries",
    "db_av_engine_detection_totals",
    "db_av_engine_verdicts",
    "db_fetch_av_engine_raw_results",
    "db_permission_analysis_queries",
    "db_utils",
    "split_db_health",
    # Operator / diagnostics helpers (same identity shims as ``database.<name>``).
    "db_sample_timelines_queries",
    "db_av_disagreement_analysis",
    "db_av_engine_stats",
    "db_extract_av_label_keywords",
)

FACADE_MODULE_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (name, f"obsidiandroid.database.{name}") for name in FACADE_EXPORT_NAMES
)

__all__ = (
    "FACADE_EXPORT_NAMES",
    "FACADE_MODULE_PAIRS",
)
