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

# Repo-root compatibility trees whose non-``__init__`` leaves must remain thin
# ModuleType identity shims until retirement.
LEGACY_LEAF_SHIM_ROOTS = (
    "analysis",
)

# Repo-root shim namespace that remains intentionally compatibility-only while
# implementations live under ``src/obsidiandroid/database``.
LEGACY_DATABASE_SHIM_ROOT = "database"

# Allowlisted files that intentionally exercise legacy compatibility behavior.
CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST = (
    Path("scripts/dev/check_import_surface.py"),
)

NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST = (
    Path("tests/test_legacy_shim_parity.py"),
)

ANALYSIS_PIPELINE_PATCH_SENSITIVE_SHIMS = (
    "analysis/pipeline/main_facade.py",
    "analysis/pipeline/runner.py",
)

ANALYSIS_PIPELINE_PACKAGE_SPECIAL_CASES = (
    "analysis/pipeline/__init__.py",
    "analysis/pipeline/governance/__init__.py",
    "analysis/pipeline/permission_trends/__init__.py",
)

ANALYSIS_PIPELINE_PLAIN_IDENTITY_SHIMS = (
    "analysis/pipeline/artifacts/__init__.py",
    "analysis/pipeline/artifacts/paths.py",
    "analysis/pipeline/artifacts/registry.py",
    "analysis/pipeline/governance/exceptions.py",
    "analysis/pipeline/governance/integrity.py",
    "analysis/pipeline/governance/policy.py",
    "analysis/pipeline/governance/readiness.py",
    "analysis/pipeline/manifest/__init__.py",
    "analysis/pipeline/manifest/builder.py",
    "analysis/pipeline/manifest/hashing.py",
    "analysis/pipeline/manifest/paper_compliance_checks.py",
    "analysis/pipeline/manifest/paper_figure_renderers.py",
    "analysis/pipeline/manifest/runtime_support.py",
    "analysis/pipeline/manifest/schema.py",
    "analysis/pipeline/manifest/writer.py",
    "analysis/pipeline/permission_trends/bundle_manifest.py",
    "analysis/pipeline/permission_trends/constants.py",
    "analysis/pipeline/permission_trends/publish_paths.py",
    "analysis/pipeline/permission_trends/reporting_support.py",
    "analysis/pipeline/permission_trends/sample_permission_data.py",
    "analysis/pipeline/permission_trends/stats_core.py",
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


LEGACY_TREE_RETIREMENT_MATRIX = (
    LegacyTreeRetirementEntry(
        root="analysis",
        file_count=27,
        implementation_status="canonical relocation complete; remaining root tree is pipeline-focused shim surface",
        compatibility_role="legacy pipeline import identity and monkeypatch-sensitive runner/test seams",
        blockers=(
            "pipeline monkeypatch surfaces still target analysis.pipeline in some parity flows",
            "package-level shim identity is still exercised by explicit parity tests",
            "retirement needs staged caller/test deprecation, not drive-by deletion",
        ),
        next_step="narrow parity-test coverage and define per-subtree deletion criteria",
    ),
    LegacyTreeRetirementEntry(
        root="database",
        file_count=24,
        implementation_status="canonical relocation complete under src/obsidiandroid/database",
        compatibility_role="repo-root import compatibility and python -m database.split_db_health entrypoint",
        blockers=(
            "repo-root database.* remains an intentional compatibility namespace",
            "facade/implementation distinction must stay clear to avoid circular import regressions",
            "split_db_health still needs the repo-root execution surface",
        ),
        next_step="separate module-retirement candidates from entrypoint-compatibility shims",
    ),
)

LEGACY_SUBTREE_RETIREMENT_BUCKETS = (
    LegacySubtreeRetirementBucket(
        tree="analysis/pipeline",
        canonical_target="obsidiandroid.pipeline",
        bucket="monkeypatch-sensitive shim tree",
        file_count=26,
        readiness="deprecate later",
        rationale="runner/main_facade remain stable monkeypatch and compatibility surfaces; ordinary top-level leaves now resolve through package-level alias registration",
        next_step="keep shrinking toward runner/main_facade plus nested package shims, then define final retirement order for the remaining nested surfaces",
        import_prefixes=("analysis.pipeline",),
    ),
    LegacySubtreeRetirementBucket(
        tree="database/__init__.py",
        canonical_target="obsidiandroid.database",
        bucket="repo-root compatibility package",
        file_count=1,
        readiness="keep for now",
        rationale="defines the repo-root compatibility namespace for database.* imports",
        next_step="keep until broader database shim retirement plan is approved",
        import_prefixes=("database",),
    ),
    LegacySubtreeRetirementBucket(
        tree="database/split_db_health.py",
        canonical_target="obsidiandroid.database.split_db_health",
        bucket="entrypoint compatibility shim",
        file_count=1,
        readiness="keep for now",
        rationale="supports python -m database.split_db_health in addition to import compatibility",
        next_step="preserve until CLI/ops entrypoint migration is explicitly approved",
        import_prefixes=("database.split_db_health",),
    ),
    LegacySubtreeRetirementBucket(
        tree="database/*.py (other leaf shims)",
        canonical_target="obsidiandroid.database",
        bucket="leaf identity shims",
        file_count=19,
        readiness="deprecate later",
        rationale="canonical implementation is complete but repo-root database namespace still intentionally exists",
        next_step="separate pure import-compat leaves from any remaining ops-facing surfaces",
        import_prefixes=("database",),
    ),
)

EARLY_DEPRECATION_READY_TREES = tuple(
    entry.tree for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS if entry.readiness == "ready to deprecate now"
)

__all__ = (
    "CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST",
    "CANONICAL_FILENAME_HEADER_BAD_ROOTS",
    "CANONICAL_RELOCATION_COMPLETE_DOMAINS",
    "ANALYSIS_PIPELINE_PACKAGE_SPECIAL_CASES",
    "ANALYSIS_PIPELINE_PATCH_SENSITIVE_SHIMS",
    "ANALYSIS_PIPELINE_PLAIN_IDENTITY_SHIMS",
    "EARLY_DEPRECATION_READY_TREES",
    "LEGACY_SUBTREE_RETIREMENT_BUCKETS",
    "LEGACY_TREE_RETIREMENT_MATRIX",
    "LegacyTreeRetirementEntry",
    "LegacySubtreeRetirementBucket",
    "LEGACY_COMPATIBILITY_IMPORT_ROOTS",
    "LEGACY_DATABASE_SHIM_ROOT",
    "LEGACY_LEAF_SHIM_ROOTS",
    "NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST",
)
