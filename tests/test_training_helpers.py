"""Tests for training helper estimator construction."""

import numpy as np
import pandas as pd

from config import app_config
from ml_classification.training import training_helpers


def test_build_base_estimator_xgboost_binary_objective() -> None:
    """Binary CV estimator should use binary objective and omit num_class."""
    estimator = training_helpers.build_base_estimator(
        model_type="xgboost",
        random_state=42,
        n_classes=2,
    )
    params = estimator.get_params()
    assert params.get("objective") == "binary:logistic"
    assert params.get("eval_metric") == "logloss"
    assert params.get("num_class") is None


def test_build_base_estimator_xgboost_multiclass_objective() -> None:
    """Multiclass CV estimator should use multiclass objective with num_class."""
    estimator = training_helpers.build_base_estimator(
        model_type="xgboost",
        random_state=42,
        n_classes=5,
    )
    params = estimator.get_params()
    assert params.get("objective") == "multi:softprob"
    assert params.get("eval_metric") == "mlogloss"
    assert params.get("num_class") == 5


def test_cross_validation_xgboost_caps_folds_and_avoids_nested_parallelism(monkeypatch) -> None:
    """XGBoost CV should cap fold count and force estimator threads to 1 when CV is parallel."""
    monkeypatch.setattr(app_config, "CV_FOLDS", 5, raising=False)
    monkeypatch.setattr(app_config, "CV_REPEATS", 1, raising=False)
    monkeypatch.setattr(app_config, "CV_N_JOBS", -1, raising=False)
    monkeypatch.setattr(app_config, "XGB_CV_MAX_FOLDS", 3, raising=False)
    monkeypatch.setattr(app_config, "CV_AVOID_NESTED_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CV_REBALANCING", False, raising=False)

    captured: dict[str, object] = {}

    def _fake_cross_val_score(estimator, X, y, cv, scoring, n_jobs):  # noqa: ANN001
        del X, y, scoring
        captured["cv_splits"] = getattr(cv, "n_splits", None)
        captured["n_jobs"] = n_jobs
        captured["estimator_n_jobs"] = estimator.get_params().get("n_jobs")
        return np.array([0.7, 0.71, 0.72])

    monkeypatch.setattr(training_helpers, "cross_val_score", _fake_cross_val_score)

    y = np.array([0, 0, 0, 1, 1, 1, 2, 2, 2, 2])
    X = pd.DataFrame({"f1": np.arange(len(y)), "f2": np.arange(len(y))[::-1]})
    scores = training_helpers.perform_cross_validation(
        X=X,
        y=y,
        model_type="xgboost",
        random_state=42,
    )
    assert scores is not None
    assert captured["cv_splits"] == 3
    assert captured["n_jobs"] == -1
    assert captured["estimator_n_jobs"] == 1
