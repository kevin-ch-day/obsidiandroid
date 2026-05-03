"""Tests for profile-driven dataset partition filters."""

from __future__ import annotations

import pandas as pd

from analysis.orchestration import profile_filters


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
