"""Tests for backlog triage health assessment and blank-resolved triage wiring."""

from __future__ import annotations

from obsidiandroid.common.backlog_semantics import (
    assess_backlog_triage_health,
    build_backlog_debt_summary,
)


def test_assess_backlog_triage_health_flags_stale_android_export() -> None:
    health = assess_backlog_triage_health(
        readiness={"taxonomy_signals": {"blank_resolved_family_samples": 191}},
        android_missing_triage={"row_count": 0, "freshness": "stale"},
        fp_triage={"row_count": 0, "freshness": "current"},
    )

    assert health["needs_refresh"] is True
    assert "android_missing_resolution" in health["refresh_exports"]


def test_assess_backlog_triage_health_flags_empty_android_mismatch() -> None:
    health = assess_backlog_triage_health(
        readiness={"taxonomy_signals": {"blank_resolved_family_samples": 191}},
        android_missing_triage={"row_count": 0, "freshness": "current"},
        fp_triage={"row_count": 0, "freshness": "current"},
    )

    assert health["needs_refresh"] is True
    assert any(
        issue.get("code") == "android_missing_resolution_empty_mismatch"
        for issue in health["issues"]
        if isinstance(issue, dict)
    )


def test_build_backlog_debt_summary_includes_blank_resolved_row() -> None:
    summary = build_backlog_debt_summary(
        readiness={"taxonomy_signals": {"blank_resolved_family_samples": 191}},
        fp_triage={},
        android_missing_triage={"row_count": 152, "freshness": "current", "top_lane": "vt_tail_review"},
        blank_resolved_triage={
            "row_count": 43,
            "freshness": "current",
            "top_lane": "singleton_provenance_review",
            "top_lane_count": 33,
        },
    )

    blank_row = next(
        row for row in summary["rows"] if row["label"] == "Blank resolved-family residue"
    )
    assert blank_row["count"] == 43
    assert "live_blank_resolved=191" in blank_row["detail"]
