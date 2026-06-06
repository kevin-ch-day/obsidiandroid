"""Aligned→trainable loss wording in research question artifacts."""

from __future__ import annotations

from obsidiandroid.reporting.research_three_questions import _describe_aligned_to_trainable_loss


def test_lineage_loss_describes_authority_filter_not_support_floor() -> None:
    text = _describe_aligned_to_trainable_loss(
        aligned=4563,
        trainable=4352,
        manifest_context={
            "alignment_attrition_stats": {
                "alignment_non_authoritative_family_drop_count": 211,
            },
            "support_floor_mode": "diagnostic_only",
        },
        low_support_drop_detail=[],
    )
    assert "family-authority filter" in text
    assert "211 non-authoritative" in text
    assert "min-family-support" not in text


def test_lineage_loss_describes_support_floor_when_rows_dropped() -> None:
    text = _describe_aligned_to_trainable_loss(
        aligned=2123,
        trainable=2000,
        manifest_context={"support_floor_mode": "benchmark_eligibility"},
        low_support_drop_detail=[{"family": "Ginp", "aligned_support": 1}],
    )
    assert "min-family-support filter" in text
