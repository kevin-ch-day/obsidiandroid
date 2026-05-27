"""Tests for cohort foundation diagnostics export."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.diagnostics import cohort_foundation_export
from obsidiandroid.diagnostics import cohort_vocabulary


def test_export_cohort_foundation_bundle_writes_four_artifacts(tmp_path: Path) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a" * 64, "b" * 64],
            "family_canonical": ["f1", "f2"],
            "type_slug": ["trojan", "trojan"],
            "analysis_lane": ["android_artifact", "android_artifact"],
            "sample_label_kind": ["family_or_common_name", "unclassified"],
            "payload_target_platform": ["android", "android"],
            "payload_target_source": ["artifact_platform", "artifact_platform"],
            "vt_family_token": ["famtok", ""],
            "family_label_raw": ["", "NotF2"],
            "source_batch_label": ["batch_a", "batch_a"],
            "android_package_name": ["com.example", ""],
            "vt_first_submission_date": [
                pd.Timestamp("2020-01-01", tz="UTC"),
                pd.Timestamp("2020-01-02", tz="UTC"),
            ],
        }
    )
    gate_stats = {
        "total_candidates": 50,
        "governed_cohort_count": 2,
        "excluded_unmapped_family": 3,
        "excluded_unknown_type_slug": 0,
        "excluded_missing_sha256": 1,
        "excluded_missing_hash_registry": 0,
        "excluded_missing_package_name": 0,
        "excluded_low_support": 0,
    }
    profile = {
        "profile_id": "unit_cohort",
        "cohort_gates": {"min_samples_per_family": 3},
    }
    time_contract = {"start_utc": "2019-01-01", "end_utc": None, "require_effective_first_seen": True}
    paths = cohort_foundation_export.export_cohort_foundation_bundle(
        diagnostics_dir=diagnostics_dir,
        run_id="run_unit",
        profile_id="unit_cohort",
        profile=profile,
        gate_stats=gate_stats,
        samples_df=df,
        time_contract=time_contract,
        type_slug=None,
        min_samples_per_family_sql=None,
        configured_min_samples_per_family=3,
    )
    assert len(paths) == 4
    assert (diagnostics_dir / "cohort_foundation.json").exists()
    assert (diagnostics_dir / "cohort_foundation.md").exists()
    assert (diagnostics_dir / "cohort_foundation_counts.csv").exists()
    assert (diagnostics_dir / "cohort_foundation_schema.csv").exists()
    blob = json.loads((diagnostics_dir / "cohort_foundation.json").read_text(encoding="utf-8"))
    assert blob["run_id"] == "run_unit"
    assert blob[cohort_vocabulary.KEY_COHORT_SQL_SCOPE_ROW_COUNT] == 50
    assert blob[cohort_vocabulary.KEY_COHORT_PREPARED_ROW_COUNT] == 2
    assert blob["gate_stats"]["total_candidates"] == 50
    assert blob["loaded_dataframe"]["rows"] == 2
    assert blob["cohort_attrition"]["sql_scope_total"] == 50
    assert blob["cohort_attrition"]["governed_sql_total"] == 2
    assert blob["cohort_attrition"]["prepared_total"] == 2
    assert blob["catalog_semantics_summary"]["non_android_lane_rows"] == 0
    assert blob["catalog_semantics_summary"]["non_android_payload_target_rows"] == 0
    assert blob["catalog_semantics_summary"]["unclassified_label_rows"] == 1
    assert blob["catalog_semantics_summary"]["vt_family_token_rows"] == 1
    assert blob["catalog_semantics_summary"]["blank_family_raw_with_vt_token_rows"] == 1
    assert blob["catalog_semantics_summary"]["weak_label_with_canonical_family_rows"] == 1
    assert blob["catalog_semantics_summary"]["raw_family_vs_canonical_conflict_rows"] == 1
    assert blob["catalog_semantics_summary"]["top_drift_families"][0]["family_canonical"] == "f2"
    assert blob["catalog_semantics_summary"]["top_drift_families"][0]["issue_events"] >= 2
    assert blob["catalog_semantics_summary"]["top_drift_source_batches"][0]["source_batch_label"] == "batch_a"
    md_blob = (diagnostics_dir / "cohort_foundation.md").read_text(encoding="utf-8")
    assert "## Cohort attrition" in md_blob
    assert "## Catalog semantics" in md_blob
    assert "### Top analysis lanes" in md_blob
    assert "### Top sample-label kinds" in md_blob
    assert "### Top drift families" in md_blob


def test_interim_warning_when_upstream_expected_min_exceeded() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "sha256": ["c" * 64],
            "family_canonical": ["fam"],
            "type_slug": ["trojan"],
        }
    )
    profile = {
        "profile_id": "malicious_temporal_stability",
        "cohort_gates": {"upstream_expected_min_gate_total": 99999},
    }
    gate_stats = {"total_candidates": 10, "governed_cohort_count": 1}
    payload = cohort_foundation_export.build_cohort_foundation_payload(
        run_id="r1",
        profile_id="malicious_temporal_stability",
        profile=profile,
        gate_stats=gate_stats,
        samples_df=df,
        time_contract={},
        type_slug=None,
        min_samples_per_family_sql=None,
        configured_min_samples_per_family=3,
    )
    warns = payload.get("interim_rebuild_warnings") or []
    assert any("Erebus" in w for w in warns)


def test_counts_csv_includes_sql_scope_semantics_section(tmp_path: Path) -> None:
    """Counts CSV should include SQL-scope semantics metrics for quick diffing."""
    diagnostics_dir = tmp_path / "diagnostics"
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a" * 64, "b" * 64],
            "family_canonical": ["f1", "f2"],
            "type_slug": ["trojan", "trojan"],
            "analysis_lane": ["android_artifact", "android_artifact"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
            "payload_target_platform": ["android", "android"],
            "android_package_name": ["com.example.a", "com.example.b"],
            "vt_first_submission_date": [
                pd.Timestamp("2020-01-01", tz="UTC"),
                pd.Timestamp("2020-01-02", tz="UTC"),
            ],
        }
    )
    df.attrs["catalog_semantics_sql_scope"] = {
        "non_android_lane_rows": 3,
        "non_android_payload_target_rows": 1,
        "hash_like_label_rows": 2,
        "opaque_label_rows": 0,
        "unclassified_label_rows": 1,
        "filename_label_rows": 4,
        "vt_family_token_rows": 5,
        "blank_family_raw_with_vt_token_rows": 2,
        "weak_label_with_canonical_family_rows": 4,
        "raw_family_vs_canonical_conflict_rows": 1,
    }

    cohort_foundation_export.export_cohort_foundation_bundle(
        diagnostics_dir=diagnostics_dir,
        run_id="run_scope",
        profile_id="profile_scope",
        profile={"cohort_gates": {}},
        gate_stats={"total_candidates": 10, "governed_cohort_count": 8},
        samples_df=df,
        time_contract={},
        type_slug="trojan",
        min_samples_per_family_sql=3,
        configured_min_samples_per_family=3,
    )

    csv_text = (diagnostics_dir / "cohort_foundation_counts.csv").read_text(encoding="utf-8")
    assert "catalog_semantics_sql_scope,non_android_lane_rows,3" in csv_text
    assert "catalog_semantics_sql_scope,weak_label_with_canonical_family_rows,4" in csv_text
    assert "catalog_semantics_delta,non_android_lane_rows,3" in csv_text
    assert "catalog_semantics_delta,weak_label_with_canonical_family_rows,4" in csv_text


def test_compact_mode_skips_cohort_foundation_sidecar_csvs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", False, raising=False)
    diagnostics_dir = tmp_path / "diagnostics"
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "sha256": ["a" * 64],
            "family_canonical": ["f1"],
            "type_slug": ["trojan"],
        }
    )

    cohort_foundation_export.export_cohort_foundation_bundle(
        diagnostics_dir=diagnostics_dir,
        run_id="run_compact",
        profile_id="profile_compact",
        profile={"cohort_gates": {}},
        gate_stats={"total_candidates": 1, "governed_cohort_count": 1},
        samples_df=df,
        time_contract={},
        type_slug=None,
        min_samples_per_family_sql=None,
        configured_min_samples_per_family=3,
    )

    assert (diagnostics_dir / "cohort_foundation.json").exists()
    assert (diagnostics_dir / "cohort_foundation.md").exists()
    assert not (diagnostics_dir / "cohort_foundation_counts.csv").exists()
    assert not (diagnostics_dir / "cohort_foundation_schema.csv").exists()


def test_cohort_foundation_payload_and_markdown_include_semantics_delta(tmp_path: Path) -> None:
    """Foundation artifacts should show how much cleaner the prepared cohort is than SQL scope."""
    diagnostics_dir = tmp_path / "diagnostics"
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a" * 64, "b" * 64],
            "family_canonical": ["f1", "f2"],
            "type_slug": ["trojan", "trojan"],
            "analysis_lane": ["android_artifact", "android_artifact"],
            "sample_label_kind": ["family_or_common_name", "unclassified"],
            "payload_target_platform": ["android", "android"],
            "payload_target_source": ["artifact_platform", "artifact_platform"],
            "vt_family_token": ["tok1", ""],
            "family_label_raw": ["", "WrongF2"],
            "android_package_name": ["pkg.a", "pkg.b"],
            "vt_first_submission_date": [
                pd.Timestamp("2020-01-01", tz="UTC"),
                pd.Timestamp("2020-01-02", tz="UTC"),
            ],
        }
    )
    df.attrs["catalog_semantics_sql_scope"] = {
        "non_android_lane_rows": 3,
        "non_android_payload_target_rows": 1,
        "filename_label_rows": 2,
        "hash_like_label_rows": 2,
        "opaque_label_rows": 1,
        "unclassified_label_rows": 4,
        "blank_family_raw_with_vt_token_rows": 2,
        "weak_label_with_canonical_family_rows": 5,
        "raw_family_vs_canonical_conflict_rows": 4,
    }

    cohort_foundation_export.export_cohort_foundation_bundle(
        diagnostics_dir=diagnostics_dir,
        run_id="run_delta",
        profile_id="profile_delta",
        profile={"cohort_gates": {}},
        gate_stats={"total_candidates": 10, "governed_cohort_count": 8},
        samples_df=df,
        time_contract={},
        type_slug="trojan",
        min_samples_per_family_sql=3,
        configured_min_samples_per_family=3,
    )

    blob = json.loads((diagnostics_dir / "cohort_foundation.json").read_text(encoding="utf-8"))
    assert blob["catalog_semantics_delta"]["non_android_lane_rows"] == 3
    assert blob["catalog_semantics_delta"]["unclassified_label_rows"] == 3
    assert blob["catalog_semantics_delta"]["weak_label_with_canonical_family_rows"] == 4
    md_blob = (diagnostics_dir / "cohort_foundation.md").read_text(encoding="utf-8")
    assert "## Catalog semantics delta (SQL scope minus prepared cohort)" in md_blob
    assert "- non_android_lane_rows: 3" in md_blob
    assert "- weak_label_with_canonical_family_rows: 4" in md_blob


def test_cohort_foundation_reports_snapshot_lock_policy_deferral(tmp_path: Path) -> None:
    """Foundation bundle should record when SQL min-support/exclusions were deferred by lock."""
    diagnostics_dir = tmp_path / "diagnostics"
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "sha256": ["a" * 64],
            "family_canonical": ["f1"],
            "type_slug": ["trojan"],
            "analysis_lane": ["android_artifact"],
            "sample_label_kind": ["family_or_common_name"],
            "payload_target_platform": ["android"],
            "android_package_name": ["com.example.a"],
            "vt_first_submission_date": [pd.Timestamp("2020-01-01", tz="UTC")],
        }
    )
    df.attrs["exclude_families_deferred_by_snapshot_lock"] = True
    df.attrs["requested_exclude_families"] = ("devixor", "gigabud")

    cohort_foundation_export.export_cohort_foundation_bundle(
        diagnostics_dir=diagnostics_dir,
        run_id="run_policy",
        profile_id="profile_policy",
        profile={"cohort_gates": {"min_samples_per_family": 20}},
        gate_stats={"total_candidates": 10, "governed_cohort_count": 8},
        samples_df=df,
        time_contract={},
        type_slug=None,
        min_samples_per_family_sql=None,
        configured_min_samples_per_family=20,
    )

    blob = json.loads((diagnostics_dir / "cohort_foundation.json").read_text(encoding="utf-8"))
    assert blob["min_samples_per_family_applied_in_sql"] is False
    assert blob["min_samples_per_family_sql_value"] is None
    assert blob["exclude_families_deferred_by_snapshot_lock"] is True
    assert blob["requested_excluded_families"] == ["devixor", "gigabud"]
    md_blob = (diagnostics_dir / "cohort_foundation.md").read_text(encoding="utf-8")
    assert "## Cohort policy contract" in md_blob
    assert "- min_samples_per_family applied in SQL: `False`" in md_blob
    assert "- exclude_families_deferred_by_snapshot_lock: `True`" in md_blob
    assert "- requested_excluded_families: `devixor, gigabud`" in md_blob
