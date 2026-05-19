"""Paper-mode compliance gate rows (split audit, duplicates, taxonomy, etc.)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import obsidiandroid.governance.artifacts as artifacts


def build_paper_compliance_checks(
    *,
    paper_mode: bool,
    split_hash: str,
    split_audit_path: str,
    duplicate_report_path: str,
    duplicate_count: int,
    invalid_sha_count: int,
    vendor_gate_debug_path: str,
    run_paths_manifest_path: str,
    experiment_registry_path: str,
    taxonomy_summary_path: str,
    taxonomy_type_rows_evaluated: int,
    taxonomy_mismatch_count: int,
    taxonomy_mismatch_max_allowed: int,
) -> list[dict[str, Any]]:
    """Build compliance check payload rows for paper/evidence runs."""
    checks: list[dict[str, Any]] = []
    checks.append(
        _compliance_check_row(
            "split_hash_present",
            bool(split_hash),
            "fatal",
            "split_hash missing",
            artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
            "Ensure split audit exports before training.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _compliance_check_row(
            "split_audit_exists",
            bool(split_audit_path) and Path(split_audit_path).exists(),
            "fatal",
            "split audit artifact missing",
            artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
            "Export split_freeze_audit_<run_id>.csv prior to training.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _compliance_check_row(
            "duplicate_report_exists",
            bool(duplicate_report_path) and Path(duplicate_report_path).exists(),
            "fatal",
            "duplicate sha report missing",
            artifacts.ArtifactKey.DUPLICATE_SHA_REPORT_CSV,
            "Run duplicate SHA audit after alignment.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _compliance_check_row(
            "duplicate_sha_clean",
            duplicate_count == 0 and invalid_sha_count == 0,
            "fatal",
            f"duplicate/invalid sha detected (dup={duplicate_count}, invalid={invalid_sha_count})",
            artifacts.ArtifactKey.DUPLICATE_SHA_REPORT_CSV,
            "Fix sample universe and rerun paper mode.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _compliance_check_row(
            "vendor_gate_debug_exists",
            bool(vendor_gate_debug_path) and Path(vendor_gate_debug_path).exists(),
            "fatal",
            "vendor gate debug artifact missing",
            artifacts.ArtifactKey.VENDOR_GATE_DEBUG_CSV,
            "Export vendor gate debug CSV from feature build stage.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _compliance_check_row(
            "experiment_registry_exists",
            Path(experiment_registry_path).exists(),
            "fatal",
            "experiment registry missing",
            artifacts.ArtifactKey.EXPERIMENT_REGISTRY_JSON,
            "Ensure registry write in finalize stage.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _compliance_check_row(
            "run_paths_manifest_exists",
            Path(run_paths_manifest_path).exists(),
            "fatal",
            "run paths manifest missing",
            artifacts.ArtifactKey.RUN_PATHS_MANIFEST_JSON,
            "Ensure manifest writer persists run_paths_manifest.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _compliance_check_row(
            "taxonomy_type_audit_not_blind",
            bool(taxonomy_summary_path)
            and Path(taxonomy_summary_path).exists()
            and int(taxonomy_type_rows_evaluated) > 0,
            "fatal",
            f"taxonomy type audit blind or missing (type_rows_evaluated={int(taxonomy_type_rows_evaluated)})",
            artifacts.ArtifactKey.RUN_PATHS_MANIFEST_JSON,
            "Ensure taxonomy audit has type_slug_expected coverage before finalizing paper run.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _compliance_check_row(
            "taxonomy_mismatch_budget_respected",
            bool(taxonomy_summary_path)
            and Path(taxonomy_summary_path).exists()
            and int(taxonomy_mismatch_count) <= int(taxonomy_mismatch_max_allowed),
            "fatal",
            (
                "taxonomy mismatch strict budget exceeded "
                f"(mismatches={int(taxonomy_mismatch_count)}, max_allowed={int(taxonomy_mismatch_max_allowed)})"
            ),
            artifacts.ArtifactKey.RUN_PATHS_MANIFEST_JSON,
            "Reconcile taxonomy mismatches or relax strict mismatch policy before finalizing paper run.",
            enabled=paper_mode,
        )
    )
    return checks


def _compliance_check_row(
    check_id: str,
    passed: bool,
    severity: str,
    reason: str,
    artifact_key: str,
    remediation: str,
    *,
    enabled: bool,
) -> dict[str, Any]:
    """Build one compliance row."""
    if not enabled:
        return {
            "check_id": check_id,
            "status": "skipped",
            "severity": severity,
            "reason": "paper_mode disabled",
            "artifact_key": artifact_key,
            "remediation": "",
        }
    return {
        "check_id": check_id,
        "status": "pass" if passed else "fail",
        "severity": severity,
        "reason": "" if passed else reason,
        "artifact_key": artifact_key,
        "remediation": "" if passed else remediation,
    }
