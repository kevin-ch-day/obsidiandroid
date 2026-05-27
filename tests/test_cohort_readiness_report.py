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
            "analysis_lane": ["android_artifact"] * 5,
            "sample_label_kind": [
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
                "unclassified",
                "hash_like",
            ],
            "payload_target_platform": ["android"] * 5,
            "payload_target_source": ["artifact_platform"] * 5,
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
    assert "target surfaces" in out_lower
    assert "catalog semantics" in out_lower
    assert "top drift cohorts" in out_lower
    assert "top family" in out_lower
    assert "top 3 families" in out_lower
    assert "top 5 families" in out_lower
    assert "hash-like sample labels" in out_lower
    assert "(40.00%)" in out or "(40.0%)" in out
    assert "Excluded Families" in out
    assert "devixor, gigabud" in out
    assert "Family Target" in out
    assert "Type Target" in out
    assert "Raw→Type Alignment" in out


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
    df.attrs["cohort_gate_stats"] = {"governed_cohort_count": 100, "total_candidates": 160}

    cohort_readiness_report.print_cohort_readiness_report(df, gates={"max_missing_package_pct": 10.0})
    out = capsys.readouterr().out
    out_lower = out.lower()
    warnings = df.attrs.get("cohort_operational_warnings")
    assert "SQL governed cohort (reference)" in out
    assert "SQL Profile Scope" in out
    assert "cohort attrition" in out_lower
    assert "SQL Scope → Governed" in out
    assert "SQL Scope → Prepared" in out
    assert "100" in out
    assert "Final Samples" in out
    assert "50" in out
    assert "Prepared cohort is 50 rows" in out
    assert isinstance(warnings, list)
    assert any("prepared cohort retains only" in msg for msg in warnings)
    assert any("SQL governed cohort retains only" in msg for msg in warnings)

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


def test_cohort_readiness_report_warns_for_android_catalog_semantic_anomalies(capsys) -> None:
    """Readiness should surface Android cohort contamination and weak-label signals."""
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "banker", "banker"],
            "family_canonical": ["A", "B", "C"],
            "analysis_lane": ["android_artifact", "windows_targeting_non_windows", "android_artifact"],
            "sample_label_kind": ["family_or_common_name", "hash_like", "unclassified"],
            "payload_target_platform": ["android", "windows", "android"],
            "payload_target_source": ["artifact_platform", "vendor_consensus", "artifact_platform"],
            "vt_family_token": ["fam_a", "fam_b", "fam_c"],
            "family_label_raw": ["FamA", "WrongB", "Unknown"],
            "source_batch_label": ["batch_a", "batch_b", "batch_b"],
            "android_package_name": ["pkg.a", "pkg.b", "pkg.c"],
            "vt_first_submission_date": ["2024-01-01", "2024-01-01", "2024-01-01"],
        }
    )

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"max_missing_package_pct": 10.0},
    )
    out = capsys.readouterr().out.lower()
    warnings = df.attrs.get("cohort_operational_warnings")
    assert "non-android lane rows" in out
    assert "non-android target rows" in out
    assert "rows with vt family token" in out
    assert "weak labels with canonical family" in out
    assert "raw-vs-canonical family conflicts" in out
    assert "top drift cohorts" in out
    assert "families:" in out
    assert "source batches:" in out
    assert isinstance(warnings, list)
    assert any("non-android analysis_lane rows present" in msg for msg in warnings)
    assert any("non-android payload_target_platform rows present" in msg for msg in warnings)
    assert any("hash-like sample labels remain" in msg for msg in warnings)
    assert any("unclassified sample labels remain" in msg.lower() for msg in warnings)
    assert any("blank/generic family_label_raw despite vt_family_token" in msg for msg in warnings)
    assert any("weak sample labels despite canonical family authority" in msg for msg in warnings)
    assert any("raw family label differs from canonical family" in msg for msg in warnings)


