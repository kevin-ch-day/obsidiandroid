"""Tests for train_model_executor path behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.modeling import train_model_executor


def test_train_and_evaluate_model_uses_configured_output_root_for_exports(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Model export should receive the current configured output root."""
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)

    monkeypatch.setattr(train_model_executor, "announce_training", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(train_model_executor.ml_console, "is_minimal", lambda: True)
    monkeypatch.setattr(
        train_model_executor,
        "train_model",
        lambda *_args, **_kwargs: {
            "model": object(),
            "X_test": pd.DataFrame({"f": [0.1]}),
            "y_test": pd.Series(["a"]),
            "label_encoder": object(),
            "metadata": {},
            "label_classes": ["a"],
        },
    )
    monkeypatch.setattr(
        train_model_executor,
        "evaluate_model",
        lambda **_kwargs: {"accuracy": 1.0, "f1_score": 1.0},
    )
    monkeypatch.setattr(
        train_model_executor.ml_result_validator,
        "validate_result_structure",
        lambda _result: True,
    )
    monkeypatch.setattr(
        train_model_executor,
        "display_post_training_metrics",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        train_model_executor,
        "run_predictions_and_compile_result",
        lambda *_args, **_kwargs: {"ok": True},
    )

    captured: dict[str, Path] = {}

    def _fake_export_model(result, model_type, features_df, evaluation, output_dir):
        captured["output_dir"] = Path(output_dir)

    monkeypatch.setattr(train_model_executor, "export_model", _fake_export_model)

    result = train_model_executor.train_and_evaluate_model(
        model_type="random_forest",
        features_df=pd.DataFrame({"f": [0.1, 0.2]}),
        labels=pd.Series(["a", "b"]),
        save_model=True,
    )

    assert result == {"ok": True}
    assert captured["output_dir"] == (tmp_path / "output").resolve()
