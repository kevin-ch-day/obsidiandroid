"""Tests for missing-primary label triage export and backlog wiring."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.common.backlog_semantics import (
    assess_backlog_triage_health,
    build_backlog_debt_summary,
    choose_priority_triage,
    read_missing_primary_triage_snapshot,
)
from scripts.diagnostics.report_missing_primary_label_triage import (
    attach_proposal_review_fields,
    build_authority_backfill_proposals,
    build_review_template,
)


def test_build_authority_backfill_proposals_groups_review_only_candidates() -> None:
    detail_rows = pd.DataFrame(
        [
            {
                "sample_id": 9,
                "residual_lane": "authority_backed_primary_backfill_review",
                "proposed_classification_primary": "trojan",
                "authority_type_slug": "banker",
                "authority_parent_type_slug": "trojan",
                "authority_family_slug": "anubis",
                "confidence_bucket": "high",
            },
            {
                "sample_id": 3,
                "residual_lane": "authority_backed_primary_backfill_review",
                "proposed_classification_primary": "trojan",
                "authority_type_slug": "banker",
                "authority_parent_type_slug": "trojan",
                "authority_family_slug": "anubis",
                "confidence_bucket": "high",
            },
            {
                "sample_id": 12,
                "residual_lane": "high_strong_primary_no_authority_review",
                "proposed_classification_primary": "",
                "authority_type_slug": "",
                "authority_parent_type_slug": "",
                "authority_family_slug": "",
                "confidence_bucket": "strong",
            },
        ]
    )

    proposals = build_authority_backfill_proposals(detail_rows)

    record = proposals.to_dict("records")[0]
    assert record["proposal_id"].startswith("mpb_")
    assert record["review_status"] == "pending_human_review"
    assert record["proposed_classification_primary"] == "trojan"
    assert record["authority_type_slug"] == "banker"
    assert record["authority_parent_type_slug"] == "trojan"
    assert record["authority_family_slug"] == "anubis"
    assert record["confidence_bucket"] == "high"
    assert record["sample_count"] == 2
    assert record["sample_ids"] == "3,9"
    assert len(record["sample_id_hash"]) == 64

    detailed = attach_proposal_review_fields(detail_rows, proposals)
    assert detailed.loc[detailed["sample_id"].eq(12), "proposal_id"].item() == ""
    assert detailed.loc[detailed["sample_id"].eq(12), "proposal_review_status"].item() == "not_closure_ready"
    candidate_ids = detailed.loc[detailed["sample_id"].isin([3, 9]), "proposal_id"].unique().tolist()
    assert candidate_ids == [record["proposal_id"]]
    assert set(
        detailed.loc[detailed["sample_id"].isin([3, 9]), "proposal_review_status"]
    ) == {"pending_human_review"}

    template = build_review_template(proposals)
    assert template.loc[0, "proposal_id"] == record["proposal_id"]
    assert template.loc[0, "decision"] == "pending"
    assert template.loc[0, "review_status"] == "pending_human_review"
    assert template.loc[0, "sample_id_hash"] == record["sample_id_hash"]


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


def test_missing_primary_snapshot_requires_current_authority_backfill_schema(tmp_path: Path) -> None:
    """A legacy CSV must trigger refresh even if its mtime is recent."""
    csv_path = tmp_path / "diagnostics" / "missing_primary_label_triage_latest.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"sample_id": 1, "residual_lane": "manual_review", "recommended_triage_action": "Review."}]
    ).to_csv(csv_path, index=False)

    snapshot = read_missing_primary_triage_snapshot(output_root=tmp_path)
    health = assess_backlog_triage_health(
        readiness={"taxonomy_signals": {"missing_primary_label_active_residual_samples": 1}},
        android_missing_triage={},
        fp_triage={},
        missing_primary_triage=snapshot,
    )

    assert snapshot["schema_status"] == "incompatible"
    assert "authority_family_slug" in snapshot["missing_required_columns"]
    assert "missing_primary_label" in health["refresh_exports"]


def test_priority_uses_closure_ready_missing_primary_subset(tmp_path: Path) -> None:
    """Large provenance queues must not hide a smaller authority-backed closure queue."""
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    row = {
        "sample_id": 1,
        "authority_bucket": "authority_family_typed",
        "resolved_family_lc": "anubis",
        "authority_family_slug": "anubis",
        "authority_type_slug": "banker",
        "authority_parent_type_slug": "trojan",
        "proposed_classification_primary": "trojan",
        "confidence_bucket": "high",
        "residual_lane": "authority_backed_primary_backfill_review",
        "recommended_triage_action": "Review authority-backed primary proposal.",
    }
    pd.DataFrame([row, {**row, "sample_id": 2, "residual_lane": "pua_adware_or_testkey_signal_review"}]).to_csv(
        diagnostics / "missing_primary_label_triage_latest.csv", index=False
    )
    pd.DataFrame([{"sample_count": 1}]).to_csv(
        diagnostics / "missing_primary_label_authority_backfill_proposals_latest.csv", index=False
    )

    snapshot = read_missing_primary_triage_snapshot(output_root=tmp_path)
    priority = choose_priority_triage(
        android_missing_triage={"row_count": 1, "freshness": "current"},
        fp_triage={},
        missing_primary_triage=snapshot,
    )

    assert snapshot["schema_status"] == "compatible"
    assert snapshot["closure_ready_row_count"] == 1
    assert snapshot["proposal_sample_count"] == 1
    assert priority["label"] == "Authority-backed primary backfill review"
    assert priority["row_count"] == 1


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
