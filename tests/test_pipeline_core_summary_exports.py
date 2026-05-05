"""Tests for model-summary export behavior in pipeline_core."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.modeling import pipeline_core


def test_summarize_models_exports_csv_and_skips_excel_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Summary export should default to CSV and avoid hot-path Excel writes."""
    run_id = "20260302T000000Z__testrun"
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_DIAGNOSTICS_DIR",
        str(output_root / "runs" / run_id / "diagnostics"),
        raising=False,
    )
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_CSV_EXPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(
        pipeline_core.comparator,
        "compare_model_performance",
        lambda _results: pd.DataFrame(
            [
                {"Model": "logistic_regression", "Macro F1-Score": 0.80},
                {"Model": "random_forest", "Macro F1-Score": 0.75},
            ]
        ),
    )
    monkeypatch.setattr(
        pipeline_core.inspector,
        "generate_classification_summary",
        lambda **_kwargs: None,
    )

    excel_calls = {"count": 0}

    def _fake_export_dataframe_to_excel(**_kwargs):
        excel_calls["count"] += 1
        return "unused.xlsx"

    monkeypatch.setattr(pipeline_core.em, "export_dataframe_to_excel", _fake_export_dataframe_to_excel)

    results = {
        "logistic_regression": {
            "evaluation": {
                "accuracy": 0.90,
                "macro_f1_score": 0.80,
                "confusion_matrix_path": "cm.png",
            }
        },
        "random_forest": {
            "evaluation": {
                "accuracy": 0.88,
                "macro_f1_score": 0.75,
                "confusion_matrix_path": "cm2.png",
            }
        },
    }

    top_model = pipeline_core.summarize_models(results)

    assert top_model == "logistic_regression"
    assert excel_calls["count"] == 0
    summary_csv = output_root / "runs" / run_id / "diagnostics" / f"model_comparison_summary_{run_id}.csv"
    assert summary_csv.exists()


def test_summarize_models_paper_mode_filters_balanced_rf(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Paper-mode summary should keep only RF/XGB/LR rows."""
    run_id = "20260302T000000Z__paper"
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_DIAGNOSTICS_DIR",
        str(output_root / "runs" / run_id / "diagnostics"),
        raising=False,
    )
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_CSV_EXPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(
        pipeline_core.comparator,
        "compare_model_performance",
        lambda _results: pd.DataFrame(
            [
                {"Model": "balanced_random_forest", "Macro F1-Score": 0.95},
                {"Model": "random_forest", "Macro F1-Score": 0.90},
                {"Model": "xgboost", "Macro F1-Score": 0.89},
                {"Model": "logistic_regression", "Macro F1-Score": 0.88},
            ]
        ),
    )
    monkeypatch.setattr(
        pipeline_core.inspector,
        "generate_classification_summary",
        lambda **_kwargs: None,
    )

    results = {
        "balanced_random_forest": {"evaluation": {"accuracy": 0.95, "macro_f1_score": 0.95}},
        "random_forest": {"evaluation": {"accuracy": 0.90, "macro_f1_score": 0.90}},
        "xgboost": {"evaluation": {"accuracy": 0.89, "macro_f1_score": 0.89}},
        "logistic_regression": {"evaluation": {"accuracy": 0.88, "macro_f1_score": 0.88}},
    }

    top_model = pipeline_core.summarize_models(results)

    assert top_model == "random_forest"
    summary_csv = output_root / "runs" / run_id / "diagnostics" / f"model_comparison_summary_{run_id}.csv"
    exported = pd.read_csv(summary_csv)
    assert set(exported["Model"].tolist()) == {"random_forest", "xgboost", "logistic_regression"}


def test_run_classifier_pipeline_exports_leakage_pruning_audit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Leakage pruning should emit a reason-coded audit artifact for dropped columns."""
    run_id = "20260321T000000Z__audit"
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 1, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_AGGRESSIVE_LEAKAGE_PRUNING", False, raising=False)
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "print_family_distribution",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "apply_min_family_support",
        lambda **kwargs: (kwargs["features_df"], kwargs["labels_df"], 0, 0, []),
    )
    monkeypatch.setattr(
        pipeline_core,
        "train_models",
        lambda *_args, **_kwargs: (
            {"logistic_regression": {"evaluation": {"accuracy": 1.0}}},
            [],
        ),
    )
    monkeypatch.setattr(pipeline_core, "summarize_models", lambda _results: "logistic_regression")
    monkeypatch.setattr(pipeline_core, "promote_default_model", lambda *_args, **_kwargs: None)

    features_df = pd.DataFrame(
        {
            "sample_id": ["101", "102"],
            "signal": [1.0, 2.0],
        },
        index=["101", "102"],
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [101, 102],
            "family_id": [44, 51],
            "family_canonical": ["Irata", "Applite"],
        }
    )

    result = pipeline_core.run_classifier_pipeline(
        features_df=features_df,
        samples_df=samples_df,
        save_model=False,
        models=["logistic_regression"],
    )

    assert "logistic_regression" in result
    audit_path = diagnostics_dir / f"leakage_pruning_audit_{run_id}.csv"
    assert audit_path.exists()
    audit_df = pd.read_csv(audit_path)
    assert "reason_code" in audit_df.columns
    names = audit_df["column_name"].tolist()
    assert "sample_id" in names
    assert "__summary__" in names
