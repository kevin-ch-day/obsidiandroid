"""Shared live backlog/debt context for operator and pipeline surfaces."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from obsidiandroid.common.backlog_semantics import (
    assess_backlog_triage_health,
    build_backlog_debt_summary,
    choose_priority_triage,
    read_android_missing_resolution_snapshot,
    read_blank_resolved_triage_snapshot,
    read_false_positive_triage_snapshot,
    read_missing_primary_triage_snapshot,
    read_policy_held_token_risk_snapshot,
    read_profile_family_mapping_debt_snapshot,
)
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot
from obsidiandroid.diagnostics.backlog_triage_refresh import refresh_stale_backlog_triage_exports


def preflight_backlog_snapshot_enabled() -> bool:
    """Return whether pipeline preflight should load live backlog/debt context."""
    if os.environ.get("OBSIDIANDROID_TEST_OUTPUT_ROOT", "").strip():
        return False
    raw = os.environ.get("OBSIDIANDROID_PREFLIGHT_SKIP_BACKLOG", "").strip().lower()
    return raw not in {"1", "true", "yes", "on"}


def preflight_auto_refresh_backlog_enabled() -> bool:
    """Return whether pipeline preflight should refresh stale backlog triage exports."""
    if not preflight_backlog_snapshot_enabled():
        return False
    raw = os.environ.get("OBSIDIANDROID_PREFLIGHT_REFRESH_BACKLOG", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def load_backlog_triage_context(*, output_root: Path) -> dict[str, Any]:
    """Load live readiness, triage exports, debt summary, and health in one shape."""
    try:
        readiness = get_cohort_readiness_snapshot()
    except Exception as exc:
        readiness = {
            "status": "degraded",
            "warnings": [f"Cohort readiness unavailable: {exc}"],
            "taxonomy_signals": {},
            "buckets": {},
        }
    fp_triage = read_false_positive_triage_snapshot(output_root=output_root)
    android_triage = read_android_missing_resolution_snapshot(output_root=output_root)
    missing_primary_triage = read_missing_primary_triage_snapshot(output_root=output_root)
    policy_held_triage = read_policy_held_token_risk_snapshot(output_root=output_root)
    profile_mapping_debt = read_profile_family_mapping_debt_snapshot(output_root=output_root)
    blank_resolved_triage = read_blank_resolved_triage_snapshot(output_root=output_root)
    debt_summary = build_backlog_debt_summary(
        readiness=readiness,
        fp_triage=fp_triage,
        android_missing_triage=android_triage,
        policy_held_triage=policy_held_triage,
        missing_primary_triage=missing_primary_triage,
        profile_mapping_debt=profile_mapping_debt,
        blank_resolved_triage=blank_resolved_triage,
    )
    if isinstance(debt_summary, dict):
        debt_summary["source_note"] = "live DB current-state view, not frozen run snapshot"
    priority_backlog = choose_priority_triage(
        fp_triage=fp_triage,
        android_missing_triage=android_triage,
        missing_primary_triage=missing_primary_triage,
    )
    health = assess_backlog_triage_health(
        readiness=readiness,
        android_missing_triage=android_triage,
        fp_triage=fp_triage,
        missing_primary_triage=missing_primary_triage,
        policy_held_triage=policy_held_triage,
        profile_mapping_debt=profile_mapping_debt,
        blank_resolved_triage=blank_resolved_triage,
    )
    return {
        "readiness": readiness,
        "fp_triage": fp_triage,
        "android_missing_triage": android_triage,
        "missing_primary_triage": missing_primary_triage,
        "policy_held_triage": policy_held_triage,
        "profile_mapping_debt": profile_mapping_debt,
        "blank_resolved_triage": blank_resolved_triage,
        "debt_summary": debt_summary,
        "priority_backlog": priority_backlog,
        "backlog_triage_health": health,
    }


def load_backlog_triage_context_with_refresh(
    *,
    output_root: Path,
    auto_refresh_stale: bool = False,
) -> dict[str, Any]:
    """Load backlog context and optionally refresh stale triage exports first."""
    context = load_backlog_triage_context(output_root=output_root)
    health = context.get("backlog_triage_health", {})
    if not auto_refresh_stale or not isinstance(health, dict) or not health.get("needs_refresh"):
        return context
    _, refreshed = refresh_stale_backlog_triage_exports(output_root=output_root)
    if not refreshed:
        return context
    context = load_backlog_triage_context(output_root=output_root)
    context["auto_refreshed_exports"] = refreshed
    return context


def format_pipeline_preflight_backlog_lines(context: dict[str, Any]) -> list[str]:
    """Render compact pipeline preflight lines for live curation debt."""
    if not isinstance(context, dict):
        return []
    debt_summary = context.get("debt_summary", {})
    health = context.get("backlog_triage_health", {})
    if not isinstance(debt_summary, dict):
        debt_summary = {}
    if not isinstance(health, dict):
        health = {}
    lines: list[str] = []
    refreshed = context.get("auto_refreshed_exports", [])
    if isinstance(refreshed, list) and refreshed:
        lines.append(
            "[PREFLIGHT] Refreshed stale backlog triage export(s): "
            + ", ".join(str(key) for key in refreshed)
        )
    focus_label = str(debt_summary.get("focus_label", "") or "").strip()
    focus_count = int(debt_summary.get("focus_count", 0) or 0)
    if focus_label and focus_count > 0:
        lines.append(
            f"[PREFLIGHT] Live curation debt focus: {focus_label} ({focus_count} row(s))."
        )
    android_triage = context.get("android_missing_triage", {})
    if isinstance(android_triage, dict):
        top_lane = str(android_triage.get("top_lane", "") or "").strip()
        top_lane_count = int(android_triage.get("top_lane_count", 0) or 0)
        if top_lane and top_lane_count > 0:
            lines.append(
                f"[PREFLIGHT] Android missing-resolution top lane: {top_lane} ({top_lane_count} row(s))."
            )
        lane_counts = android_triage.get("lane_counts", {})
        if isinstance(lane_counts, dict):
            vt_tail_count = int(lane_counts.get("vt_tail_review", 0) or 0)
            if vt_tail_count > 0:
                lines.append(
                    f"[PREFLIGHT] VT-tail review lane: {vt_tail_count} row(s) "
                    f"(see android_missing_resolution_vt_tail_latest.csv)."
                )
    profile_note = str(debt_summary.get("profile_mapping_note", "") or "").strip()
    if profile_note:
        lines.append(f"[PREFLIGHT] Profile mapping split: {profile_note}")
    if health.get("needs_refresh") and not refreshed:
        exports = health.get("refresh_exports", [])
        if isinstance(exports, list) and exports:
            lines.append(
                "[PREFLIGHT] Stale backlog triage export(s) detected: "
                + ", ".join(str(key) for key in exports)
                + ". Refresh backlog triage exports before trusting operator queues."
            )
    return lines
