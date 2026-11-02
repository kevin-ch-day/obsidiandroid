"""SVM probabilities come from CalibratedClassifierCV, not the deprecated SVC flag."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.datasets import make_classification
from sklearn.svm import SVC

from config import app_config
from obsidiandroid.modeling import training_helpers
from obsidiandroid.modeling.ml_trainers import svm_trainer


def _dataset(n_samples: int = 120, n_classes: int = 3, random_state: int = 0):
    X, y = make_classification(
        n_samples=n_samples,
        n_features=6,
        n_informative=5,
        n_redundant=0,
        n_classes=n_classes,
        random_state=random_state,
    )
    return pd.DataFrame(X), pd.Series(y)


def _train(monkeypatch, X, y, **kwargs):
    monkeypatch.setattr(app_config, "ENABLE_SVM_GRID_SEARCH", False, raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        return svm_trainer.train_svm(X, y, X_test=X, y_test=y, verbose=False, **kwargs)


def test_svm_training_emits_no_deprecation_and_returns_calibrated_probabilities(monkeypatch) -> None:
    X, y = _dataset()
    model, result = _train(monkeypatch, X, y)

    assert isinstance(model, CalibratedClassifierCV)
    probabilities = model.predict_proba(X)
    assert probabilities.shape == (len(X), 3)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, atol=1e-6)
    assert len(result["confidences"]) == len(X)
    assert result["metadata"]["probability_calibration"] == {
        "method": "sigmoid",
        "mode": "cross_validated",
        "folds": 5,
    }
    assert "probability" not in result["metadata"]["params"]


def test_calibration_folds_are_capped_by_the_smallest_class() -> None:
    assert svm_trainer.probability_calibration_folds([0] * 10 + [1] * 3) == 3
    assert svm_trainer.probability_calibration_folds([0] * 10 + [1] * 2) == 2
    assert svm_trainer.probability_calibration_folds([0] * 10 + [1]) is None
    assert svm_trainer.probability_calibration_folds([0] * 50 + [1] * 50) == 5


def test_singleton_class_falls_back_to_prefit_calibration(monkeypatch) -> None:
    X, y = _dataset(n_samples=60, n_classes=2)
    y = y.copy()
    y.iloc[0] = 2  # a third class with exactly one member
    model, result = _train(monkeypatch, X, y)

    assert result["metadata"]["probability_calibration"]["mode"] == "prefit_training_data"
    assert result["metadata"]["probability_calibration"]["folds"] is None
    assert model.predict_proba(X).shape == (len(X), 3)
    assert set(result["predictions"]) <= {0, 1, 2}


def test_explicit_probability_kwarg_is_ignored(monkeypatch) -> None:
    X, y = _dataset()
    _, result = _train(monkeypatch, X, y, probability=True, C=0.7)
    assert result["metadata"]["params"]["C"] == 0.7
    assert "probability" not in result["metadata"]["params"]


def test_grid_search_tunes_plain_svc_then_calibrates(monkeypatch) -> None:
    X, y = _dataset()
    monkeypatch.setattr(app_config, "SVM_PARAM_GRID", {"kernel": ["linear"], "C": [0.3]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2, raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        model, result = svm_trainer.train_svm(X, y, X_test=X, y_test=y, grid_search=True, verbose=False)

    assert result["metadata"]["grid_search_status"] == "completed"
    assert result["metadata"]["params"]["C"] == 0.3
    assert isinstance(model, CalibratedClassifierCV)
    assert model.predict_proba(X).shape[1] == 3


def test_default_params_and_base_estimator_do_not_request_svc_probability() -> None:
    assert "probability" not in svm_trainer.get_default_svm_params()
    estimator = training_helpers.build_base_estimator("svm", random_state=3)
    assert isinstance(estimator, SVC)
    # scikit-learn 1.9 leaves the deprecated flag at its sentinel unless a caller sets it.
    assert estimator.get_params().get("probability") is not True
