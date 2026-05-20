"""Tests for cohort readiness summary formatting and policy highlights."""

from __future__ import annotations

import pandas as pd

import obsidiandroid.governance.cohort_readiness_report as cohort_readiness_report
from config import app_config


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


def test_cohort_readiness_report_notes_sql_vs_prepared_gap(capsys) -> None:
    """When cohort_gate_stats is present, explain SQL governed count vs prepared rows."""
    df = pd.DataFrame(
        {
            "sample_id": list(range(1, 51)),
            "type_slug": ["banker"] * 50,
            "family_canonical": ["Fam"] * 50,
            "android_package_name": ["p"] * 50,
            "vt_first_submission_date": ["2024-01-01"] * 50,
        }
    )
    df.attrs["cohort_gate_stats"] = {"governed_cohort_count": 100}

    cohort_readiness_report.print_cohort_readiness_report(df, gates={"max_missing_package_pct": 10.0})
    out = capsys.readouterr().out
    assert "SQL governed cohort (reference)" in out
    assert "100" in out
    assert "Final Samples" in out
    assert "50" in out
    assert "Prepared cohort is 50 rows" in out

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
    warnings = df.attrs.get("cohort_operational_warnings")
    assert isinstance(warnings, list)
    assert any("top family concentration" in msg for msg in warnings)
    assert any("banker share" in msg for msg in warnings)


def test_cohort_readiness_report_compact_limits_terminal_lists(monkeypatch, capsys) -> None:
    """Compact operator mode should trim long type/family terminal lists."""
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    df = pd.DataFrame(
        {
            "sample_id": list(range(1, 13)),
            "type_slug": ["banker", "adware", "rat", "spyware", "stealer", "sms-trojan"] * 2,
            "family_canonical": [f"fam_{i}" for i in range(12)],
            "android_package_name": ["pkg"] * 12,
            "vt_first_submission_date": ["2024-01-01"] * 12,
        }
    )

    cohort_readiness_report.print_cohort_readiness_report(df, gates={"max_missing_package_pct": 10.0})
    out = capsys.readouterr().out
    out_lower = out.lower()
    assert "top families (top 5)" in out_lower
    assert "additional families omitted from terminal output" in out_lower
    assert "additional type bucket(s)" in out_lower
