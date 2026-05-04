"""Tests for cohort readiness summary formatting and policy highlights."""

from __future__ import annotations

import pandas as pd

import obsidiandroid.governance.cohort_readiness_report as cohort_readiness_report


def test_cohort_readiness_report_prints_percentages_and_concentration(capsys) -> None:
    """Summary should include type percentages and family concentration metrics."""
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "type_slug": ["banker", "banker", "adware", "rat", "rat"],
            "family_canonical": ["A", "A", "B", "C", "D"],
            "android_package_name": ["pkg.a", "", "pkg.b", "pkg.c", "pkg.d"],
            "vt_first_submission_date": ["2024-01-01", "2024-01-01", "2024-01-01", "2024-01-01", "2024-01-01"],
        }
    )
    df.attrs["sql_exclude_families_applied"] = ("devixor", "gigabud")

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"exclude_unknown_type_slug": True, "min_samples_per_family": 20, "max_missing_package_pct": 5.0},
    )
    out = capsys.readouterr().out
    out_lower = out.lower()

    assert "Cohort Readiness Summary" in out
    assert "type distribution" in out_lower
    assert "family concentration" in out_lower
    assert "top family" in out_lower
    assert "top 3 families" in out_lower
    assert "top 5 families" in out_lower
    assert "(40.00%)" in out or "(40.0%)" in out
    assert "Excluded Families" in out
    assert "devixor, gigabud" in out


def test_cohort_readiness_report_warns_for_concentration_or_missingness(capsys) -> None:
    """Verdict should warn when cohort is strongly concentrated or too incomplete."""
    df = pd.DataFrame(
        {
            "sample_id": list(range(1, 11)),
            "type_slug": ["banker"] * 8 + ["adware", "rat"],
            "family_canonical": ["A"] * 8 + ["B", "C"],
            "android_package_name": [""] * 4 + ["pkg"] * 6,
            "vt_first_submission_date": ["2024-01-01"] * 10,
        }
    )

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"max_missing_package_pct": 10.0},
    )
    out = capsys.readouterr().out
    assert "Cohort is usable but remains concentration-heavy" in out
