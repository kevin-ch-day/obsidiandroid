"""Shared glob and filename lists for pruning legacy clutter under ``output/``.

Used by ``scripts/fresh_pipeline_reset`` and ``scripts/cleanup_output_artifacts``
so bundle smoke patterns and mirror filenames stay in one place.
"""

from __future__ import annotations

# Glob patterns at the pipeline output root (paper bundles / smoke zips).
PAPER_BUNDLE_ARCHIVE_GLOBS: tuple[str, ...] = (
    "paper_bundle_20*",
    "paper_bundle_20*.zip",
)
PAPER_BUNDLE_SMOKE_GLOBS: tuple[str, ...] = (
    "paper_bundle_smoke*",
    "paper_bundle_zip_smoke*",
    "paper_bundle_unit_smoke*",
    "paper_bundle_*smoke*.zip",
)

# Exact legacy filenames at output root (old mirrors and one-off reports).
LEGACY_OUTPUT_ROOT_FILES: tuple[str, ...] = (
    "paper_bundle_latest",
    "permission_trends",
    "permission_trends.zip",
    "engine_scoring_summary_log.txt",
    "family_distribution_report.txt",
    "obsidiandroid_outputs_copy.xlsx",
    "obsidiandroid_outputs_snapshot.xlsx",
    "obsidiandroid_outputs__unknown.xlsx",
)

WORKBOOK_CORRUPT_GLOB = "obsidiandroid_outputs.corrupt_*.xlsx"

# Under ``output/diagnostics/`` — timestamped duplicates (``.latest.*`` kept elsewhere).
DIAGNOSTICS_TIMESTAMP_GLOBS: tuple[str, ...] = (
    "ablation_per_family_20*.csv",
    "ablation_summary_20*.csv",
    "feature_contract_20*.json",
    "leakage_assessment_20*.txt",
    "classifier_summary_eval_20*.txt",
)

# Under ``output/runs/<run_id>/`` — legacy convenience mirrors or historical bad layout.
# These are safe to prune from older runs because canonical artifacts already live at the
# run root and global operator mirrors live under ``output/diagnostics`` / ``output/promoted``.
LEGACY_RUN_SUBDIR_NAMES: tuple[str, ...] = (
    "latest",
    "promoted",
    "runs",
)

# Under ``output/runs/<run_id>/diagnostics/`` — redundant mirrors / bulky historical exports.
RUN_DIAGNOSTICS_LOCAL_LATEST_GLOB = "*.latest.*"
RUN_DIAGNOSTICS_SPLIT_FREEZE_GLOB = "split_freeze_ablation__*.csv"

# Whole directories to remove on a full output wipe (pre–repo-root ``logs/`` layout).
LEGACY_OUTPUT_LOG_DIR_SEGMENTS: tuple[tuple[str, ...], ...] = (
    ("diagnostics", "runtime_logs"),
    ("diagnostics", "logs"),
    ("logs",),
)

__all__ = [
    "DIAGNOSTICS_TIMESTAMP_GLOBS",
    "LEGACY_OUTPUT_LOG_DIR_SEGMENTS",
    "LEGACY_OUTPUT_ROOT_FILES",
    "LEGACY_RUN_SUBDIR_NAMES",
    "PAPER_BUNDLE_ARCHIVE_GLOBS",
    "PAPER_BUNDLE_SMOKE_GLOBS",
    "RUN_DIAGNOSTICS_LOCAL_LATEST_GLOB",
    "RUN_DIAGNOSTICS_SPLIT_FREEZE_GLOB",
    "WORKBOOK_CORRUPT_GLOB",
]
