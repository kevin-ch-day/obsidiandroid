"""Tests for ``ml_classification.ml_utils.distribution_reporter``."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.modeling import distribution_reporter as dr


def test_build_distribution_df_basic() -> None:
    labels = ["A", "A", "B", "C", "C", "C"]
    df = dr.build_distribution_df(labels)
    assert list(df.columns) == ["family", "count", "percent", "support_tier"]
    assert df.loc[df["family"] == "C", "count"].iloc[0] == 3
    assert round(df["percent"].sum(), 2) == 100.00


def _sample_df_and_labels() -> tuple[pd.DataFrame, pd.Series]:
    df = pd.DataFrame({"feat": [0, 1, 2, 3, 4]}, index=[f"s{i}" for i in range(5)])
    labels = pd.Series(["A", "A", "B", "C", "C"], index=df.index)
    return df, labels


def test_apply_min_family_support_remove() -> None:
    df, labels = _sample_df_and_labels()
    f, l, affected, fams = dr.apply_min_family_support(
        df, labels, min_support=2, group_label=None
    )
    assert len(f) == 4
    assert "B" not in l.values
    assert affected == 1
    assert fams == 1


def test_apply_min_family_support_group() -> None:
    df, labels = _sample_df_and_labels()
    f, l, affected, fams = dr.apply_min_family_support(
        df, labels, min_support=2, group_label="other"
    )
    assert len(f) == 5
    assert (l == "other").sum() == 1
    assert "B" not in l.values
    assert affected == 1
    assert fams == 1
