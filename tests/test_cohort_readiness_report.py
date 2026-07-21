"""Tests for cohort readiness summary formatting and policy highlights."""

from __future__ import annotations

import pandas as pd
import pytest

import obsidiandroid.governance.cohort_readiness_report as cohort_readiness_report
from obsidiandroid.governance.support_floor_policy import resolve_support_floor_mode
from config import app_config

pytestmark = pytest.mark.contract


def test_catalog_quality_metrics_do_not_count_known_aliases_as_conflicts() -> None:
    """Readiness surfaces must use the same alias semantics as cohort gates."""
    df = pd.DataFrame(
        {
            "family_label_raw": ["Wroba", "BlackLoan", "SpyC23"],
            "family_canonical": ["RoamingMantis", "SpyLoan", "HiddenAd"],
        }
    )

    quality = cohort_readiness_report._build_catalog_quality_metrics(  # pylint: disable=protected-access
        samples_df=df,
        total=len(df),
        missing_pkg=0.0,
        missing_vt_time=0.0,
        unmapped=0,
    )

    assert quality["family_conflict_rows"] == 1


def test_cohort_readiness_report_prints_percentages_and_concentration(capsys) -> None:
    """Summary should use the compact benchmark structure."""
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

    assert "Cohort Benchmark Summary" in out
    assert "cohort funnel" in out_lower
    assert "benchmark targets" in out_lower
    assert "cohort composition" in out_lower
    assert "quality / risk flags" in out_lower
    assert "top types" in out_lower
    assert "top families" in out_lower
    assert "concentration" in out_lower
    assert "label readiness" in out_lower
    assert "(40.00%)" in out or "(40.0%)" in out
    assert "Family target" in out
    assert "Type target" in out
    assert "Excluded type_slug values" in out


def test_cohort_readiness_report_notes_sql_vs_prepared_gap(capsys) -> None:
    """When cohort_gate_stats is present, funnel should reflect SQL vs prepared counts."""
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
    warnings = df.attrs.get("cohort_operational_warnings")
    assert "Cohort funnel" in out
    assert "160 SQL" in out
    assert "100 governed" in out
    assert "50 prepared" in out
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
    """Risk block should surface Android contamination and weak-label signals compactly."""
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
    assert "quality / risk flags" in out
    assert "label readiness" in out
    assert "family conflicts" in out
    assert "top data-quality pockets" in out.lower()
    assert "families" in out
    assert isinstance(warnings, list)
    assert any("non-android analysis_lane rows present" in msg for msg in warnings)
    assert any("non-android payload_target_platform rows present" in msg for msg in warnings)
    assert any("hash-like sample labels remain" in msg for msg in warnings)
    assert any("unclassified sample labels remain" in msg.lower() for msg in warnings)
    assert any("blank/generic family_label_raw despite vt_family_token" in msg for msg in warnings)
    assert any("weak sample labels despite canonical family authority" in msg for msg in warnings)
    assert any("raw family label differs from canonical family" in msg for msg in warnings)


def test_cohort_readiness_report_distinguishes_visible_benchmark_and_modeled_family_counts(
    capsys,
) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "type_slug": ["banker", "banker", "adware", "rat", "rat"],
            "family_canonical": ["A", "A", "B", "C", "D"],
            "android_package_name": ["pkg.a", "pkg.b", "pkg.c", "pkg.d", "pkg.e"],
            "vt_first_submission_date": ["2024-01-01"] * 5,
        }
    )
    df.attrs["support_floor_mode"] = "diagnostic_only"

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"min_samples_per_family": 20, "max_missing_package_pct": 10.0},
    )
    out = capsys.readouterr().out
    assert "Represented taxonomy" in out
    assert "4 known families" in out
    assert "4 observed family labels" in out
    assert "Family target" in out
    assert "benchmark-eligible classes" in out
    assert "Diagnostic candidate family classes" in out
    assert "4 before label-authority filtering" in out


