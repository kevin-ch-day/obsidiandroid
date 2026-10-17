"""Tests for profile-driven dataset partition filters."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.orchestration import profile_filters


def test_unfiltered_exploration_keeps_benign_malicious_and_unresolved_rows() -> None:
    samples = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "vt_malicious_count": [2, 0, pd.NA],
            "vt_suspicious_count": [0, 0, pd.NA],
            "vt_undetected_count": [0, 5, pd.NA],
            "vt_reputation": [0, 1, pd.NA],
        }
    )

    out = profile_filters.apply_dataset_filters(samples, {"dataset_filters": {"mode": "none"}})

    assert out.sample_id.tolist() == [1, 2, 3]
    summary = out.attrs["cohort_filter_summary"]
    assert summary["malicious_candidates"] == 1
    assert summary["benign_candidates"] == 1
    assert summary["unresolved_candidates"] == 1


def test_partitions_hold_conflicts_and_incomplete_zero_consensus() -> None:
    """Partition counts must be disjoint and must not infer an absent VT count as zero."""
    samples = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "vt_malicious_count": [pd.NA, 0, 1, 0, pd.NA],
            "vt_suspicious_count": [pd.NA, pd.NA, pd.NA, 0, pd.NA],
            "vt_undetected_count": [pd.NA, 5, 0, 5, pd.NA],
            "vt_reputation": [pd.NA, 1, 0, 1, pd.NA],
            "category_primary": ["benign", "", "", "", "benign"],
            "family_canonical": ["NamedFamily", "", "", "", ""],
        }
    )

    benign, malicious = profile_filters.split_benign_malicious(samples)
    summary = profile_filters.apply_dataset_filters(
        samples, {"dataset_filters": {"mode": "none"}}
    ).attrs["cohort_filter_summary"]

    assert benign.sample_id.tolist() == [4, 5]
    assert malicious.sample_id.tolist() == [3]
    assert summary["benign_candidates"] == 2
    assert summary["malicious_candidates"] == 1
    assert summary["unresolved_candidates"] == 2


def test_malicious_only_retains_vt_positive_rows_only() -> None:
    """malicious_only should drop VT-clean rows instead of returning the full SQL cohort."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "vt_malicious_count": [1, 0, 0],
            "vt_suspicious_count": [0, 0, 0],
            "vt_undetected_count": [0, 5, 0],
            "vt_reputation": [0.0, 1.0, 0.0],
        }
    )
    profile = {
        "dataset_filters": {"mode": "malicious_only"},
    }
    out = profile_filters.apply_dataset_filters(samples_df, profile)
    assert list(out["sample_id"]) == [1]
    summary = out.attrs.get("cohort_filter_summary", {})
    assert summary.get("post_filter_total") == 1
    assert summary.get("malicious_candidates") == 1


def test_malicious_only_retains_taxonomy_backed_rows_when_vt_consensus_missing() -> None:
    """Missing VT counts should not eject rows that are still classified as malware by taxonomy."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "vt_malicious_count": [pd.NA, 0],
            "vt_suspicious_count": [pd.NA, 0],
            "vt_undetected_count": [pd.NA, 5],
            "vt_reputation": [pd.NA, 1.0],
            "family_canonical": ["Alien", ""],
            "type_slug": ["banker", ""],
            "vt_suggested_label": ["trojan.bankbot/alien", ""],
        }
    )
    profile = {
        "dataset_filters": {"mode": "malicious_only"},
    }

    out = profile_filters.apply_dataset_filters(samples_df, profile)

    assert list(out["sample_id"]) == [1]
    summary = out.attrs.get("cohort_filter_summary", {})
    assert summary.get("malicious_candidates") == 1


def test_textual_null_taxonomy_tokens_do_not_rescue_missing_consensus_rows() -> None:
    """CSV-style null strings are absence of evidence, not malicious taxonomy."""
    frame = pd.DataFrame(
        {
            "family_canonical": ["nan", "n/a", "NamedFamily"],
            "type_slug": ["n/a", "null", "banker"],
            "category_primary": ["", "", ""],
            "category_subtype": ["", "", ""],
            "vt_suggested_label": ["", "", ""],
        }
    )

    assert profile_filters.malicious_signal_or_taxonomy_mask(frame).tolist() == [False, False, True]
