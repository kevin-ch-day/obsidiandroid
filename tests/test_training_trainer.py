from pathlib import Path
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
from obsidiandroid.modeling import train_model_executor
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
        criterion="entropy",
        max_features=1.0,
    )
    assert result["metadata"]["params"]["n_estimators"] == 5
    assert model.get_params()["max_depth"] == 2
    assert model.get_params()["criterion"] == "entropy"
    assert model.get_params()["max_features"] == 1.0


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


def test_xgboost_calibration_and_early_stopping_use_separate_training_holdouts(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 10, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_PROBABILITY_CALIBRATION", True, raising=False)
    monkeypatch.setattr(app_config, "CALIBRATION_HOLDOUT", 0.15, raising=False)
    model, result = xgboost_trainer.train_xgboost(
        X,
        y,
        X_test=X,
        y_test=y,
        early_stopping_rounds=3,
        verbose=False,
    )

    assert result["metadata"]["calibrated"] is True
    assert result["metadata"]["calibration_status"] == "fitted"
    assert result["metadata"]["calibration_holdout_size"] > 0
    assert result["metadata"]["xgb_early_stopping_validation_source"] == "training_validation_holdout"
    assert result["metadata"]["xgb_early_stopping_validation_size"] > 0
    assert result["metadata"]["xgb_test_partition_used_for_early_stopping"] is False
    assert model is not None


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
    assert result["metadata"]["xgb_grid_search_requested"] is True
    assert result["metadata"]["xgb_grid_search_active"] is True
    assert result["metadata"]["xgb_grid_search_status"] == "completed"
    assert result["metadata"]["xgb_grid_candidate_count"] == 1


def test_xgboost_unsupported_grid_request_keeps_training_early_stopping(monkeypatch):
    X, y = _create_dataset(n_samples=24)
    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 10, raising=False)
    monkeypatch.setattr(app_config, "GRID_SEARCH_MIN_CLASS_SUPPORT", 9, raising=False)
    monkeypatch.setattr(app_config, "XGB_PARAM_GRID", {"n_estimators": [5]}, raising=False)

    model, result = xgboost_trainer.train_xgboost(
        X,
        y,
        X_test=X,
        y_test=y,
        grid_search=True,
        early_stopping_rounds=3,
        verbose=False,
    )

    assert result["metadata"]["xgb_grid_search_requested"] is True
    assert result["metadata"]["xgb_grid_search_active"] is False
    assert result["metadata"]["xgb_grid_search_status"] == "skipped_insufficient_class_support"
    assert result["metadata"]["xgb_grid_candidate_count"] is None
    assert result["metadata"]["xgb_early_stopping_validation_source"] == "training_validation_holdout"
    assert model is not None


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
        max_iter=77,
        random_state=7,
    )
    assert result["metadata"]["params"]["C"] == 0.5
    assert model.named_steps["logisticregression"].C == 0.5
    assert model.named_steps["logisticregression"].max_iter == 77
    assert model.named_steps["logisticregression"].random_state == 7