def test_compact_top_drift_groups_dedupes_same_sample_pocket(capsys, monkeypatch) -> None:
    """Compact curation queue should not report the same sample pocket twice."""
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_canonical": ["SpyNote", "SpyNote", "SpyLoan", "Octo"],
            "type_slug": ["rat", "rat", "spyware", "banker"],
            "analysis_lane": ["android_artifact"] * 4,
            "sample_label_kind": ["filename", "hash_like", "family_or_common_name", "family_or_common_name"],
            "payload_target_platform": ["android"] * 4,
            "vt_family_token": ["", "", "", ""],
            "family_label_raw": ["SpyNote", "SpyNote", "BlackLoan", "ExobotCompact.D/Octo"],
            "source_batch_label": ["", "", "", ""],
            "android_package_name": ["pkg.a", "pkg.b", "pkg.c", "pkg.d"],
            "vt_first_submission_date": ["2024-01-01"] * 4,
        }
    )

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"max_missing_package_pct": 10.0},
    )
    out = capsys.readouterr().out
    assert "top data-quality pockets" in out.lower()
    assert "families" in out and "SpyNote" in out
    assert "types rat" not in out.lower()
    assert "source batches <blank>" not in out.lower()


def test_cohort_readiness_report_includes_sql_scope_catalog_preview(capsys) -> None:
    """Detailed SQL-scope preview stays out of terminal even when attached."""
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
    warnings = df.attrs.get("cohort_operational_warnings")
    assert "SQL Scope Catalog Preview" not in out
    assert "Loader Slice Catalog Preview" not in out
    assert isinstance(warnings, list)
    assert any("SQL scope contains more non-android analysis_lane drift" in msg for msg in warnings)
    assert any("SQL scope contains more weak-label rows with canonical family authority" in msg for msg in warnings)


def test_cohort_readiness_report_labels_limited_loader_preview(capsys) -> None:
    """Limited loader slice details should not appear in the compact terminal block."""
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
    assert "Loader Slice Catalog Preview" not in out
    assert "loader top analysis lane" not in out.lower()


def test_cohort_readiness_report_marks_snapshot_lock_deferred_exclusions(capsys) -> None:
    """Policy block should stay concise under snapshot-lock deferred exclusions."""
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
    assert "policy" in out
    assert "family support rule" in out
    assert "excluded type_slug values" in out


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
    assert "diagnostic only / not applied" in out


def test_cohort_readiness_report_marks_diagnostic_only_support_floor(capsys) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "type_slug": ["banker", "banker", "rat", "spyware"],
            "family_canonical": ["fam_a", "fam_a", "fam_b", "fam_c"],
            "android_package_name": ["pkg.a", "pkg.b", "pkg.c", "pkg.d"],
            "vt_first_submission_date": ["2024-01-01"] * 4,
        }
    )
    df.attrs["configured_min_samples_per_family"] = None
    df.attrs["diagnostic_min_samples_per_family"] = 3
    df.attrs["support_floor_mode"] = "diagnostic_only"
    df.attrs["min_samples_per_family_applied_in_sql"] = False
    df.attrs["min_samples_per_family_sql_value"] = None

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"support_floor_mode": "diagnostic_only", "max_missing_package_pct": 10.0},
    )
    out = capsys.readouterr().out
    out_lower = out.lower()
    assert "policy" in out_lower
    assert "below-threshold families" in out_lower
    assert "family support rule" not in out_lower
    assert "trainable@20" not in out_lower


def test_cohort_readiness_report_marks_benchmark_eligibility_support_floor(capsys) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "type_slug": ["banker", "banker", "banker", "rat", "spyware"],
            "family_canonical": ["fam_a", "fam_a", "fam_a", "fam_b", ""],
            "family_id": [1, 1, 1, 2, None],
            "category_primary": ["trojan", "trojan", "trojan", "trojan", ""],
            "category_subtype": ["banker", "banker", "banker", "rat", "trojan"],
            "sample_label_kind": ["family_or_common_name"] * 5,
            "android_package_name": ["pkg.a", "pkg.b", "pkg.c", "pkg.d", "pkg.e"],
            "vt_first_submission_date": ["2024-01-01"] * 5,
        }
    )
    df.attrs["configured_min_samples_per_family"] = 3
    df.attrs["diagnostic_min_samples_per_family"] = 3
    df.attrs["support_floor_mode"] = "benchmark_eligibility"
    df.attrs["min_samples_per_family_applied_in_sql"] = False
    df.attrs["min_samples_per_family_sql_value"] = None

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={
            "support_floor_mode": "benchmark_eligibility",
            "min_samples_per_family": 3,
            "max_missing_package_pct": 10.0,
        },
    )
    out = capsys.readouterr().out.lower()
    assert "family support rule" in out
    assert "benchmark trainable" in out
    assert "diagnostic-only rows" in out


