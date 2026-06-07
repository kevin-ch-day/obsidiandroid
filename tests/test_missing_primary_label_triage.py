"""Tests for missing-primary label triage export and backlog wiring."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.common.backlog_semantics import (
    build_backlog_debt_summary,
    read_missing_primary_triage_snapshot,
)


def test_read_missing_primary_triage_snapshot_reads_lane_counts(tmp_path: Path) -> None:
    csv_path = tmp_path / "diagnostics" / "missing_primary_label_triage_latest.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "sample_id": 101,
                "residual_lane": "fake_app_or_impersonation_signal_review",
                "recommended_triage_action": "Review impersonation/fake-app vendor signals before primary assignment.",
            },
            {
                "sample_id": 102,
                "residual_lane": "manual_review",
                "recommended_triage_action": "Manual review before classification_primary backfill.",
            },
        ]
    ).to_csv(csv_path, index=False)

    snapshot = read_missing_primary_triage_snapshot(output_root=tmp_path)

    assert snapshot["row_count"] == 2
    assert snapshot["top_lane"] == "fake_app_or_impersonation_signal_review"
    assert snapshot["top_lane_count"] == 1
    assert snapshot["freshness"] == "current"


def test_build_backlog_debt_summary_uses_missing_primary_triage_action() -> None:
    summary = build_backlog_debt_summary(
        readiness={
            "taxonomy_signals": {
                "missing_primary_label_samples": 3,
                "missing_primary_label_raw_samples": 5,
                "missing_primary_label_actionable_samples": 0,
                "missing_primary_label_residual_samples": 5,
                "missing_primary_label_suppressed_samples": 2,
                "missing_primary_label_active_residual_samples": 3,
            }
        },
        fp_triage={},
        android_missing_triage={},
        missing_primary_triage={
            "row_count": 3,
            "freshness": "current",
            "top_lane": "manual_review",
            "top_lane_count": 2,
        },
    )

    missing_row = next(
        row for row in summary["rows"] if row["label"] == "Missing primary labels"
    )
    assert missing_row["count"] == 3
    assert "missing-primary label triage export" in missing_row["action"]
    assert "top_lane=manual_review (2)" in missing_row["detail"]
