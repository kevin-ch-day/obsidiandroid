"""Tests for profile-driven dataset partition filters."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.orchestration import profile_filters


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
