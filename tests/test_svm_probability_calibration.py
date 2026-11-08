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


@pytest.mark.parametrize("grid_search", [False, True])
def test_singleton_class_is_refused_before_any_fit(monkeypatch, grid_search) -> None:
    X, y = _dataset(n_samples=60, n_classes=2)
    y = y.copy()
    y.iloc[0] = 2  # a third class with exactly one member

    def unexpected_fit(*args, **kwargs):
        pytest.fail("insufficient-support input reached a fit call")

    monkeypatch.setattr(SVC, "fit", unexpected_fit)
    monkeypatch.setattr(CalibratedClassifierCV, "fit", unexpected_fit)
    with pytest.raises(ValueError, match="at least two training samples per class"):
        _train(monkeypatch, X, y, grid_search=grid_search)


def test_two_training_samples_per_class_supports_cross_validated_calibration(monkeypatch) -> None:
    X = pd.DataFrame([[0.0], [0.2], [1.0], [1.2]])
    y = pd.Series([0, 0, 1, 1])
    model, result = _train(monkeypatch, X, y)

    assert result["metadata"]["probability_calibration"]["folds"] == 2
    assert result["metadata"]["probability_calibration"]["mode"] == "cross_validated"
    np.testing.assert_allclose(model.predict_proba(X).sum(axis=1), 1.0)


def test_calibration_fits_training_rows_only_and_predicts_calibrated_argmax(monkeypatch) -> None:
    X, y = _dataset(n_samples=160)
    X_train, X_test = X.iloc[:120].copy(), X.iloc[120:].copy() + 1000.0
    y_train, y_test = y.iloc[:120].copy(), y.iloc[120:].copy()
    original_fit = CalibratedClassifierCV.fit
    seen = []

    def record_fit(self, fit_X, fit_y, *args, **kwargs):
        pd.testing.assert_frame_equal(fit_X, X_train)
        pd.testing.assert_series_equal(fit_y, y_train)
        seen.append(True)
        return original_fit(self, fit_X, fit_y, *args, **kwargs)

    monkeypatch.setattr(CalibratedClassifierCV, "fit", record_fit)
    monkeypatch.setattr(app_config, "ENABLE_SVM_GRID_SEARCH", False, raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        model, result = svm_trainer.train_svm(
            X_train, y_train, X_test=X_test, y_test=y_test, verbose=False
        )
    assert seen == [True]
    probabilities = model.predict_proba(X_test)
    expected = model.classes_[np.argmax(probabilities, axis=1)]
    np.testing.assert_array_equal(result["predictions"], expected)
    np.testing.assert_allclose(result["confidences"], probabilities.max(axis=1))


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
