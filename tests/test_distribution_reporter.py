"""Tests for ``obsidiandroid.modeling.distribution_reporter``."""

from __future__ import annotations

from collections import Counter

import pandas as pd

from obsidiandroid.modeling import distribution_reporter as dr
from obsidiandroid.reporting import family_distribution_report


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
    f, lbl, affected, fams, detail = dr.apply_min_family_support(
        df, labels, min_support=2, group_label=None
    )
    assert len(f) == 4
    assert "B" not in lbl.values
    assert affected == 1
    assert fams == 1
    assert detail == [{"family": "B", "aligned_support": 1}]


def test_apply_min_family_support_group() -> None:
    df, labels = _sample_df_and_labels()
    f, lbl, affected, fams, detail = dr.apply_min_family_support(
        df, labels, min_support=2, group_label="other"
    )
    assert len(f) == 5
    assert (lbl == "other").sum() == 1
    assert "B" not in lbl.values
    assert affected == 1
    assert fams == 1
    assert detail == [{"family": "B", "aligned_support": 1}]


def test_generate_family_report_uses_configured_min_support() -> None:
    fam_counts = Counter({"A": 19, "B": 20, "C": 48})

    report = family_distribution_report._generate_family_report_text(  # pylint: disable=protected-access
        fam_counts,
        min_support=20,
    )

    assert "Configured Min Family Support       : 20" in report
    assert "Low-Sample Families (<20)          : 1" in report
    assert "Sufficient-Sample Families (>=20)  : 2" in report


def test_resolve_min_family_support_prefers_dataframe_attr() -> None:
    df = pd.DataFrame({"family_name": ["A", "B"]})
    df.attrs["configured_min_samples_per_family"] = 20

    out = family_distribution_report._resolve_min_family_support(df)  # pylint: disable=protected-access

    assert out == 20