def test_resolve_support_floor_mode_accepts_samples_df_compatibility() -> None:
    df = pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"]})
    df.attrs["support_floor_mode"] = "benchmark_eligibility"

    mode = resolve_support_floor_mode({}, samples_df=df)

    assert mode == "benchmark_eligibility"


def test_cohort_readiness_report_handles_samples_df_support_floor_compatibility(capsys) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5, 6],
            "type_slug": ["banker", "banker", "banker", "banker", "rat", "rat"],
            "family_canonical": ["fam_a", "fam_a", "fam_a", "fam_b", "fam_c", "fam_d"],
            "family_id": [1, 1, 1, 2, 3, 4],
            "category_primary": ["trojan"] * 6,
            "category_subtype": ["banker", "banker", "banker", "banker", "rat", "rat"],
            "sample_label_kind": ["family_or_common_name"] * 6,
            "android_package_name": ["pkg.a", "pkg.b", "pkg.c", "pkg.d", "pkg.e", "pkg.f"],
            "vt_first_submission_date": ["2024-01-01"] * 6,
        }
    )
    df.attrs["support_floor_mode"] = "benchmark_eligibility"
    df.attrs["configured_min_samples_per_family"] = 3
    df.attrs["diagnostic_min_samples_per_family"] = 3
    df.attrs["min_samples_per_family_applied_in_sql"] = False
    df.attrs["min_samples_per_family_sql_value"] = None
    df.attrs["cohort_gate_stats"] = {"governed_cohort_count": 6, "total_candidates": 6}

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"min_samples_per_family": 3, "max_missing_package_pct": 10.0},
    )
    out = capsys.readouterr().out

    assert "Cohort Benchmark Summary" in out
    assert "Benchmark trainable" in out
    assert "Family target" in out


def test_cohort_readiness_report_compact_limits_terminal_lists(monkeypatch, capsys) -> None:
    """Compact benchmark summary should avoid verbose family ladder blocks."""
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
    assert "top families (top 5)" not in out_lower
    assert "additional families omitted from terminal output" not in out_lower
    assert "additional type bucket(s)" not in out_lower
    assert "cohort composition" in out_lower


def test_cohort_readiness_report_compact_dedupes_overlapping_drift_groups(monkeypatch, capsys) -> None:
    """Compact curation queue should avoid rendering the same row pocket twice."""
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "type_slug": ["rat", "rat", "rat", "banker", "banker"],
            "family_canonical": ["SpyNote", "SpyNote", "SpyNote", "Octo", "Octo"],
            "analysis_lane": ["android_artifact"] * 5,
            "sample_label_kind": [
                "opaque_string",
                "opaque_string",
                "filename",
                "family_or_common_name",
                "family_or_common_name",
            ],
            "payload_target_platform": ["android"] * 5,
            "payload_target_source": ["artifact_platform"] * 5,
            "vt_family_token": ["spy", "spy", "spy", "octo", "octo"],
            "family_label_raw": ["spynote", "spynote", "spynote", "octo", "octo"],
            "source_batch_label": ["", "", "", "batch_a", "batch_a"],
            "android_package_name": [f"pkg.{i}" for i in range(5)],
            "vt_first_submission_date": ["2024-01-01"] * 5,
        }
    )

    cohort_readiness_report.print_cohort_readiness_report(df, gates={"max_missing_package_pct": 10.0})
    out = capsys.readouterr().out
    assert "1. families: SpyNote" in out
    assert out.count("families: SpyNote") == 1
    assert "types rat" not in out
    assert "source batches <blank>" not in out


def test_cohort_readiness_report_attrs_metadata_dict_not_truthy(capsys) -> None:
    """Evidence-mode metadata dicts with resolved_value=False must not enable publication labels."""
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["Godfather", "FluBot"],
            "type_slug": ["banker", "banker"],
            "android_package_name": ["a", "b"],
            "vt_first_submission_date": ["2024-01-01", "2024-01-02"],
        }
    )
    df.attrs["evidence_mode"] = {"resolved_value": False, "source": "profile"}
    df.attrs["publication_ready_mode"] = {"resolved_value": False, "source": "profile"}

    cohort_readiness_report.print_cohort_readiness_report(
        df,
        gates={"max_missing_package_pct": 10.0},
    )
    out = capsys.readouterr().out
    assert "Locked Publication Cohort Summary" not in out
    assert "Locked publication cohort" not in out
