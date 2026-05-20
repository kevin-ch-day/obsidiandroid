"""Tests for terminal-facing model evaluation output helpers."""

from __future__ import annotations

from config import app_config
from obsidiandroid.modeling import model_evaluation


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
        model_evaluation.du,
        "print_info",
        lambda msg, *_args, **_kwargs: printed.append(str(msg)),
    )

    model_evaluation.display_post_training_metrics(
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
