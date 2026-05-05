"""Classify generated artifacts for evidence vs diagnostics vs debug (policy table)."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

# Buckets: evidence_required | diagnostics_required | diagnostics_optional |
# debug_only | operator_state | promoted_latest | deprecated_or_duplicate

_RULES: list[dict[str, Any]] = []


def _rule(
    pattern: str,
    *,
    bucket: str,
    producer: str,
    run_scoped: bool,
    paper_required: bool,
    safe_delete_after_run: bool,
    duplicate_latest: bool,
    description: str,
) -> dict[str, Any]:
    return {
        "pattern": pattern,
        "artifact_bucket": bucket,
        "producer_module": producer,
        "run_scoped": run_scoped,
        "required_for_paper_mode": paper_required,
        "safe_to_delete_after_run": safe_delete_after_run,
        "duplicate_latest_copy": duplicate_latest,
        "human_description": description,
    }


def _init_rules() -> None:
    global _RULES  # pylint: disable=global-statement
    if _RULES:
        return
    # Canonical run contracts
    _RULES.extend(
        [
            _rule(
                "run_manifest.json",
                bucket="evidence_required",
                producer="analysis.pipeline.stage_manifest",
                run_scoped=True,
                paper_required=True,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Canonical run manifest (schema-versioned).",
            ),
            _rule(
                "**/run_manifest.json",
                bucket="evidence_required",
                producer="analysis.pipeline.stage_manifest",
                run_scoped=True,
                paper_required=True,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Canonical run manifest (schema-versioned).",
            ),
            _rule(
                "**/run_summary.json",
                bucket="evidence_required",
                producer="analysis.pipeline.stage_manifest",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Operator-friendly run summary JSON at run root.",
            ),
            _rule(
                "**/paper2_pack/**",
                bucket="evidence_required",
                producer="analysis.pipeline.stage_manifest",
                run_scoped=True,
                paper_required=True,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Strict paper evidence pack (evidence mode).",
            ),
            _rule(
                "**/cohort_filter_contract_*.json",
                bucket="evidence_required",
                producer="analysis.pipeline.sample_exports",
                run_scoped=True,
                paper_required=True,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Frozen cohort filter contract JSON.",
            ),
            _rule(
                "**/experiment_registry_*.json",
                bucket="diagnostics_required",
                producer="analysis.pipeline.stage_manifest",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Experiment registry for reproducibility tracking.",
            ),
            _rule(
                "**/split_freeze_audit_*.csv",
                bucket="evidence_required",
                producer="ml_classification.training.model_trainer_factory",
                run_scoped=True,
                paper_required=True,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Train/test split freeze audit rows.",
            ),
            _rule(
                "**/preflight_report.json",
                bucket="diagnostics_required",
                producer="main",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=False,
                description="Evidence preflight status snapshot.",
            ),
            _rule(
                "**/paper_mode_compliance_report_*.json",
                bucket="diagnostics_required",
                producer="analysis.pipeline.stage_manifest",
                run_scoped=True,
                paper_required=True,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Paper-mode compliance gate results.",
            ),
            _rule(
                "**/ablation_summary*.csv",
                bucket="diagnostics_required",
                producer="analysis.pipeline.stage_ablation",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Ablation comparison summary table.",
            ),
            _rule(
                "**/ablation_cohort_gap_summary.*",
                bucket="diagnostics_required",
                producer="analysis.diagnostics.ablation_cohort_diagnostics",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Ablation cohort alignment audit.",
            ),
            _rule(
                "**/ablation_feature_schema_audit.csv",
                bucket="diagnostics_required",
                producer="analysis.pipeline.stage_ablation",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Ablation fit vs predict feature column audit.",
            ),
            _rule(
                "**/feature_build_coverage*.json",
                bucket="diagnostics_required",
                producer="analysis.diagnostics.feature_build_coverage_export",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Feature build coverage / cohort vs matrix lineage.",
            ),
            _rule(
                "**/vendor_gate_debug*.csv",
                bucket="diagnostics_required",
                producer="ml_classification.vectorization.feature_vector_builder",
                run_scoped=True,
                paper_required=True,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Vendor gate debug rows for feature inclusion.",
            ),
            _rule(
                "**/vendor_parser_stress_test*.csv",
                bucket="debug_only",
                producer="analysis.pipeline.vendor_metadata_pipeline",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=False,
                description="Parser threshold sweep stress grid (debug / deep audit).",
            ),
            _rule(
                "**/aligned_features*.csv.gz",
                bucket="operator_state",
                producer="analysis.orchestration.runtime_reporting",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=False,
                description="Cached aligned feature matrix export for retraining.",
            ),
            _rule(
                "**/*.latest.*",
                bucket="deprecated_or_duplicate",
                producer="various",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=True,
                description="Legacy `.latest` mirror inside a run directory (prefer global mirrors).",
            ),
            _rule(
                "**/diagnostics/run_manifest.latest.json",
                bucket="operator_state",
                producer="obsidiandroid.governance.run_manifest",
                run_scoped=False,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=True,
                description="Global pointer copy of latest manifest (operator convenience).",
            ),
            _rule(
                "**/diagnostics/latest_run_pointer.json",
                bucket="operator_state",
                producer="analysis.pipeline.stage_manifest",
                run_scoped=False,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=False,
                description="Points to latest run root / run id.",
            ),
            _rule(
                "**/promoted/latest_run*.json",
                bucket="promoted_latest",
                producer="analysis.pipeline.stage_manifest",
                run_scoped=False,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=True,
                description="Promoted latest-run pointer for menus/tools.",
            ),
            _rule(
                "**/latest/**",
                bucket="promoted_latest",
                producer="obsidiandroid.common.output_paths",
                run_scoped=False,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=True,
                description="Global latest mirrors (confusion matrix copy, etc.).",
            ),
            _rule(
                "**/logs/**",
                bucket="diagnostics_optional",
                producer="obsidiandroid.observability.logging.runtime",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=False,
                description="Legacy per-run log folders under diagnostics (canonical logs: repo logs/).",
            ),
            _rule(
                "**/models/**",
                bucket="diagnostics_optional",
                producer="ml_classification.training",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=False,
                description="Serialized model pickles when export enabled.",
            ),
            _rule(
                "**/conf_matrices/**",
                bucket="diagnostics_optional",
                producer="ml_classification.training",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Exported confusion matrix figures.",
            ),
            _rule(
                "**/artifact_inventory.*",
                bucket="diagnostics_required",
                producer="analysis.diagnostics.output_inventory",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Per-run artifact classification inventory.",
            ),
            _rule(
                "**/run_evidence_index.md",
                bucket="evidence_required",
                producer="analysis.diagnostics.output_inventory",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=False,
                duplicate_latest=False,
                description="Human-first evidence index for the run.",
            ),
            _rule(
                "**/virtual_layout.json",
                bucket="diagnostics_optional",
                producer="analysis.diagnostics.output_inventory",
                run_scoped=True,
                paper_required=False,
                safe_delete_after_run=True,
                duplicate_latest=False,
                description="Logical grouping of paths without moving files on disk.",
            ),
        ]
    )


def classify_relative_path(rel_posix: str) -> dict[str, Any]:
    """Return classification metadata for a path relative to the run or repo output root.

    First matching glob wins; unknown paths default to diagnostics_optional.
    """
    _init_rules()
    rel = rel_posix.replace("\\", "/").lstrip("/")
    for rule in _RULES:
        if fnmatch.fnmatch(rel, rule["pattern"]):
            return dict(rule)
    return _rule(
        "**",
        bucket="diagnostics_optional",
        producer="unknown",
        run_scoped=True,
        paper_required=False,
        safe_delete_after_run=False,
        duplicate_latest=False,
        description="Unclassified pipeline artifact (default bucket).",
    )


def classify_file(path: Path, *, base: Path) -> dict[str, Any]:
    """Classify ``path`` relative to ``base`` (typically run root or output root)."""
    try:
        rel = path.resolve().relative_to(base.resolve())
    except ValueError:
        rel = Path(path.name)
    meta = classify_relative_path(rel.as_posix())
    meta["relative_path"] = rel.as_posix()
    return meta


__all__ = ["classify_file", "classify_relative_path"]
