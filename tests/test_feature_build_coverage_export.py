"""Tests for feature build coverage export (no database)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.diagnostics.feature_build_coverage_export import (
    export_feature_build_coverage,
    export_feature_matrix_lineage_gate,
    gap_permission_bag_strata,
)


def test_export_feature_build_coverage_writes_files(tmp_path: Path) -> None:
    feat = pd.DataFrame({"x": [1.0, 2.0]}, index=[10, 20])
    feat.attrs["vendor_merge_sample_ids"] = [10, 20]
    cov_json, cov_csv = export_feature_build_coverage(
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


def test_export_disabled_returns_none(tmp_path: Path) -> None:
    feat = pd.DataFrame({"x": [1]}, index=[1])
    j, c = export_feature_build_coverage(
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
    cov_json, cov_csv = export_feature_build_coverage(
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


def test_export_feature_matrix_lineage_gate_passes_when_sets_match(tmp_path: Path) -> None:
    samples = pd.DataFrame({"sample_id": [1, 2]})
    feat = pd.DataFrame({"x": [1.0, 2.0]}, index=[1, 2])
    feat.attrs["feature_matrix_row_authority"] = "governed_cohort"
    out = export_feature_matrix_lineage_gate(
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


def test_gap_permission_bag_strata_on_missing_ids(tmp_path: Path) -> None:
    perm = pd.DataFrame(
        {
            "sample_id": [30, 40],
            "perm__android_permission_internet": [1, 0],
            "perm__total_count": [2, 0],
        }
    )
    s = gap_permission_bag_strata([30, 99], perm)
    assert s["gap_missing_sample_id_count"] == 2
    assert s["gap_missing_with_any_perm_bag_positive"] == 1

    feat = pd.DataFrame({"x": [1.0]}, index=[10])
    feat.attrs["vendor_merge_sample_ids"] = [10]
    _, _ = export_feature_build_coverage(
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
