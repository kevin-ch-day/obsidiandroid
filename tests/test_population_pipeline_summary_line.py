"""Tests for one-line population summary used in manifests and logs."""

from __future__ import annotations

from obsidiandroid.orchestration.runtime_reporting import format_population_pipeline_summary_line
from config import app_config


def test_format_population_pipeline_summary_line_includes_class_count(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", 13, raising=False)
    mc = {
        "cohort_prepared_row_count": 1226,
        "fused_feature_rows": 1226,
        "aligned_supervised_rows": 1220,
        "post_low_support_training_rows": 712,
        "train_sample_count": 534,
        "test_sample_count": 178,
    }
    line = format_population_pipeline_summary_line(mc)
    assert "governed_cohort_n=1226" in line
    assert "fused_feature_matrix_n=1226" in line
    assert "train_n=534" in line
    assert "test_n=178" in line
    assert "distinct_family_labels_after_support=13" in line


def test_format_population_pipeline_summary_line_empty_without_core_counts() -> None:
    assert format_population_pipeline_summary_line({}) == ""
