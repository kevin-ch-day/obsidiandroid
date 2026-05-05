"""Tests for feature-column survival export."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics import feature_column_survival_export
from config import app_config


def test_infer_feature_modality(tmp_path: Path) -> None:
    attrs = {"vendor_feature_column_names": ["v_score"]}
    assert feature_column_survival_export.infer_feature_modality("v_score", attrs) == "vendor"
    assert feature_column_survival_export.infer_feature_modality("perm__x", {}) == "permission"
    assert feature_column_survival_export.infer_feature_modality("perm_grp__y", {}) == "grouped_permission"
    assert feature_column_survival_export.infer_feature_modality("meta__z", {}) == "metadata"


def test_export_feature_column_survival_matrix_writes_csv(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_FEATURE_NONZERO_COHORT_FUSED", {"a": 5, "b": 0}, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_FEATURE_NONZERO_AFTER_ALIGN", {"a": 5, "b": 0}, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_FEATURE_NONZERO_AFTER_FAMILY_SUPPORT", {"a": 4, "b": 0}, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_FEATURE_NONZERO_AFTER_LOW_INFORMATION", {"a": 4}, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_FEATURE_NONZERO_FINAL_TRAINING", {"a": 4}, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_LOW_INFORMATION_PRUNED_COLUMNS", ["b"], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", [], raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_COLUMN_SURVIVAL_EXPORT", True, raising=False)
    out = feature_column_survival_export.export_feature_column_survival_matrix(
        diagnostics_dir=tmp_path,
        run_id="u1",
        feature_attrs={"vendor_feature_column_names": []},
        enabled=True,
    )
    assert out is not None
    df = pd.read_csv(tmp_path / "feature_column_survival.latest.csv")
    assert set(df["feature_name"]) == {"a", "b"}
    dropped = df.loc[df["feature_name"] == "b", "dropped_by_low_information_prune"].iloc[0]
    assert bool(dropped) is True


def test_nonzero_counts_for_columns_skips_sample_id_column() -> None:
    df = pd.DataFrame({"sample_id": [1, 2], "perm__x": [0, 1]})
    got = feature_column_survival_export.nonzero_counts_for_columns(df)
    assert "sample_id" not in got
    assert got.get("perm__x") == 1