def test_svm_grid_search(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "SVM_PARAM_GRID", {"kernel": ["linear"], "C": [0.5]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2)
    model, result = svm_trainer.train_svm(
        X,
        y,
        grid_search=True,
        verbose=False,
        random_state=7,
        gamma="auto",
    )
    assert result["metadata"]["params"]["C"] == 0.5
    assert model.get_params()["kernel"] == "linear"
    assert model.get_params()["gamma"] == "auto"
    assert model.get_params()["random_state"] == 7


def test_numpy_sample_ids_are_packaged_without_ambiguous_truth_checks(monkeypatch):
    X, y = _create_dataset(n_samples=60)
    monkeypatch.setattr(app_config, "RF_NUM_TREES", 5, raising=False)
    sample_ids = np.arange(1000, 1010)

    _, result = random_forest_trainer.train_random_forest(
        X,
        y,
        X_test=X.iloc[:10],
        y_test=y.iloc[:10],
        sample_ids=sample_ids,
        verbose=False,
    )

    assert isinstance(result["predictions"], dict)
    assert set(result["predictions"]) == set(sample_ids.tolist())


def test_misaligned_sample_ids_fall_back_without_truncating_lr_results(monkeypatch):
    X, y = _create_dataset(n_samples=60)
    monkeypatch.setattr(app_config, "LR_MAX_ITER", 100, raising=False)

    _, result = logistic_regression_trainer.train_logistic_regression(
        X,
        y,
        X_test=X.iloc[:10],
        y_test=y.iloc[:10],
        sample_ids=[1, 2],
        verbose=False,
    )

    assert not isinstance(result["predictions"], dict)
    assert len(result["predictions"]) == 10


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
    monkeypatch.setattr(app_config, "GRID_SEARCH_MIN_CLASS_SUPPORT", 2, raising=False)

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
    assert rf_result["metadata"]["grid_search_status"] == "completed"


def test_grid_search_uses_stable_per_class_support_floor(monkeypatch, capfd):
    X, y = _create_dataset(n_samples=9)
    monkeypatch.setattr(app_config, "GRID_SEARCH_MIN_CLASS_SUPPORT", 5, raising=False)
    monkeypatch.setattr(app_config, "RF_PARAM_GRID", {"n_estimators": [5]}, raising=False)
    monkeypatch.setattr(app_config, "RF_NUM_TREES", 7, raising=False)

    model, result = random_forest_trainer.train_random_forest(
        X,
        y,
        grid_search=True,
        verbose=True,
    )

    assert model.get_params()["n_estimators"] == 7
    assert result["metadata"]["params"]["n_estimators"] == 7
    assert result["metadata"]["grid_search_status"] == "skipped_insufficient_class_support"
    assert "need ≥5 samples per class" in capfd.readouterr().out


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


def test_train_and_evaluate_model_uses_configured_output_root_for_exports(
    monkeypatch,
    tmp_path,
) -> None:
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


def test_train_and_evaluate_model_uses_frozen_schema_for_full_predictions(
    monkeypatch,
) -> None:
    """Full-cohort prediction must not reintroduce train-pruned columns."""
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(train_model_executor, "announce_training", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(train_model_executor.ml_console, "is_minimal", lambda: True)
    monkeypatch.setattr(
        train_model_executor,
        "train_model",
        lambda *_args, **_kwargs: {
            "model": object(),
            "X_test": pd.DataFrame({"keep": [0.1]}),
            "y_test": pd.Series([0]),
            "label_encoder": object(),
            "metadata": {},
            "label_classes": [0],
            "feature_selection_contract": {"retained_feature_columns": ["keep"]},
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
    monkeypatch.setattr(train_model_executor, "display_post_training_metrics", lambda *_args, **_kwargs: None)
    captured: dict[str, list[str]] = {}

    def fake_compile(_model_type, _result, features, _labels):
        captured["columns"] = list(features.columns)
        return {"ok": True}

    monkeypatch.setattr(train_model_executor, "run_predictions_and_compile_result", fake_compile)
    monkeypatch.setattr(
        train_model_executor,
        "export_model",
        lambda _result, _model_type, features, _evaluation, _output_dir: captured.setdefault(
            "export_columns", list(features.columns)
        ),
    )

    result = train_model_executor.train_and_evaluate_model(
        model_type="random_forest",
        features_df=pd.DataFrame({"keep": [0.1, 0.2], "pruned": [0, 0]}),
        labels=pd.Series([0, 1]),
        save_model=True,
    )

    assert result == {"ok": True}
    assert captured["columns"] == ["keep"]
    assert captured["export_columns"] == ["keep"]


def test_train_and_evaluate_model_withholds_export_when_full_prediction_fails(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ENABLE_ML_LOGGING", False, raising=False)
    monkeypatch.setattr(train_model_executor, "announce_training", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(train_model_executor.ml_console, "is_minimal", lambda: True)
    monkeypatch.setattr(
        train_model_executor,
        "train_model",
        lambda *_args, **_kwargs: {
            "model": object(),
            "X_test": pd.DataFrame({"feature": [0.1]}),
            "y_test": pd.Series([0]),
            "label_encoder": object(),
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
    monkeypatch.setattr(train_model_executor, "display_post_training_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(train_model_executor, "run_predictions_and_compile_result", lambda *_args, **_kwargs: {})
    exported: list[bool] = []
    monkeypatch.setattr(
        train_model_executor,
        "export_model",
        lambda *_args, **_kwargs: exported.append(True),
    )

    result = train_model_executor.train_and_evaluate_model(
        model_type="random_forest",
        features_df=pd.DataFrame({"feature": [0.1, 0.2]}),
        labels=pd.Series([0, 1]),
        save_model=True,
    )

    assert result == {}
    assert not exported


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


def test_factory_cross_validation_uses_pre_resample_train_partition(monkeypatch):
    """CV must not receive synthetic rows created for the final holdout fit."""
    X, y = _create_dataset(n_samples=90, n_features=5, n_classes=3)
    model_trainer_factory.reset_runtime_training_caches()
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)

    observed: dict[str, int] = {}

    def fake_smote(X_train, y_train, _random_state):
        observed["pre_resample_fit_rows"] = len(X_train)
        return pd.concat([X_train, X_train], ignore_index=True), np.concatenate([y_train, y_train])

    def fake_cv(X_train, y_train, _model_type, _random_state):
        observed["cv_rows"] = len(X_train)
        observed["cv_labels"] = len(y_train)
        return np.asarray([0.5, 0.6])

    def fake_trainer(**kwargs):
        observed["fit_rows"] = len(kwargs["X_train"])
        return object(), {"evaluation": {"macro_f1_score": 0.5}}

    monkeypatch.setattr(model_trainer_factory, "apply_smote", fake_smote)
    monkeypatch.setattr(model_trainer_factory, "perform_cross_validation", fake_cv)
    monkeypatch.setattr(model_trainer_factory, "get_model_trainer", lambda _model: fake_trainer)

    result = model_trainer_factory.train_model_factory(
        features_df=X,
        labels=y,
        model_type="random_forest",
        cross_validate=True,
        test_size=0.25,
        enable_grid_search=False,
    )

    assert observed["cv_rows"] == observed["pre_resample_fit_rows"]
    assert observed["cv_labels"] == observed["pre_resample_fit_rows"]
    assert observed["fit_rows"] == observed["pre_resample_fit_rows"] * 2
    assert result["cv_input_population"] == "pre_resample_train_partition"
    assert result["cv_input_sample_count"] == observed["cv_rows"]


def test_random_forest_class_weight(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "RF_CLASS_WEIGHT", "balanced_subsample", raising=False)
    model, _ = random_forest_trainer.train_random_forest(
        X,
        y,
        verbose=False,
    )
    assert model.get_params()["class_weight"] == "balanced_subsample"


def test_random_forest_caps_training_threads_for_broad_corpus(monkeypatch):
    X, y = _create_dataset()
    monkeypatch.setattr(app_config, "ENABLE_ADAPTIVE_TRAINING_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PROFILE_ID", "android_malware_all_current", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(app_config, "BROAD_CORPUS_TRAINING_N_JOBS_CAP", 2, raising=False)
    model, result = random_forest_trainer.train_random_forest(
        X,
        y,
        verbose=False,
    )
    assert model.get_params()["n_jobs"] == 2
    assert result["metadata"]["params"]["n_jobs"] == 2


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
    monkeypatch.setattr(app_config, "GRID_SEARCH_MIN_CLASS_SUPPORT", 2, raising=False)
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


def test_xgboost_early_stopping_does_not_use_unseen_test_labels(monkeypatch):
    """The held-out test partition must not supply XGBoost early-stopping rows."""
    le = LabelEncoder()
    le.fit(["a", "b", "c", "d"])
    rng = np.random.default_rng(1)
    X_train = pd.DataFrame(rng.standard_normal((18, 6)))
    y_train = pd.Series([0] * 6 + [2] * 6 + [3] * 6)
    X_test = pd.DataFrame(rng.standard_normal((8, 6)))
    y_test = pd.Series([0, 2, 3, 1, 1, 2, 3, 0])

    monkeypatch.setattr(app_config, "XGB_NUM_ESTIMATORS", 12, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_PROBABILITY_CALIBRATION", False, raising=False)

    model, result = xgboost_trainer.train_xgboost(
        X_train,
        y_train,
        X_test=X_test,
        y_test=y_test,
        label_encoder=le,
        early_stopping_rounds=3,
        verbose=False,
    )

    assert result["metadata"]["xgb_encoded_label_remap"] == [0, 2, 3]
    assert result["metadata"]["xgb_early_stopping_validation_source"] == "training_validation_holdout"
    assert result["metadata"]["xgb_early_stopping_validation_size"] > 0
    assert result["metadata"]["xgb_test_partition_used_for_early_stopping"] is False
    assert len(result["predictions"]) == len(y_test)
    assert hasattr(model, "best_iteration")


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
