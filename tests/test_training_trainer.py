import pandas as pd
import numpy as np
import pytest
from sklearn.datasets import make_classification
from sklearn.preprocessing import LabelEncoder

from obsidiandroid.modeling.ml_trainers import (
    random_forest_trainer,
    balanced_random_forest_trainer,
    xgboost_trainer,
    logistic_regression_trainer,
    svm_trainer,
)
from obsidiandroid.modeling import model_trainer_factory
from config import app_config


def _create_dataset(n_samples=400, n_features=8, n_classes=3, random_state=0):
    X, y = make_classification(
        n_samples=n_samples,
        n_features=n_features,
        n_informative=n_features - 1,
        n_redundant=0,
        n_classes=n_classes,
        random_state=random_state,
    )
    return pd.DataFrame(X), pd.Series(y)


def test_random_forest_grid_search(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "RF_PARAM_GRID", {"n_estimators": [5], "max_depth": [2]})
    monkeypatch.setattr(app_config, "CV_FOLDS", 2)
    model, result = random_forest_trainer.train_random_forest(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert result["metadata"]["params"]["n_estimators"] == 5
    assert model.get_params()["max_depth"] == 2


def test_xgboost_early_stopping(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 10)
    model, result = xgboost_trainer.train_xgboost(
        X,
        y,
        X_test=X,
        y_test=y,
        early_stopping_rounds=5,
        verbose=False,
    )
    assert result["metadata"]["params"]["n_estimators"] == 10
    assert hasattr(model, "best_iteration")
    assert model.best_iteration is not None
    assert result["metadata"]["best_iteration"] == model.best_iteration


def test_xgboost_grid_search(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "XGB_PARAM_GRID", {"n_estimators": [50], "max_depth": [3]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2, raising=False)
    model, result = xgboost_trainer.train_xgboost(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert result["metadata"]["params"]["n_estimators"] == 50
    assert model.get_params()["max_depth"] == 3


def test_xgboost_bad_data(monkeypatch):
    X, y = _create_dataset()
    X_bad = X.copy().astype(object)
    X_bad.iloc[0, 0] = "bad"
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 5)
    with pytest.raises(ValueError):
        xgboost_trainer.train_xgboost(
            X_bad,
            y,
            X_test=X_bad,
            y_test=y,
            early_stopping_rounds=5,
            verbose=False,
        )


def test_logistic_regression_training(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "LR_MAX_ITER", 50)
    model, result = logistic_regression_trainer.train_logistic_regression(
        X,
        y,
        X_test=X,
        y_test=y,
        verbose=False,
    )
    assert model.named_steps["logisticregression"].max_iter == 50
    assert len(result["predictions"]) == len(y)


def test_svm_training(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "SVM_C", 0.1)
    model, result = svm_trainer.train_svm(
        X,
        y,
        X_test=X,
        y_test=y,
        verbose=False,
    )
    assert result["metadata"]["params"]["C"] == 0.1
    assert len(result["predictions"]) == len(y)


def test_logistic_regression_grid_search(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "LR_PARAM_GRID", {"logisticregression__C": [0.5]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2)
    model, result = logistic_regression_trainer.train_logistic_regression(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert result["metadata"]["params"]["C"] == 0.5
    assert model.named_steps["logisticregression"].C == 0.5


def test_svm_grid_search(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "SVM_PARAM_GRID", {"kernel": ["linear"], "C": [0.5]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2)
    model, result = svm_trainer.train_svm(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert result["metadata"]["params"]["C"] == 0.5
    assert model.get_params()["kernel"] == "linear"


def test_logistic_regression_grid_search_large_dataset(monkeypatch):
    X, y = _create_dataset(n_samples=600)
    monkeypatch.setattr(
        app_config,
        "LR_PARAM_GRID",
        {"logisticregression__C": [0.5], "logisticregression__solver": ["liblinear"], "logisticregression__penalty": ["l2"]},
        raising=False,
    )
    model, result = logistic_regression_trainer.train_logistic_regression(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert result["metadata"]["params"]["C"] == 0.5
    assert result["metadata"]["params"]["solver"] == "liblinear"


def test_svm_grid_search_large_dataset(monkeypatch):
    X, y = _create_dataset(n_samples=600)
    monkeypatch.setattr(
        app_config,
        "SVM_PARAM_GRID",
        {"kernel": ["rbf"], "C": [0.5], "gamma": ["scale"]},
        raising=False,
    )
    model, result = svm_trainer.train_svm(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert result["metadata"]["params"]["C"] == 0.5
    assert result["metadata"]["params"]["gamma"] == "scale"


def test_logistic_regression_grid_search_config(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "ENABLE_LR_GRID_SEARCH", True, raising=False)
    monkeypatch.setattr(app_config, "LR_PARAM_GRID", {"logisticregression__C": [0.7]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2, raising=False)
    model, result = logistic_regression_trainer.train_logistic_regression(
        X,
        y,
        verbose=False,
    )
    assert result["metadata"]["params"]["C"] == 0.7


def test_svm_grid_search_config(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "ENABLE_SVM_GRID_SEARCH", True, raising=False)
    monkeypatch.setattr(app_config, "SVM_PARAM_GRID", {"kernel": ["linear"], "C": [0.7]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2, raising=False)
    model, result = svm_trainer.train_svm(
        X,
        y,
        verbose=False,
    )
    assert result["metadata"]["params"]["C"] == 0.7
    assert model.get_params()["kernel"] == "linear"


def test_grid_search_small_class_counts(monkeypatch):
    X, y = _create_dataset(n_samples=9)
    monkeypatch.setattr(app_config, "CV_FOLDS", 5, raising=False)

    monkeypatch.setattr(app_config, "LR_PARAM_GRID", {"logisticregression__C": [0.3]}, raising=False)
    lr_model, lr_result = logistic_regression_trainer.train_logistic_regression(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert lr_result["metadata"]["params"]["C"] == 0.3

    monkeypatch.setattr(app_config, "SVM_PARAM_GRID", {"kernel": ["linear"], "C": [0.3]}, raising=False)
    svm_model, svm_result = svm_trainer.train_svm(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert svm_result["metadata"]["params"]["C"] == 0.3

    monkeypatch.setattr(app_config, "RF_PARAM_GRID", {"n_estimators": [5]}, raising=False)
    rf_model, rf_result = random_forest_trainer.train_random_forest(
        X,
        y,
        grid_search=True,
        verbose=False,
    )
    assert rf_result["metadata"]["params"]["n_estimators"] == 5


def test_logistic_regression_bad_data_nan(monkeypatch):
    X, y = _create_dataset()
    X.iloc[0, 0] = np.nan
    monkeypatch.setattr(app_config, "LR_MAX_ITER", 10)
    with pytest.raises(ValueError):
        logistic_regression_trainer.train_logistic_regression(
            X,
            y,
            verbose=False,
        )


def test_svm_bad_data_length():
    X, y = _create_dataset()
    y_short = y[:-1]
    with pytest.raises(ValueError):
        svm_trainer.train_svm(
            X,
            y_short,
            verbose=False,
        )


def test_factory_cross_validation(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "CV_FOLDS", 2, raising=False)
    result = model_trainer_factory.train_model_factory(
        features_df=X,
        labels=y,
        model_type="random_forest",
        cross_validate=True,
        test_size=0.3,
        enable_grid_search=False,
    )
    assert result["cv_scores"] is not None
    assert len(result["cv_scores"]) == 2
    assert pytest.approx(np.mean(result["cv_scores"])) == result["cv_score_mean"]


def test_random_forest_class_weight(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "RF_CLASS_WEIGHT", "balanced_subsample", raising=False)
    model, _ = random_forest_trainer.train_random_forest(
        X,
        y,
        verbose=False,
    )
    assert model.get_params()["class_weight"] == "balanced_subsample"


def test_balanced_random_forest_training(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "BRF_NUM_TREES", 10, raising=False)
    model, result = balanced_random_forest_trainer.train_balanced_random_forest(
        X,
        y,
        X_test=X,
        y_test=y,
        verbose=False,
    )
    assert result["metadata"]["params"]["n_estimators"] == 10
    assert len(result["predictions"]) == len(y)


def test_verbose_analysis_output(monkeypatch, capfd):
    X, y = _create_dataset(n_samples=12)
    monkeypatch.setattr(app_config, "LR_PARAM_GRID", {"logisticregression__C": [0.2]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2, raising=False)
    logistic_regression_trainer.train_logistic_regression(
        X,
        y,
        grid_search=True,
        verbose=True,
    )
    captured = capfd.readouterr().out
    assert "[ANALYSIS]" in captured
    assert "Grid search" in captured


def test_xgboost_guardrails_cap_estimators_for_large_multiclass(monkeypatch):
    X, y = _create_dataset(n_samples=500, n_classes=30)
    monkeypatch.setattr(app_config, "XGB_ADAPTIVE_ESTIMATORS_ENABLED", True, raising=False)
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 300, raising=False)
    monkeypatch.setattr(app_config, "XGB_GUARDRAIL_LARGE_CLASS_THRESHOLD", 25, raising=False)
    monkeypatch.setattr(app_config, "XGB_GUARDRAIL_LARGE_ESTIMATOR_CAP", 90, raising=False)
    monkeypatch.setattr(app_config, "XGB_GUARDRAIL_LARGE_EARLY_STOPPING", 8, raising=False)
    monkeypatch.setattr(app_config, "XGB_EARLY_STOPPING_ROUNDS", 20, raising=False)
    model, result = xgboost_trainer.train_xgboost(
        X,
        y,
        X_test=X,
        y_test=y,
        verbose=False,
    )
    assert result["metadata"]["xgb_guardrail_profile"] == "large_multiclass"
    assert result["metadata"]["params"]["n_estimators"] == 90
    assert result["metadata"]["xgb_effective_early_stopping_rounds"] == 8


def test_xgboost_guardrails_disabled_respects_requested_estimators(monkeypatch):
    X, y = _create_dataset(n_samples=300, n_classes=20)
    monkeypatch.setattr(app_config, "XGB_ADAPTIVE_ESTIMATORS_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 260, raising=False)
    monkeypatch.setattr(app_config, "XGB_EARLY_STOPPING_ROUNDS", 22, raising=False)
    model, result = xgboost_trainer.train_xgboost(
        X,
        y,
        X_test=X,
        y_test=y,
        verbose=False,
    )
    assert result["metadata"]["xgb_adaptive_estimators_enabled"] is False
    assert result["metadata"]["params"]["n_estimators"] == 260
    assert result["metadata"]["xgb_effective_early_stopping_rounds"] == 22



def test_xgboost_binary_uses_binary_objective(monkeypatch):
    X, y = _create_dataset(n_samples=220, n_classes=2)
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 40, raising=False)
    model, result = xgboost_trainer.train_xgboost(
        X,
        y,
        X_test=X,
        y_test=y,
        verbose=False,
    )
    assert result["metadata"]["params"]["objective"] == "binary:logistic"
    assert "num_class" not in result["metadata"]["params"]


def test_xgboost_num_class_uses_label_encoder_when_train_omits_label(monkeypatch):
    """Regression: sparse present-class count must not shrink XGBoost ``num_class`` vs encoder."""
    le = LabelEncoder()
    le.fit(["a", "b", "c", "d"])
    rng = np.random.default_rng(0)
    n = 60
    X = pd.DataFrame(rng.standard_normal((n, 8)))
    # Encoded 0,2,3 only — class 1 missing from training (as after a split / resample edge case).
    y_sparse = pd.Series(np.array([0] * 15 + [2] * 15 + [3] * 15 + [0] * 15))
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 12, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_PROBABILITY_CALIBRATION", False, raising=False)
    model, result = xgboost_trainer.train_xgboost(
        X,
        y_sparse,
        X_test=X,
        y_test=y_sparse,
        label_encoder=le,
        early_stopping_rounds=0,
        verbose=False,
    )
    assert result["metadata"]["num_classes"] == 3  # contiguous fit space covers {0,2,3} → 3 XGB logits
    assert result["metadata"]["ontology_classes"] == 4  # encoder still holds 4 string classes
    assert result["metadata"]["xgb_encoded_label_remap"] == [0, 2, 3]
    assert int(model.get_params().get("num_class", 0)) == 3


def test_xgboost_guardrail_profile_caps_override(monkeypatch):
    X, y = _create_dataset(n_samples=420, n_classes=30)
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 260, raising=False)
    monkeypatch.setattr(app_config, "XGB_EARLY_STOPPING_ROUNDS", 18, raising=False)
    monkeypatch.setattr(app_config, "XGB_GUARDRAIL_LARGE_CLASS_THRESHOLD", 25, raising=False)
    monkeypatch.setattr(
        app_config,
        "XGB_GUARDRAIL_PROFILE_CAPS",
        {
            "default": {"estimator_cap": 260, "early_stopping_rounds": 18},
            "medium_multiclass": {"estimator_cap": 170, "early_stopping_rounds": 12},
            "large_multiclass": {"estimator_cap": 75, "early_stopping_rounds": 6},
        },
        raising=False,
    )
    model, result = xgboost_trainer.train_xgboost(
        X,
        y,
        X_test=X,
        y_test=y,
        verbose=False,
    )
    assert result["metadata"]["xgb_guardrail_profile"] == "large_multiclass"
    assert result["metadata"]["params"]["n_estimators"] == 75
    assert result["metadata"]["xgb_effective_early_stopping_rounds"] == 6
