"""Unit tests for strict lifecycle-aware authority readiness counts."""

from __future__ import annotations

from obsidiandroid.database.db_cohort_readiness import _authority_lifecycle_coverage


def test_authority_lifecycle_coverage_separates_broad_and_strict_rows() -> None:
    rows = [
        {
            "sample_id": 1,
            "family_slug": "anubis",
            "authority_bucket": "authority_family_typed",
            "family_is_active": 1,
            "type_is_active": 1,
        },
        {
            "sample_id": 2,
            "family_slug": "kuguo",
            "authority_bucket": "authority_family_typed",
            "family_is_active": 1,
            "type_is_active": 0,
        },
        {
            "sample_id": 3,
            "family_slug": "kuguo",
            "authority_bucket": "authority_family_typed",
            "family_is_active": 1,
            "type_is_active": 0,
        },
        {
            "sample_id": 4,
            "family_slug": "oldfamily",
            "authority_bucket": "authority_family_typed",
            "family_is_active": 0,
            "type_is_active": 1,
        },
        {
            "sample_id": 5,
            "family_slug": "unknown",
            "authority_bucket": "resolved_unknown",
            "family_is_active": None,
            "type_is_active": None,
        },
    ]

    coverage = _authority_lifecycle_coverage(
        authority_rows=rows,
        permission_sample_ids={1, 2, 3, 4, 5},
        source_mode="live_view",
    )

    assert coverage == {
        "typed_authority_permission_obs_samples": 4,
        "typed_authority_permission_obs_families": 3,
        "strict_active_authority_permission_obs_samples": 1,
        "strict_active_authority_permission_obs_families": 1,
        "retired_type_authority_permission_obs_samples": 2,
        "inactive_family_authority_permission_obs_samples": 1,
        "unknown_lifecycle_authority_permission_obs_samples": 0,
    }


def test_authority_lifecycle_coverage_refuses_strict_counts_without_flags() -> None:
    coverage = _authority_lifecycle_coverage(
        authority_rows=[
            {
                "sample_id": 1,
                "family_slug": "anubis",
                "authority_bucket": "authority_family_typed",
            }
        ],
        permission_sample_ids={1},
        source_mode="live_view",
    )

    assert coverage["typed_authority_permission_obs_samples"] == 1
    assert coverage["strict_active_authority_permission_obs_samples"] is None
    assert coverage["retired_type_authority_permission_obs_samples"] is None


def test_authority_lifecycle_coverage_is_unavailable_for_legacy_fallback() -> None:
    coverage = _authority_lifecycle_coverage(
        authority_rows=[],
        permission_sample_ids=set(),
        source_mode="legacy_resolution_fallback",
    )

    assert all(value is None for value in coverage.values())
