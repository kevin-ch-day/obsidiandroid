"""Tests for feature build coverage export (no database)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.diagnostics import feature_build_coverage_export


def test_export_feature_build_coverage_writes_files(tmp_path: Path) -> None:
    feat = pd.DataFrame({"x": [1.0, 2.0]}, index=[10, 20])
    feat.attrs["vendor_merge_sample_ids"] = [10, 20]
    cov_json, cov_csv = feature_build_coverage_export.export_feature_build_coverage(
        cohort_sample_ids=[10, 20, 30],
        feature_df=feat,
        output_dir=tmp_path,
        run_id="run_test",
        enabled=True,
    )
    assert cov_json is not None and cov_csv is not None
    data = json.loads((tmp_path / "feature_build_coverage.latest.json").read_text(encoding="utf-8"))
    assert data["cohort_rows_missing_from_feature_matrix"] == 1
    missing = pd.read_csv(tmp_path / "cohort_missing_from_feature_matrix.latest.csv")
    assert list(missing["sample_id"]) == [30]


def test_export_feature_build_coverage_skips_empty_missing_csv(tmp_path: Path) -> None:
    feat = pd.DataFrame({"x": [1.0, 2.0]}, index=[10, 20])
    feat.attrs["vendor_merge_sample_ids"] = [10, 20]
    cov_json, cov_csv = feature_build_coverage_export.export_feature_build_coverage(
        cohort_sample_ids=[10, 20],
        feature_df=feat,
        output_dir=tmp_path,
        run_id="run_clean",
        enabled=True,
    )
    assert cov_json is not None
    assert cov_csv == tmp_path / "cohort_missing_from_feature_matrix_run_clean.csv"
    assert not cov_csv.exists()
    assert not (tmp_path / "cohort_missing_from_feature_matrix.latest.csv").exists()


def test_export_disabled_returns_none(tmp_path: Path) -> None:
    feat = pd.DataFrame({"x": [1]}, index=[1])
    j, c = feature_build_coverage_export.export_feature_build_coverage(
        cohort_sample_ids=[1],
        feature_df=feat,
        output_dir=tmp_path,
        run_id="x",
        enabled=False,
    )
    assert j is None and c is None


def test_export_feature_build_coverage_uses_sample_id_column_when_index_is_range(tmp_path: Path) -> None:
    """Coverage counts must not treat default RangeIndex as cohort sample ids."""
    feat = pd.DataFrame({"sample_id": [10, 20], "x": [1.0, 2.0]}, index=pd.RangeIndex(2))
    cov_json, cov_csv = feature_build_coverage_export.export_feature_build_coverage(
        cohort_sample_ids=[10, 20, 30],
        feature_df=feat,
        output_dir=tmp_path,
        run_id="run_range",
        enabled=True,
    )
    assert cov_json is not None and cov_csv is not None
    data = json.loads((tmp_path / "feature_build_coverage.latest.json").read_text(encoding="utf-8"))
    assert data["cohort_rows_missing_from_feature_matrix"] == 1
    assert data["feature_matrix_unique_row_count"] == 2


def test_export_feature_build_coverage_run_scoped_writes_named_and_global_latest_only(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("run_cov")
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    feat = pd.DataFrame({"x": [1.0, 2.0]}, index=[10, 20])
    feat.attrs["vendor_merge_sample_ids"] = [10, 20]

    cov_json, cov_csv = feature_build_coverage_export.export_feature_build_coverage(
        cohort_sample_ids=[10, 20, 30],
        feature_df=feat,
        output_dir=diagnostics_dir,
        run_id="run_cov",
        enabled=True,
    )

    assert cov_json == diagnostics_dir / "feature_build_coverage_run_cov.json"
    assert cov_csv == diagnostics_dir / "cohort_missing_from_feature_matrix_run_cov.csv"
    assert cov_json.is_file()
    assert cov_csv.is_file()
    assert not (diagnostics_dir / "feature_build_coverage.latest.json").exists()
    assert not (diagnostics_dir / "cohort_missing_from_feature_matrix.latest.csv").exists()
    assert (output_root / "diagnostics" / "feature_build_coverage.latest.json").is_file()
    assert (output_root / "diagnostics" / "cohort_missing_from_feature_matrix.latest.csv").is_file()


def test_export_feature_matrix_lineage_gate_passes_when_sets_match(tmp_path: Path) -> None:
    samples = pd.DataFrame({"sample_id": [1, 2]})
    feat = pd.DataFrame({"x": [1.0, 2.0]}, index=[1, 2])
    feat.attrs["feature_matrix_row_authority"] = "governed_cohort"
    out = feature_build_coverage_export.export_feature_matrix_lineage_gate(
        samples_df=samples,
        feature_df=feat,
        output_dir=tmp_path,
        run_id="gate_test",
        enabled=True,
    )
    assert out is not None
    data = json.loads((tmp_path / "feature_matrix_lineage_gate.latest.json").read_text(encoding="utf-8"))
    assert data["hard_equality_governed_fused_passes"] is True
    assert data["governed_distinct_sample_ids"] == 2
    assert data["fused_feature_matrix_unique_rows"] == 2


def test_export_feature_auxiliaries_run_scoped_use_global_latest_mirrors_only(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("run_aux")
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    feat = pd.DataFrame({"x": [1.0, 2.0]}, index=[1, 2])
    feat.attrs["feature_matrix_row_authority"] = "governed_cohort"
    samples = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["F1", "F2"],
            "type_slug": ["banker", "banker"],
        }
    )
    perms = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "perm__android_permission_internet": [1, 0],
            "perm__total_count": [2, 0],
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_VENDOR_MERGE_SAMPLE_IDS", [1, 2], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PERMISSION_FRAME_SAMPLE_IDS", [1, 2], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_FUSED_MATRIX_SAMPLE_IDS", [1, 2], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ALIGNED_SUPERVISED_SAMPLE_IDS", [1, 2], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_POST_FAMILY_SUPPORT_TRAINABLE_SAMPLE_IDS", [1], raising=False)

    csv_path, json_path = feature_build_coverage_export.export_feature_modality_coverage_audit(
        cohort_sample_ids=[1, 2],
        samples_df=samples,
        feature_df=feat,
        output_dir=diagnostics_dir,
        run_id="run_aux",
        permission_features_df=perms,
        enabled=True,
    )
    gate_path = feature_build_coverage_export.export_feature_matrix_lineage_gate(
        samples_df=samples,
        feature_df=feat,
        output_dir=diagnostics_dir,
        run_id="run_aux",
        enabled=True,
    )
    lineage_path = feature_build_coverage_export.export_sample_stage_lineage_audit(
        cohort_sample_ids=[1, 2],
        output_dir=diagnostics_dir,
        run_id="run_aux",
        enabled=True,
    )

    assert csv_path == diagnostics_dir / "feature_modality_coverage_audit_run_aux.csv"
    assert json_path == diagnostics_dir / "feature_modality_coverage_summary_run_aux.json"
    assert gate_path == diagnostics_dir / "feature_matrix_lineage_gate_run_aux.json"
    assert lineage_path == diagnostics_dir / "sample_stage_lineage_run_aux.csv"
    for name in (
        "feature_modality_coverage_audit.latest.csv",
        "feature_modality_coverage_summary.latest.json",
        "feature_matrix_lineage_gate.latest.json",
        "sample_stage_lineage.latest.csv",
    ):
        assert not (diagnostics_dir / name).exists()
        assert (output_root / "diagnostics" / name).is_file()


def test_export_sample_stage_lineage_defaults_off_in_compact_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_BUILD_COVERAGE_EXPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", False, raising=False)
    out = feature_build_coverage_export.export_sample_stage_lineage_audit(
        cohort_sample_ids=[1, 2],
        output_dir=tmp_path,
        run_id="compact",
        enabled=None,
    )
    assert out is None
    assert not (tmp_path / "sample_stage_lineage_compact.csv").exists()


def test_gap_permission_bag_strata_on_missing_ids(tmp_path: Path) -> None:
    perm = pd.DataFrame(
        {
            "sample_id": [30, 40],
            "perm__android_permission_internet": [1, 0],
            "perm__total_count": [2, 0],
        }
    )
    s = feature_build_coverage_export.gap_permission_bag_strata([30, 99], perm)
    assert s["gap_missing_sample_id_count"] == 2
    assert s["gap_missing_with_any_perm_bag_positive"] == 1

    feat = pd.DataFrame({"x": [1.0]}, index=[10])
    feat.attrs["vendor_merge_sample_ids"] = [10]
    _, _ = feature_build_coverage_export.export_feature_build_coverage(
        cohort_sample_ids=[10, 30],
        feature_df=feat,
        output_dir=tmp_path,
        run_id="perm_gap",
        enabled=True,
        permission_features_df=perm,
    )
    data = json.loads((tmp_path / "feature_build_coverage.latest.json").read_text(encoding="utf-8"))
    assert data["cohort_rows_missing_from_feature_matrix"] == 1
    assert data["gap_missing_with_any_perm_bag_positive"] == 1
