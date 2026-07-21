"""Tests for canonical cohort family/type count contract."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.reporting.cohort_count_contract import (
    COHORT_COUNT_CONTRACT_VERSION,
    compute_cohort_identity_counts,
    format_family_type_count_lines,
    normalize_family_labels_including_unknown,
)


def test_compute_cohort_identity_counts_splits_unknown_bucket() -> None:
    frame = pd.DataFrame(
        {
            "family_canonical": ["ClayRat", "Godfather", "", "unknown", "ClayRat", None],
            "type_slug": ["rat", "banker", "unknown", "", "rat", "banker"],
        }
    )
    counts = compute_cohort_identity_counts(frame)
    assert counts["contract_version"] == COHORT_COUNT_CONTRACT_VERSION
    assert counts["governed_known_family_count"] == 2
    assert counts["observed_family_label_count_including_unknown"] == 3
    assert counts["unknown_family_sample_count"] == 3
    assert counts["governed_known_type_count"] == 2
    assert counts["observed_type_slug_count_including_unknown"] == 3
    assert counts["unknown_type_sample_count"] == 2


def test_normalize_blank_to_unknown() -> None:
    series = pd.Series(["A", "", None, "unknown", "  "])
    out = normalize_family_labels_including_unknown(series)
    assert list(out) == ["A", "unknown", "unknown", "unknown", "unknown"]


def test_format_family_type_count_lines() -> None:
    lines = format_family_type_count_lines(
        {
            "governed_known_family_count": 206,
            "observed_family_label_count_including_unknown": 207,
            "governed_known_type_count": 14,
            "observed_type_slug_count_including_unknown": 15,
        }
    )
    assert lines[0] == "Known governed families: 206"
    assert lines[1] == "Observed family labels: 207 including `unknown`"
    assert lines[2] == "Known governed types: 14"
    assert lines[3] == "Observed type_slug values: 15 including `unknown`"
