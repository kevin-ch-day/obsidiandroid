"""Tests for feature build coverage export (no database)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.diagnostics.feature_build_coverage_export import export_feature_build_coverage


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
