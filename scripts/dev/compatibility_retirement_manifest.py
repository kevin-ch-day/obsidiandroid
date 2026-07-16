"""Single source of truth for canonical-relocation completion and legacy-compat surfaces.

This module is intentionally data-only. It exists to keep the final migration
phase honest and maintainable:

- canonical relocation complete domains live in one place
- legacy compatibility roots / shim trees are declared once
- test allowlists for shim-parity coverage stay explicit

Consumers include import-surface guardrails, docs, and future compatibility
retirement tooling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Core domains whose implementation is now treated as canonical under
# ``src/obsidiandroid``. Remaining work in these areas is shim retirement,
# boundary cleanup, or docs/tests rather than physical code relocation.
CANONICAL_RELOCATION_COMPLETE_DOMAINS = (
    "pipeline",
    "common",
    "governance",
    "observability",
    "diagnostics",
    "database",
    "modeling",
    "evaluation",
    "reporting",
    "vendors",
    "features",
    "feature_engineering",
    "labeling",
    "classification_builder",
    "inference",
    "engine_weights",
    "risk_band",
    "matrix",
    "orchestration",
)

# Legacy roots that canonical code must not import directly.
LEGACY_COMPATIBILITY_IMPORT_ROOTS = (
    "analysis",
    "ml_classification",
)

# Canonical application and script code must also avoid the repository-root
# launcher.  ``main.py`` remains a temporary external/test compatibility
# surface, but active application paths use ``obsidiandroid.cli.pipeline_entry``.
CANONICAL_CODE_COMPATIBILITY_IMPORT_ROOTS = (
    *LEGACY_COMPATIBILITY_IMPORT_ROOTS,
    "main",
)

# There are no remaining repo-root compatibility leaf trees.
LEGACY_LEAF_SHIM_ROOTS: tuple[str, ...] = ()

# The repository-root ``database/`` directory remains for SQL assets, not Python
# imports. Keep it in the filename-header denylist so canonical source headers
# cannot drift back to the former root package path.
LEGACY_DATABASE_SHIM_ROOT = "database"

# Allowlisted files that intentionally exercise legacy compatibility behavior.
CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST = (
    Path("scripts/dev/check_import_surface.py"),
)

NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST: tuple[Path, ...] = ()

# These roots are fully retired.  A static guard rejects the whole tree rather
# than maintaining a brittle list of former individual shim files.
RETIRED_COMPATIBILITY_ROOTS = (
    "analysis",
    "ml_classification",
)

# The SQL asset directory stays at the repository root, so guard the two former
# Python compatibility files individually instead of rejecting the whole tree.
RETIRED_ROOT_COMPATIBILITY_FILES = (
    Path("database/__init__.py"),
    Path("database/split_db_health.py"),
)

CANONICAL_FILENAME_HEADER_BAD_ROOTS = (
    *LEGACY_COMPATIBILITY_IMPORT_ROOTS,
    LEGACY_DATABASE_SHIM_ROOT,
)


@dataclass(frozen=True)
class LegacyTreeRetirementEntry:
    """Status snapshot for one legacy compatibility tree."""

    root: str
    file_count: int
    implementation_status: str
    compatibility_role: str
    blockers: tuple[str, ...]
    next_step: str


@dataclass(frozen=True)
class LegacySubtreeRetirementBucket:
    """Retirement status for one legacy subtree or special compatibility surface."""

    tree: str
    canonical_target: str
    bucket: str
    file_count: int
    readiness: str
    rationale: str
    next_step: str
    import_prefixes: tuple[str, ...] = ()


LEGACY_TREE_RETIREMENT_MATRIX: tuple[LegacyTreeRetirementEntry, ...] = ()

LEGACY_SUBTREE_RETIREMENT_BUCKETS: tuple[LegacySubtreeRetirementBucket, ...] = ()

EARLY_DEPRECATION_READY_TREES = tuple(
    entry.tree for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS if entry.readiness == "ready to deprecate now"
)

__all__ = (
    "CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST",
    "CANONICAL_CODE_COMPATIBILITY_IMPORT_ROOTS",
    "CANONICAL_FILENAME_HEADER_BAD_ROOTS",
    "CANONICAL_RELOCATION_COMPLETE_DOMAINS",
    "EARLY_DEPRECATION_READY_TREES",
    "LEGACY_SUBTREE_RETIREMENT_BUCKETS",
    "LEGACY_TREE_RETIREMENT_MATRIX",
    "LegacyTreeRetirementEntry",
    "LegacySubtreeRetirementBucket",
    "LEGACY_COMPATIBILITY_IMPORT_ROOTS",
    "LEGACY_DATABASE_SHIM_ROOT",
    "LEGACY_LEAF_SHIM_ROOTS",
    "NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST",
    "RETIRED_COMPATIBILITY_ROOTS",
    "RETIRED_ROOT_COMPATIBILITY_FILES",
)
