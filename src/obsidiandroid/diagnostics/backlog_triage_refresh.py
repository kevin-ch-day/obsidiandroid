"""Portable backlog triage export refresh for pipeline and operator surfaces."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

from obsidiandroid.common.backlog_semantics import (
    assess_backlog_triage_health,
    read_android_missing_resolution_snapshot,
    read_blank_resolved_triage_snapshot,
    read_false_positive_triage_snapshot,
    read_missing_primary_triage_snapshot,
    read_policy_held_token_risk_snapshot,
    read_profile_family_mapping_debt_snapshot,
)
from obsidiandroid.common.repo_paths import repo_operator_script
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot

_EXPORT_SCRIPT_PARTS: dict[str, tuple[str, ...]] = {
    "android_missing_resolution": ("diagnostics", "report_android_missing_resolution_triage.py"),
    "missing_primary_label": ("diagnostics", "report_missing_primary_label_triage.py"),
    "vt_false_positive_review": ("diagnostics", "report_vt_false_positive_review_triage.py"),
    "policy_held_token_risk": ("diagnostics", "report_android_policy_held_token_risk.py"),
    "profile_family_mapping_debt": ("diagnostics", "report_profile_family_mapping_debt.py"),
    "blank_resolved_family": ("diagnostics", "report_blank_resolved_family_triage.py"),
    "operator_summary": ("diagnostics", "report_backlog_debt_operator_summary.py"),
}


def run_backlog_triage_script(
    export_key: str,
    *,
    operator_script_resolver: Callable[..., Path] = repo_operator_script,
    subprocess_run: Callable[..., object] = subprocess.run,
) -> int:
    """Run one backlog triage diagnostics script by export key."""
    script_parts = _EXPORT_SCRIPT_PARTS.get(str(export_key or "").strip())
    if not script_parts:
        return 1
    script_path = operator_script_resolver(*script_parts)
    if not script_path.is_file():
        return 1
    proc = subprocess_run([sys.executable, str(script_path)], check=False)
    return int(getattr(proc, "returncode", 0) or 0)


def assess_backlog_triage_health_for_output_root(*, output_root: Path) -> dict[str, object]:
    """Assess backlog triage export freshness for one output root."""
    try:
        readiness = get_cohort_readiness_snapshot()
    except Exception:
        readiness = {"taxonomy_signals": {}}
    return assess_backlog_triage_health(
        readiness=readiness,
        android_missing_triage=read_android_missing_resolution_snapshot(output_root=output_root),
        fp_triage=read_false_positive_triage_snapshot(output_root=output_root),
        missing_primary_triage=read_missing_primary_triage_snapshot(output_root=output_root),
        policy_held_triage=read_policy_held_token_risk_snapshot(output_root=output_root),
        profile_mapping_debt=read_profile_family_mapping_debt_snapshot(output_root=output_root),
        blank_resolved_triage=read_blank_resolved_triage_snapshot(output_root=output_root),
    )


def refresh_stale_backlog_triage_exports(
    *,
    output_root: Path,
    operator_script_resolver: Callable[..., Path] = repo_operator_script,
    subprocess_run: Callable[..., object] = subprocess.run,
    refresh_exports: list[str] | None = None,
    include_operator_summary: bool = True,
) -> tuple[int, list[str]]:
    """Refresh stale or mismatched backlog triage exports and return rc + keys refreshed."""
    explicit_keys = (
        [str(key) for key in refresh_exports if str(key).strip()]
        if isinstance(refresh_exports, list) and refresh_exports
        else []
    )
    if explicit_keys:
        keys = explicit_keys
    else:
        health = assess_backlog_triage_health_for_output_root(output_root=output_root)
        keys = [
            str(key)
            for key in (health.get("refresh_exports", []) if isinstance(health, dict) else [])
            if str(key).strip()
        ]
    if not keys:
        return 0, []
    rc = 0
    refreshed: list[str] = []
    for export_key in keys:
        step_rc = run_backlog_triage_script(
            export_key,
            operator_script_resolver=operator_script_resolver,
            subprocess_run=subprocess_run,
        )
        rc = rc or step_rc
        refreshed.append(export_key)
    if include_operator_summary:
        summary_rc = run_backlog_triage_script(
            "operator_summary",
            operator_script_resolver=operator_script_resolver,
            subprocess_run=subprocess_run,
        )
        rc = rc or summary_rc
        refreshed.append("operator_summary")
    return rc, refreshed
