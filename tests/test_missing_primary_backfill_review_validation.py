"""Tests for read-only missing-primary review-ledger validation."""

from __future__ import annotations

import pandas as pd

from scripts.diagnostics.validate_missing_primary_backfill_review import validate_review_ledger


def _proposal_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "proposal_id": "mpb_a",
                "proposed_classification_primary": "trojan",
                "authority_type_slug": "banker",
                "authority_parent_type_slug": "trojan",
                "authority_family_slug": "anubis",
                "confidence_bucket": "high",
                "sample_count": 3,
                "sample_id_hash": "a" * 64,
            }
        ]
    )


def _ledger_frame(*, decision: str = "pending") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                **_proposal_frame().iloc[0].to_dict(),
                "review_status": "pending_human_review",
                "decision": decision,
                "reviewer": "reviewer" if decision != "pending" else "",
                "reviewed_at_utc": "2026-07-16T14:00:00+00:00" if decision != "pending" else "",
                "review_note": "evidence checked" if decision != "pending" else "",
            }
        ]
    )


def test_review_ledger_validator_accepts_matching_pending_ledger() -> None:
    report = validate_review_ledger(_proposal_frame(), _ledger_frame())

    assert report["valid"] is True
    assert report["approved_sample_count"] == 0
    assert report["pending_proposal_count"] == 1


def test_review_ledger_validator_rejects_changed_membership_hash() -> None:
    ledger = _ledger_frame(decision="approved")
    ledger.loc[0, "sample_id_hash"] = "b" * 64

    report = validate_review_ledger(_proposal_frame(), ledger)

    assert report["valid"] is False
    assert any(str(error).startswith("ledger_identity_mismatch=") for error in report["errors"])


def test_review_ledger_validator_requires_metadata_for_resolved_decision() -> None:
    ledger = _ledger_frame(decision="approved")
    ledger.loc[0, "review_note"] = ""

    report = validate_review_ledger(_proposal_frame(), ledger)

    assert report["valid"] is False
    assert any("resolved_decision_missing_reviewer_metadata" in str(error) for error in report["errors"])
