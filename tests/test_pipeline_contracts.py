import numpy as np
import pandas as pd

from config import app_config
from ml_classification.training import model_prediction, pipeline_core


class _DummyEncoder:
    classes_ = np.array(["Anubis", "other"])


def test_align_data_returns_series() -> None:
    features = pd.DataFrame({"feat": [1, 2]}, index=["s1", "s2"])
    labels = pd.DataFrame({"sample_id": ["s1", "s2"], "family_name": ["A", "B"]})
    f, l = pipeline_core.align_data(features, labels)
    assert isinstance(l, pd.Series)
    assert list(f.index) == ["s1", "s2"]


def test_configured_models_defaults_to_fast_mode(monkeypatch):
    monkeypatch.setattr(app_config, "ENABLE_BENCHMARK_MODELS", False, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_TRAINING_MODELS", ["xgboost"], raising=False)
    models = pipeline_core._get_configured_models(None)
    assert models == ["xgboost"]


def test_configured_models_uses_benchmark_set(monkeypatch):
    monkeypatch.setattr(app_config, "ENABLE_BENCHMARK_MODELS", True, raising=False)
    monkeypatch.setattr(
        app_config,
        "BENCHMARK_TRAINING_MODELS",
        ["xgboost", "random_forest"],
        raising=False,
    )
    models = pipeline_core._get_configured_models(None)
    assert models == ["xgboost", "random_forest"]


def test_prune_low_information_quiet_skips_terminal_warning(monkeypatch):
    """Ablations set RUNTIME_QUIET_TRAINING; prune should not spam warnings."""
    captured: list[str] = []
    monkeypatch.setattr(app_config, "RUNTIME_QUIET_TRAINING", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(
        pipeline_core.du,
        "print_warning",
        lambda msg, *a, **k: captured.append(str(msg)),
    )
    df = pd.DataFrame({"flat": [1, 1], "varying": [1, 2]})
    out = pipeline_core._prune_low_information_features(df)
    assert "flat" not in out.columns
    assert captured == []


def test_prune_low_information_verbose_emits_warning(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(app_config, "RUNTIME_QUIET_TRAINING", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(
        pipeline_core.du,
        "print_warning",
        lambda msg, *a, **k: captured.append(str(msg)),
    )
    df = pd.DataFrame({"flat": [1, 1], "varying": [1, 2]})
    pipeline_core._prune_low_information_features(df)
    assert len(captured) == 1
    assert "low-information" in captured[0]


def test_low_confidence_abstain_routes_to_other(monkeypatch):
    monkeypatch.setattr(app_config, "ENABLE_LOW_CONFIDENCE_ABSTAIN", True, raising=False)
    monkeypatch.setattr(app_config, "LOW_CONFIDENCE_THRESHOLD", 0.30, raising=False)
    monkeypatch.setattr(app_config, "ABSTAIN_LABEL", "other", raising=False)

    y_pred = np.array([0, 0, 0])  # all Anubis initially
    y_conf = np.array([0.95, 0.29, 0.05])
    out = model_prediction._apply_low_confidence_abstain(y_pred, y_conf, _DummyEncoder())
    assert out.tolist() == [0, 1, 1]
