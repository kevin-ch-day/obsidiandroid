# Filename: src/obsidiandroid/database/facade_manifest.py
"""Single source for ``obsidiandroid.database`` façade names and legacy shim parity.

``obsidiandroid.database`` :mod:`__init__` uses :data:`FACADE_EXPORT_NAMES` for eager
submodule registration order. Import-surface checks and tests use the derived pair
tuples so CI stays aligned with the package bootstrap order.

Bootstrap note: ``db_sample_malicious_scoring`` must appear before
``db_av_engine_detection_totals`` (the totals module imports the scoring module).

Migration note: the repo-root ``database/`` tree is now split into:

- keep surfaces:
  - ``database/__init__.py``
  - ``database/split_db_health.py``
- retired leaf shims:
  - plain identity shims intentionally removed after caller/guardrail review
- candidate leaf shims:
  - plain identity shims with canonical replacements and zero callers outside
    parity/tooling/docs
- deferred leaf shims:
  - currently none; add here only when a repo-root leaf remains ambiguous
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

# Repo-root ``database`` compatibility files that must remain for now.
REPO_ROOT_DATABASE_KEEP_FILES: tuple[str, ...] = (
    "__init__.py",
    "split_db_health.py",
)

# Repo-root DB leaves already retired from the compatibility tree. Canonical
# imports remain available from ``obsidiandroid.database``.
REPO_ROOT_DATABASE_RETIRED_MODULES: tuple[str, ...] = (
    "cohort_sql_fragments",
    "db_av_engine_detection_totals",
    "db_av_disagreement_analysis",
    "db_av_engine_verdicts",
    "db_av_engine_stats",
    "db_config",
    "db_engine",
    "db_errors",
    "db_extract_av_label_keywords",
    "db_fetch_av_engine_raw_results",
    "db_permission_analysis_queries",
    "db_sample_malicious_scoring",
    "db_sample_metadata_contracts",
    "db_sample_metadata_fetchers",
    "db_sample_metadata_queries",
    "db_sample_timelines_queries",
    "db_utils",
    "schema_map",
    "settings",
)
REPO_ROOT_DATABASE_RETIRED_FILES: tuple[str, ...] = tuple(
    f"{name}.py" for name in REPO_ROOT_DATABASE_RETIRED_MODULES
)

# Remaining repo-root ``database.<name>`` shims still expected to exist.
ACTIVE_REPO_ROOT_DATABASE_SHIM_EXPORT_NAMES: tuple[str, ...] = tuple(
    name for name in FACADE_EXPORT_NAMES if name not in REPO_ROOT_DATABASE_RETIRED_MODULES
)

# Repo-root leaf shims with canonical replacements, zero callers outside
# parity/tooling/docs, and no CLI/module-entrypoint behavior. They are the next
# deletion candidates once guardrails/docs are intentionally narrowed.
REPO_ROOT_DATABASE_CANDIDATE_DELETE_MODULES: tuple[str, ...] = tuple(
    name for name in ACTIVE_REPO_ROOT_DATABASE_SHIM_EXPORT_NAMES if name != "split_db_health"
)
REPO_ROOT_DATABASE_CANDIDATE_DELETE_FILES: tuple[str, ...] = tuple(
    f"{name}.py" for name in REPO_ROOT_DATABASE_CANDIDATE_DELETE_MODULES
)

# Placeholder for future ambiguous repo-root DB leaves. Keep explicit so the
# closure plan stays honest when a leaf cannot move directly from candidate to
# deleted.
REPO_ROOT_DATABASE_DEFER_MODULES: tuple[str, ...] = ()
REPO_ROOT_DATABASE_DEFER_FILES: tuple[str, ...] = ()

FACADE_MODULE_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (name, f"obsidiandroid.database.{name}") for name in FACADE_EXPORT_NAMES
)

LEGACY_SHIM_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (name, f"database.{name}") for name in ACTIVE_REPO_ROOT_DATABASE_SHIM_EXPORT_NAMES
)

__all__ = (
    "ACTIVE_REPO_ROOT_DATABASE_SHIM_EXPORT_NAMES",
    "FACADE_EXPORT_NAMES",
    "FACADE_MODULE_PAIRS",
    "LEGACY_SHIM_PAIRS",
    "REPO_ROOT_DATABASE_CANDIDATE_DELETE_FILES",
    "REPO_ROOT_DATABASE_CANDIDATE_DELETE_MODULES",
    "REPO_ROOT_DATABASE_DEFER_FILES",
    "REPO_ROOT_DATABASE_DEFER_MODULES",
    "REPO_ROOT_DATABASE_KEEP_FILES",
    "REPO_ROOT_DATABASE_RETIRED_FILES",
    "REPO_ROOT_DATABASE_RETIRED_MODULES",
)
