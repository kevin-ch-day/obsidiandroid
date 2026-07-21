"""Tests for permission protection / governance lane classification (v2)."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.reporting.permission_governance_lanes import (
    CANONICAL_PROTECTION_LANES,
    LANE_AOSP_DANGEROUS,
    LANE_AOSP_NORMAL,
    LANE_AOSP_SIGNATURE,
    LANE_AOSP_SIGNATURE_PRIVILEGED,
    LANE_APP_DEFINED,
    LANE_GOOGLE_PLATFORM,
    LANE_OEM_PLATFORM,
    LANE_UNKNOWN_UNRESOLVED,
    attach_protection_lanes,
    classify_permission_row_reportability,
    classify_protection_lane,
    lane_pair_class,
    ordered_lane_pair,
    reconcile_lane_token_counts,
)


def test_every_canonical_lane_including_signature_and_split_oem_google() -> None:
    assert (
        classify_protection_lane(pi_bucket_source="AOSP", dangerous_bucket="normal")
        == LANE_AOSP_NORMAL
    )
    assert (
        classify_protection_lane(pi_bucket_source="AOSP", dangerous_bucket="dangerous")
        == LANE_AOSP_DANGEROUS
    )
    # Without structured protection level, AOSP+unknown is unresolved (not invented signature).
    assert (
        classify_protection_lane(pi_bucket_source="AOSP", dangerous_bucket="unknown")
        == LANE_UNKNOWN_UNRESOLVED
    )
    assert (
        classify_protection_lane(
            pi_bucket_source="AOSP",
            dangerous_bucket="unknown",
            base_protection_level="signature",
        )
        == LANE_AOSP_SIGNATURE
    )
    assert (
        classify_protection_lane(
            pi_bucket_source="AOSP",
            dangerous_bucket="unknown",
            base_protection_level="signature",
            protection_flags="privileged",
        )
        == LANE_AOSP_SIGNATURE_PRIVILEGED
    )
    assert (
        classify_protection_lane(pi_bucket_source="OEM", dangerous_bucket="oem_vendor")
        == LANE_OEM_PLATFORM
    )
    assert (
        classify_protection_lane(pi_bucket_source="GOOGLE", dangerous_bucket="google")
        == LANE_GOOGLE_PLATFORM
    )
    assert (
        classify_protection_lane(pi_bucket_source="APP_DEFINED", dangerous_bucket="app_defined")
        == LANE_APP_DEFINED
    )
    assert (
        classify_protection_lane(pi_bucket_source="UNKNOWN", dangerous_bucket="unknown")
        == LANE_UNKNOWN_UNRESOLVED
    )


def test_lane_reconciliation_and_missing_fields() -> None:
    audit = pd.DataFrame(
        [
            {"pi_bucket_source": "AOSP", "dangerous_bucket": "normal", "permission_string": "a"},
            {"pi_bucket_source": "AOSP", "dangerous_bucket": "dangerous", "permission_string": "b"},
            {
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "unknown",
                "permission_string": "c",
                "base_protection_level": "signature",
                "protection_flags": "",
            },
            {
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "unknown",
                "permission_string": "d",
                "base_protection_level": "signature",
                "protection_flags": "privileged",
            },
            {"pi_bucket_source": "OEM", "dangerous_bucket": "oem_vendor", "permission_string": "e"},
            {"pi_bucket_source": "GOOGLE", "dangerous_bucket": "google", "permission_string": "f"},
            {"pi_bucket_source": "APP_DEFINED", "dangerous_bucket": "app_defined", "permission_string": "g"},
            {"pi_bucket_source": "UNKNOWN", "dangerous_bucket": "unknown", "permission_string": "h"},
        ]
    )
    framed = attach_protection_lanes(audit)
    recon = reconcile_lane_token_counts(framed["protection_governance_lane"])
    assert recon["reconciles"] is True
    assert recon["total_tokens"] == 8
    assert set(recon["lane_counts"]) == set(CANONICAL_PROTECTION_LANES)
    assert recon["lane_counts"][LANE_AOSP_SIGNATURE] == 1
    assert recon["lane_counts"][LANE_AOSP_SIGNATURE_PRIVILEGED] == 1
    assert recon["lane_counts"][LANE_OEM_PLATFORM] == 1
    assert recon["lane_counts"][LANE_GOOGLE_PLATFORM] == 1
    assert "base_protection_level" in framed.columns
    assert "protection_flags" in framed.columns
    assert "governance_namespace" in framed.columns
    assert "headline_lane" in framed.columns
    empty = attach_protection_lanes(pd.DataFrame({"permission_string": ["x"]}))
    assert empty.iloc[0]["protection_governance_lane"] == LANE_UNKNOWN_UNRESOLVED


def test_reportability_gates_dominance_and_app_defined_identity() -> None:
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
            sample_weighted_prevalence=0.4,
            family_balanced_prevalence=0.35,
            odds_ratio=3.0,
        )
        == "single_family_dominated"
    )
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
            leave_dominant_sensitive=True,
        )
        == "dominant_family_sensitive"
    )
    assert (
        classify_permission_row_reportability(
            lane=LANE_APP_DEFINED,
            type_slug="banker",
            positive_samples=2,
            families_with_permission=1,
            largest_family_share=1.0,
            sample_weighted_prevalence=0.01,
            family_balanced_prevalence=0.01,
            odds_ratio=1.0,
        )
        == "identity_risk"
    )
    assert lane_pair_class(LANE_AOSP_NORMAL, LANE_AOSP_DANGEROUS) == "cross_lane"
    assert ordered_lane_pair(LANE_AOSP_DANGEROUS, LANE_AOSP_NORMAL) == (
        LANE_AOSP_NORMAL,
        LANE_AOSP_DANGEROUS,
    )
