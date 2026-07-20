"""Tests for headline ML terminal presentation helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from config import app_config
from obsidiandroid.evaluation import ml_comparator_summary, ml_terminal_presentation as ml_term


def test_should_defer_headline_training_terminal_respects_ablation(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    assert ml_term.should_defer_headline_training_terminal() is False


def test_ablation_feature_build_suppression_applies_before_grid_execution(monkeypatch) -> None:
    """Matrix construction must be quiet before the later training flag is enabled."""
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_FEATURE_BUILD_ACTIVE", True, raising=False)
    assert ml_term.should_suppress_ablation_feature_build_terminal() is True


def test_ablation_header_distinguishes_headline_and_ablation_vendor_contracts(capsys) -> None:
    ml_term.print_ablation_experiments_header(
        cohort_n=2848,
        headline_selected_vendors=0,
        ablation_requested_top_k=8,
    )
    out = capsys.readouterr().out
    assert "Cohort: 2,848 aligned samples" in out
    assert "Headline parsed-vendor fields" in out
    assert "disabled (0 selected)" in out
    assert "Ablation lexical-vendor arms" in out
    assert "up to 8 selected" in out


def test_format_population_terminal_lines_uses_runtime_counters(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_ALIGNED_ROWS_BEFORE_LOW_SUPPORT_FILTER", 5286, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_POST_LOW_SUPPORT_TRAINING_ROWS", 5235, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", 81, raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_HEADLINE_SPLIT_METADATA",
        {"train_sample_count": 2617, "test_sample_count": 2618},
        raising=False,
    )

    monkeypatch.setattr(app_config, "RUNTIME_COHORT_FAMILY_COUNT", 116, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_BENCHMARK_SUPPORT_EXCLUDED_FAMILY_COUNT", 35, raising=False)

    lines = ml_term.format_population_terminal_lines({})
    assert any("Governed cohort       : 5,286" in line for line in lines)
    assert any("Train / test split    : 2,617 / 2,618" in line for line in lines)
    assert any("Visible families      : 116" in line for line in lines)
    assert any("Support exclusions    : 51 rows / 35 families" in line for line in lines)


def test_compare_model_performance_prints_headline_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(app_config, "MODEL_RANK_PRIMARY_METRIC", "macro_f1_score")
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_QUIET_TRAINING", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "20260606T205123Z__cdaee7", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_SLOT", "expandedfam_exploratory", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PROFILE_ID", "android_malware_expanded_families", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "family_id", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ALIGNED_ROWS_BEFORE_LOW_SUPPORT_FILTER", 5286, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_POST_LOW_SUPPORT_TRAINING_ROWS", 5235, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", 81, raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_HEADLINE_SPLIT_METADATA",
        {"train_sample_count": 2617, "test_sample_count": 2618},
        raising=False,
    )
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", "/tmp/run-root", raising=False)

    results = {
        "logistic_regression": {
            "evaluation": {
                "accuracy": 0.953,
                "precision": 0.9533,
                "recall": 0.953,
                "f1_score": 0.9505,
                "macro_precision": 0.7707,
                "macro_recall": 0.7569,
                "macro_f1_score": 0.7453,
                "samples_tested": 2618,
                "num_classes": 81,
                "train_time": 172.81,
            },
            "predictions": {"1": "9", "2": "42"},
            "export_paths": {
                "model_path": "/tmp/run-root/models/logistic_regression/logistic_regression_classifier_model.joblib",
                "metadata_path": "/tmp/run-root/models/logistic_regression/logistic_regression_classifier_model_metadata.json",
            },
        },
        "random_forest": {
            "evaluation": {
                "accuracy": 0.9255,
                "precision": 0.9403,
                "recall": 0.9255,
                "f1_score": 0.9279,
                "macro_f1_score": 0.6819,
                "samples_tested": 2618,
                "num_classes": 81,
                "train_time": 43.92,
            },
            "predictions": {"1": "9"},
        },
    }

    summary_df = ml_comparator_summary.compare_model_performance(results)
    out = capsys.readouterr().out

    assert not summary_df.empty
    assert "MODEL EVALUATION SUMMARY" in out
    assert "Claim surface" in out and "Expanded-family exploratory cohort" in out
    assert "Macro-F1" in out and "0.7453" in out
    assert "MODEL LEADERBOARD" in out
    assert "logistic_regression" in out
    assert "COHORT / SPLIT SUMMARY" in out
    assert "Governed cohort" in out
    assert "EXPORTED ARTIFACTS" in out
    assert "Promoted model: logistic_regression" in out
    assert "Training runtime: 3m 36.73s" in out
    assert "Model artifacts" in out
    assert "Run diagnostics" in out
    assert "models/logistic_regression/logistic_regression_classifier_model.joblib" in out
    assert "Primary result" not in out
    assert "BEST MODEL METRICS" not in out


def test_ablation_interpretation_lines_use_primary_family_target() -> None:
    summary_df = pd.DataFrame(
        [
            {
                "label_target": "family_id",
                "experiment": "permissions_raw",
                "model": "logistic_regression",
                "macro_f1_score": 0.6890,
            },
            {
                "label_target": "family_id",
                "experiment": "full_fused",
                "model": "logistic_regression",
                "macro_f1_score": 0.7234,
            },
            {
                "label_target": "family_id",
                "experiment": "vendor_full",
                "model": "logistic_regression",
                "macro_f1_score": 0.8100,
            },
            {
                "label_target": "family_id",
                "experiment": "vendor_no_parsed_family",
                "model": "logistic_regression",
                "macro_f1_score": 0.6818,
            },
        ]
    )
    lines = ml_term.ablation_interpretation_lines(summary_df)
    assert any("Permissions (raw)" in line and "0.6890" in line for line in lines)
    assert any("Full fused" in line and "0.7234" in line for line in lines)
    assert any("Fused − permissions" in line and "+0.0344" in line for line in lines)
    assert any("Parsed-family contrast" in line and "+0.1282" in line for line in lines)
    assert any(line.startswith("Note") for line in lines)


def test_print_ablation_leaderboard_compact_uses_family_id_row(capsys) -> None:
    rows = [
        {
            "label_target": "type_slug",
            "best_feature_set": "full_fused",
            "best_macro_f1": 0.99,
            "permission_only": "—",
            "vendor_safe": "—",
            "full_fused": "full_fused / xgboost (0.9900)",
        },
        {
            "label_target": "family_id",
            "best_feature_set": "full_fused",
            "best_macro_f1": 0.7234,
            "permission_only": "permissions_raw / logistic_regression (0.6890)",
            "vendor_safe": "vendor_without_family_strings / logistic_regression (0.6818)",
            "full_fused": "full_fused / logistic_regression (0.7234)",
        },
    ]
    ml_term.print_ablation_leaderboard_compact(rows)
    out = capsys.readouterr().out
    assert "FAMILY CLASSIFICATION" in out
    assert "Best Macro-F1         : 0.7234" in out
    assert "Best configuration    : full_fused" in out
    assert "0.7234" in out
    assert "permissions_raw" in out


def test_format_run_relative_path_prefers_run_root(monkeypatch, tmp_path: Path) -> None:
    run_root = tmp_path / "expandedfam_exploratory"
    model_path = run_root / "models" / "logistic_regression" / "model.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)

    assert (
        ml_term.format_run_relative_path(model_path)
        == "models/logistic_regression/model.joblib"
    )