def test_cohort_readiness_report_includes_sql_scope_catalog_preview(capsys) -> None:
    """Readiness should show SQL-scope semantics when the stage attached them."""
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "type_slug": ["banker", "banker"],
            "family_canonical": ["A", "B"],
            "analysis_lane": ["android_artifact", "android_artifact"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
            "payload_target_platform": ["android", "android"],
            "android_package_name": ["pkg.a", "pkg.b"],
            "vt_first_submission_date": ["2024-01-01", "2024-01-01"],
        }
    )
    df.attrs["catalog_semantics_sql_scope"] = {
        "analysis_lane_distribution": {"android_artifact": 9, "windows_targeting_non_windows": 3},
        "sample_label_kind_distribution": {"family_or_common_name": 6, "hash_like": 2},
        "payload_target_platform_distribution": {"android": 8, "windows": 1},
        "source_batch_label_distribution": {"batch_a": 7},
        "non_android_lane_rows": 3,
        "non_android_payload_target_rows": 1,
        "filename_label_rows": 1,
        "hash_like_label_rows": 2,
        "opaque_label_rows": 0,
        "unclassified_label_rows": 1,
        "vt_family_token_rows": 5,
        "blank_family_raw_with_vt_token_rows": 2,
        "weak_label_with_canonical_family_rows": 4,
        "raw_family_vs_canonical_conflict_rows": 1,
    }

    cohort_readiness_report.print_cohort_readiness_report(df, gates={"max_missing_package_pct": 10.0})
    out = capsys.readouterr().out
    out_lower = out.lower()
    warnings = df.attrs.get("cohort_operational_warnings")
    assert "sql scope catalog preview" in out_lower
    assert "SQL Top Analysis Lane" in out
    assert "SQL Top Sample Label Kind" in out
    assert "SQL Non-Android Lane Rows" in out
    assert "SQL Hash-like Sample Labels" in out
    assert isinstance(warnings, list)
    assert any("SQL scope contains more non-android analysis_lane drift" in msg for msg in warnings)
    assert any("SQL scope contains more weak-label rows with canonical family authority" in msg for msg in warnings)


def test_cohort_readiness_report_labels_limited_loader_preview(capsys) -> None:
    """Limited loader slices should not be presented as full SQL-scope semantics."""
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "type_slug": ["banker"],
            "family_canonical": ["A"],
            "analysis_lane": ["android_artifact"],
            "sample_label_kind": ["family_or_common_name"],
            "payload_target_platform": ["android"],
            "android_package_name": ["pkg.a"],
            "vt_first_submission_date": ["2024-01-01"],
        }
    )
    df.attrs["catalog_semantics_sql_scope"] = {
        "scope": "sql_limited_loader_slice",
        "analysis_lane_distribution": {"android_artifact": 5},
        "sample_label_kind_distribution": {"family_or_common_name": 5},
        "payload_target_platform_distribution": {"android": 5},
        "source_batch_label_distribution": {"batch_a": 5},
        "non_android_lane_rows": 0,
        "non_android_payload_target_rows": 0,
        "filename_label_rows": 0,
        "hash_like_label_rows": 1,
        "opaque_label_rows": 2,
        "unclassified_label_rows": 0,
        "vt_family_token_rows": 4,
        "blank_family_raw_with_vt_token_rows": 0,
        "weak_label_with_canonical_family_rows": 1,
        "raw_family_vs_canonical_conflict_rows": 2,
    }

    cohort_readiness_report.print_cohort_readiness_report(df, gates={"max_missing_package_pct": 10.0})
    out = capsys.readouterr().out
    out_lower = out.lower()
    assert "loader slice catalog preview" in out_lower
    assert "loader top analysis lane" in out_lower
    assert "loader raw-vs-canonical family conflicts" in out_lower


def test_cohort_readiness_report_marks_snapshot_lock_deferred_exclusions(capsys) -> None:
    """Locked cohorts should show requested family exclusions even when SQL application is deferred."""
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "type_slug": ["banker", "banker"],
            "family_canonical": ["A", "B"],
            "android_package_name": ["pkg.a", "pkg.b"],
            "vt_first_submission_date": ["2024-01-01", "2024-01-01"],
        }
    )
    df.attrs["requested_exclude_families"] = ("devixor", "gigabud")
    df.attrs["sql_exclude_families_applied"] = ()
    df.attrs["exclude_families_deferred_by_snapshot_lock"] = True
    df.attrs["configured_min_samples_per_family"] = 20
    df.attrs["min_samples_per_family_applied_in_sql"] = False
    df.attrs["min_samples_per_family_sql_value"] = None

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"exclude_unknown_type_slug": True, "min_samples_per_family": 20, "max_missing_package_pct": 5.0},
    )
    out = capsys.readouterr().out.lower()
    assert "excluded families" in out
    assert "devixor, gigabud (deferred by snapshot lock)" in out
    assert "20 (deferred by snapshot lock)" in out


def test_cohort_sql_scope_gate_summary_marks_low_support_as_deferred(capsys) -> None:
    cohort_readiness_report.print_cohort_sql_scope_gate_summary(
        {
            "type_slug": "all",
            "total_candidates": 2974,
            "excluded_unmapped_family": 455,
            "excluded_missing_sha256": 0,
            "excluded_unknown_type_slug": 128,
            "excluded_missing_package_name": 0,
            "excluded_low_support": 0,
            "governed_cohort_count": 2391,
            "min_samples_per_family_applied_in_sql": False,
        }
    )
    out = capsys.readouterr().out.lower()
    assert "excluded low support" in out
    assert "deferred by snapshot lock" in out


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
