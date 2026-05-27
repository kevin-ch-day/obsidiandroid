from __future__ import annotations

from collections import Counter

import pandas as pd

from obsidiandroid.reporting import family_distribution_report


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
