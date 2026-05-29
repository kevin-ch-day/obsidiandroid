"""Tests for evaluation label projection and confusion-matrix labeling."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from config import app_config
from obsidiandroid.evaluation import ml_eval_engine
from obsidiandroid.evaluation import ml_report_builder


class _DummyModel:
    """Simple deterministic model stub for evaluator tests."""

    def __init__(self, predictions: np.ndarray) -> None:
        self._predictions = predictions

    def predict(self, _x):  # type: ignore[no-untyped-def]
        return self._predictions


class _DummyRemappedModel(_DummyModel):
    """Model stub carrying a local-to-global prediction remap."""

    def __init__(self, predictions: np.ndarray, remap: list[int]) -> None:
        super().__init__(predictions)
        self._obsidiandroid_prediction_index_remap = remap


def test_evaluation_projects_family_ids_to_canonical_names(monkeypatch):
    label_encoder = LabelEncoder()
    label_encoder.fit([43, 44])

    y_test = np.array([0, 1, 0, 1])
    y_pred = np.array([0, 1, 1, 1])
    x_test = np.zeros((4, 2))

    runtime_meta = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_id": [43, 44],
            "family_canonical": ["Devixor", "Gigabud"],
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)

    captured = {}

    def _capture_cm(**kwargs):
        captured["class_labels"] = list(kwargs["class_labels"])
        return "cm.png"

    monkeypatch.setattr(ml_eval_engine.export_manager, "export_confusion_matrix", _capture_cm)

    result = ml_eval_engine.evaluate_model_performance(
        model=_DummyModel(y_pred),
        X_test=x_test,
        y_test=y_test,
        label_encoder=label_encoder,
        model_name="random_forest",
        verbose=False,
    )

    assert result["class_labels"] == ["Devixor", "Gigabud"]
    assert captured["class_labels"] == ["Devixor", "Gigabud"]


def test_evaluation_keeps_labels_when_no_runtime_family_map(monkeypatch):
    label_encoder = LabelEncoder()
    label_encoder.fit([43, 44])

    y_test = np.array([0, 1])
    y_pred = np.array([0, 1])
    x_test = np.zeros((2, 1))

    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", pd.DataFrame(), raising=False)
    monkeypatch.setattr(
        ml_eval_engine.export_manager,
        "export_confusion_matrix",
        lambda **kwargs: "cm.png",
    )

    result = ml_eval_engine.evaluate_model_performance(
        model=_DummyModel(y_pred),
        X_test=x_test,
        y_test=y_test,
        label_encoder=label_encoder,
        model_name="xgboost",
        verbose=False,
    )

    assert result["class_labels"] == [43, 44]


def test_evaluation_passes_macro_metrics_to_console_summary(monkeypatch):
    label_encoder = LabelEncoder()
    label_encoder.fit([10, 20, 30])

    y_test = np.array([0, 1, 2, 0, 1, 2])
    y_pred = np.array([0, 0, 0, 0, 1, 2])
    x_test = np.zeros((6, 1))

    monkeypatch.setattr(
        ml_eval_engine.export_manager,
        "export_confusion_matrix",
        lambda **kwargs: "cm.png",
    )

    captured = {}

    def _capture_summary(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(ml_eval_engine.ml_report_builder, "print_evaluation_summary", _capture_summary)

    result = ml_eval_engine.evaluate_model_performance(
        model=_DummyModel(y_pred),
        X_test=x_test,
        y_test=y_test,
        label_encoder=label_encoder,
        model_name="random_forest",
        verbose=True,
    )

    assert "macro_prec" in captured
    assert "macro_recall" in captured
    assert "macro_f1" in captured
    assert captured["macro_f1"] == result["macro_f1_score"]


def test_evaluation_remaps_model_local_prediction_indices_before_scoring(monkeypatch):
    label_encoder = LabelEncoder()
    label_encoder.fit([10, 11, 12, 13])

    y_test = np.array([0, 2, 3, 0])
    # Model predicts in local contiguous fit space {0,1,2}; evaluator should remap -> {0,2,3}.
    y_pred_local = np.array([0, 1, 2, 0])
    x_test = np.zeros((4, 1))

    monkeypatch.setattr(
        ml_eval_engine.export_manager,
        "export_confusion_matrix",
        lambda **kwargs: "cm.png",
    )

    result = ml_eval_engine.evaluate_model_performance(
        model=_DummyRemappedModel(y_pred_local, [0, 2, 3]),
        X_test=x_test,
        y_test=y_test,
        label_encoder=label_encoder,
        model_name="xgboost",
        verbose=False,
    )

    assert result["accuracy"] == 1.0
    assert result["class_labels"] == [10, 12, 13]
    assert list(result["y_pred"]) == [10, 12, 13, 10]


def test_display_post_training_metrics_ablation_quiet_mode_accumulates_rows(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_QUIET_TRAINING", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_ABLATION_PROGRESS_ROWS",
        [],
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_ABLATION_FEATURE_SET_NAME",
        "full_fused",
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_ABLATION_LABEL_TARGET_SLUG",
        "family_canonical_default",
        raising=False,
    )

    printed: list[str] = []
    monkeypatch.setattr(
        ml_eval_engine.du,
        "print_info",
        lambda msg, *_args, **_kwargs: printed.append(str(msg)),
    )

    ml_eval_engine.display_post_training_metrics(
        "xgboost",
        result={},
        evaluation={
            "accuracy": 0.95,
            "macro_f1_score": 0.91,
            "f1_score": 0.94,
            "train_time": 12.34,
        },
        features_df=None,
    )

    assert printed == []
    assert getattr(app_config, "RUNTIME_ABLATION_PROGRESS_ROWS") == [
        {
            "feature_set": "full_fused",
            "label_target": "family_canonical_default",
            "model": "xgboost",
            "accuracy": 0.95,
            "macro_f1_score": 0.91,
            "f1_score": 0.94,
            "train_time": 12.34,
        }
    ]


def test_print_evaluation_summary_surfaces_macro_metrics_and_uses_macro_f1_for_tier(
    monkeypatch, capsys
):
    df = pd.DataFrame(
        [
            {
                "Rank": 1,
                "Family": "Irata",
                "Precision": 0.90,
                "Recall": 0.80,
                "F1-Score": 0.85,
                "Support": 20,
                "Status": "T3 - Strong (85-89%)",
            }
        ]
    )

    infos: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    monkeypatch.setattr(ml_report_builder.du, "print_info", lambda msg: infos.append(str(msg)))
    monkeypatch.setattr(ml_report_builder.du, "print_warning", lambda msg: warnings.append(str(msg)))
    monkeypatch.setattr(ml_report_builder.du, "print_error", lambda msg: errors.append(str(msg)))

    ml_report_builder.print_evaluation_summary(
        df=df,
        acc=0.80,
        prec=0.90,
        recall=0.80,
        f1=0.84,
        macro_prec=0.40,
        macro_recall=0.35,
        macro_f1=0.32,
    )

    out = capsys.readouterr().out
    assert "Macro Prec" in out
    assert "Macro Recall" in out
    assert "Macro F1" in out
    assert "Weighted F1 across families" in out
    assert any(msg.startswith("T10 - Critically Weak") for msg in warnings)
    assert any("Model-quality failure on evaluation" in msg for msg in warnings)
    assert not errors
