"""Tests for profile family-mapping debt exports and backlog wiring."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.common.backlog_semantics import (
    build_backlog_debt_summary,
    read_profile_family_mapping_debt_snapshot,
)


def test_read_profile_family_mapping_debt_snapshot_reads_allcurrent_focus(tmp_path: Path) -> None:
    path = tmp_path / "diagnostics" / "profile_family_mapping_debt_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "android_malware_major_families",
                        "governed_sql_rows": 100,
                        "excluded_unmapped_family_rows": 0,
                        "blank_resolved_slug_rows": 0,
                        "policy_held_resolved_slug_rows": 0,
                        "true_unmapped_resolved_slug_rows": 0,
                    },
                    {
                        "profile_id": "android_malware_all_current",
                        "governed_sql_rows": 5587,
                        "excluded_unmapped_family_rows": 236,
                        "blank_resolved_slug_rows": 159,
                        "policy_held_resolved_slug_rows": 77,
                        "true_unmapped_resolved_slug_rows": 0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = read_profile_family_mapping_debt_snapshot(output_root=tmp_path)

    assert snapshot["profile_id"] == "android_malware_all_current"
    assert snapshot["family_mapped_rows"] == 5351
    assert snapshot["excluded_unmapped_family_rows"] == 236
    assert snapshot["blank_resolved_slug_rows"] == 159
    assert snapshot["policy_held_resolved_slug_rows"] == 77
    assert snapshot["freshness"] == "current"


def test_build_backlog_debt_summary_includes_profile_mapping_note() -> None:
    summary = build_backlog_debt_summary(
        readiness={
            "taxonomy_signals": {
                "blank_resolved_family_samples": 191,
                "missing_primary_label_samples": 0,
                "unresolved_family_samples": 0,
                "policy_held_family_samples": 0,
                "family_type_conflict_count": 0,
            }
        },
        fp_triage={},
        android_missing_triage={
            "row_count": 152,
            "freshness": "current",
            "top_lane": "vt_tail_review",
            "top_lane_count": 89,
        },
        profile_mapping_debt={
            "profile_id": "android_malware_all_current",
            "governed_sql_rows": 5587,
            "excluded_unmapped_family_rows": 236,
            "blank_resolved_slug_rows": 159,
            "policy_held_resolved_slug_rows": 77,
            "true_unmapped_resolved_slug_rows": 0,
            "freshness": "current",
        },
    )

    assert "profile_mapping_note" in summary
    assert "blank_resolved=159" in summary["profile_mapping_note"]
    android_row = next(
        row
        for row in summary["rows"]
        if row["label"] == "Android missing-resolution backlog"
    )
    assert "live_blank_resolved=191" in android_row["detail"]
