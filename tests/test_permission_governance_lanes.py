"""Tests for permission protection / governance lane classification."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.reporting.permission_governance_lanes import (
    CANONICAL_PROTECTION_LANES,
    LANE_AOSP_DANGEROUS,
    LANE_AOSP_NORMAL,
    LANE_AOSP_PROTECTION_UNRESOLVED,
    LANE_APP_DEFINED,
    LANE_OEM_OR_GOOGLE,
    LANE_UNKNOWN_UNRESOLVED,
    attach_protection_lanes,
    classify_permission_row_reportability,
    classify_protection_lane,
    lane_pair_class,
    ordered_lane_pair,
    reconcile_lane_token_counts,
)


def test_every_canonical_lane_and_multi_flag_ambiguity() -> None:
    assert (
        classify_protection_lane(pi_bucket_source="AOSP", dangerous_bucket="normal")
        == LANE_AOSP_NORMAL
    )
    assert (
        classify_protection_lane(pi_bucket_source="AOSP", dangerous_bucket="dangerous")
        == LANE_AOSP_DANGEROUS
    )
    # Multiple conceptual flags absent → unresolved, not invented signature lane.
    assert (
        classify_protection_lane(pi_bucket_source="AOSP", dangerous_bucket="unknown")
        == LANE_AOSP_PROTECTION_UNRESOLVED
    )
    assert (
        classify_protection_lane(pi_bucket_source="OEM", dangerous_bucket="oem_vendor")
        == LANE_OEM_OR_GOOGLE
    )
    assert (
        classify_protection_lane(pi_bucket_source="GOOGLE", dangerous_bucket="google")
        == LANE_OEM_OR_GOOGLE
    )
    assert (
        classify_protection_lane(pi_bucket_source="APP_DEFINED", dangerous_bucket="app_defined")
        == LANE_APP_DEFINED
    )
    assert (
        classify_protection_lane(pi_bucket_source="UNKNOWN", dangerous_bucket="unknown")
        == LANE_UNKNOWN_UNRESOLVED
    )
    # OEM with dangerous bucket still OEM/Google lane by precedence.
    assert (
        classify_protection_lane(pi_bucket_source="OEM", dangerous_bucket="dangerous")
        == LANE_OEM_OR_GOOGLE
    )


def test_lane_reconciliation_and_missing_fields() -> None:
    audit = pd.DataFrame(
        [
            {"pi_bucket_source": "AOSP", "dangerous_bucket": "normal", "permission_string": "a"},
            {"pi_bucket_source": "AOSP", "dangerous_bucket": "dangerous", "permission_string": "b"},
            {"pi_bucket_source": "AOSP", "dangerous_bucket": "unknown", "permission_string": "c"},
            {"pi_bucket_source": "OEM", "dangerous_bucket": "oem_vendor", "permission_string": "d"},
            {"pi_bucket_source": "GOOGLE", "dangerous_bucket": "google", "permission_string": "e"},
            {"pi_bucket_source": "APP_DEFINED", "dangerous_bucket": "app_defined", "permission_string": "f"},
            {"pi_bucket_source": "UNKNOWN", "dangerous_bucket": "unknown", "permission_string": "g"},
        ]
    )
    framed = attach_protection_lanes(audit)
    recon = reconcile_lane_token_counts(framed["protection_governance_lane"])
    assert recon["reconciles"] is True
    assert recon["total_tokens"] == 7
    assert set(recon["lane_counts"]) == set(CANONICAL_PROTECTION_LANES)
    # Missing governance columns → unresolved
    empty = attach_protection_lanes(pd.DataFrame({"permission_string": ["x"]}))
    assert empty.iloc[0]["protection_governance_lane"] == LANE_UNKNOWN_UNRESOLVED


def test_reportability_gates_and_dominance() -> None:
    assert (
        classify_permission_row_reportability(
            lane=LANE_AOSP_DANGEROUS,
            type_slug="banker",
            positive_samples=100,
            families_with_permission=8,
            largest_family_share=0.2,
            sample_weighted_prevalence=0.4,
            family_balanced_prevalence=0.35,
            odds_ratio=3.0,
        )
        == "family_balanced_supported"
    )
    assert (
        classify_permission_row_reportability(
            lane=LANE_AOSP_DANGEROUS,
            type_slug="banker",
            positive_samples=100,
            families_with_permission=8,
            largest_family_share=0.9,
            sample_weighted_prevalence=0.8,
            family_balanced_prevalence=0.2,
            odds_ratio=5.0,
        )
        == "single_family_dominated"
    )
    assert (
        classify_permission_row_reportability(
            lane=LANE_APP_DEFINED,
            type_slug="banker",
            positive_samples=100,
            families_with_permission=8,
            largest_family_share=0.1,
            sample_weighted_prevalence=0.01,
            family_balanced_prevalence=0.01,
            odds_ratio=10.0,
        )
        == "app_defined_high_cardinality"
    )
    assert (
        classify_permission_row_reportability(
            lane=LANE_AOSP_PROTECTION_UNRESOLVED,
            type_slug="banker",
            positive_samples=100,
            families_with_permission=8,
            largest_family_share=0.1,
            sample_weighted_prevalence=0.5,
            family_balanced_prevalence=0.5,
            odds_ratio=2.0,
        )
        == "protection_level_unresolved"
    )


def test_lane_pair_helpers() -> None:
    assert lane_pair_class(LANE_AOSP_NORMAL, LANE_AOSP_NORMAL) == "within_lane"
    assert lane_pair_class(LANE_AOSP_NORMAL, LANE_AOSP_DANGEROUS) == "cross_lane"
    assert ordered_lane_pair(LANE_AOSP_DANGEROUS, LANE_AOSP_NORMAL) == (
        LANE_AOSP_NORMAL,
        LANE_AOSP_DANGEROUS,
    )
