"""Tests for evaluation label projection and confusion-matrix labeling."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from config import app_config
from obsidiandroid.evaluation import ml_eval_engine


class _DummyModel:
    """Simple deterministic model stub for evaluator tests."""

    def __init__(self, predictions: np.ndarray) -> None:
        self._predictions = predictions

    def predict(self, _x):  # type: ignore[no-untyped-def]
        return self._predictions


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
