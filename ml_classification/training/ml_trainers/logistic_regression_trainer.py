# Filename: training/ml_trainers/logistic_regression_trainer.py
# Purpose  : Train a Logistic Regression model (with scaling) for Android malware classification
#            Supports parameter overrides, evaluation diagnostics, and unified output formatting.

import time
import numpy as np
import pandas as pd
from collections import Counter
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
from sklearn.model_selection import GridSearchCV
from config import app_config
from obsidiandroid.cli.ui import display as du


def _validate_inputs(X_train, y_train):
    """Basic sanity checks for training data."""
    if X_train is None or len(X_train) == 0:
        raise ValueError("X_train is missing or empty.")
    if y_train is None or len(y_train) == 0:
        raise ValueError("y_train is missing or empty.")
    if len(X_train) != len(y_train):
        raise ValueError(
            f"X_train and y_train length mismatch: {len(X_train)} != {len(y_train)}"
        )
    x_values = np.asarray(X_train)
    y_values = np.asarray(y_train)
    if np.isnan(x_values).any() or np.isnan(y_values).any():
        raise ValueError("NaN values detected in training data.")

# Train Logistic Regression Classifier
def train_logistic_regression(
    X_train,
    y_train,
    X_test=None,
    y_test=None,
    sample_ids=None,
    label_encoder=None,
    verbose=True,
    grid_search=False,
    **kwargs
):
    _validate_inputs(X_train, y_train)
    # Define default training parameters
    params = {
        "max_iter": getattr(app_config, "LR_MAX_ITER", 2000),
        "solver": getattr(app_config, "LR_SOLVER", "lbfgs"),
        "class_weight": "balanced"
    }
    model_params = {**params, **kwargs}

    def _contains_nan(data):
        if isinstance(data, (pd.DataFrame, pd.Series)):
            return data.isna().values.any()
        return np.isnan(np.array(data)).any()

    if len(X_train) != len(y_train):
        raise ValueError("X_train and y_train must have the same number of rows")
    if _contains_nan(X_train) or _contains_nan(y_train):
        raise ValueError("Training data contains NaN values")
    if X_test is not None and _contains_nan(X_test):
        raise ValueError("X_test contains NaN values")
    if y_test is not None and _contains_nan(y_test):
        raise ValueError("y_test contains NaN values")

    # Build model pipeline
    start_time = time.time()

    if grid_search or getattr(app_config, "ENABLE_LR_GRID_SEARCH", False):
        param_grid = getattr(app_config, "LR_PARAM_GRID", {
            "logisticregression__C": [0.1, 1.0, 10.0],
            "logisticregression__solver": ["lbfgs"],
        })
        # sklearn>=1.8 deprecates explicit `penalty`; default is effectively l2.
        # Strip deprecated entries from custom config grids to avoid warning spam.
        if "logisticregression__penalty" in param_grid:
            param_grid = dict(param_grid)
            param_grid.pop("logisticregression__penalty", None)
        label_counts = Counter(y_train)
        min_class_size = min(label_counts.values())
        cv_folds = min(getattr(app_config, "CV_FOLDS", 3), min_class_size)
        if verbose:
            _debug_training_info(y_train, cv_folds)
            _analyze_training_setup(X_train, y_train, param_grid, cv_folds)
        base_pipeline = make_pipeline(
            StandardScaler(),
            LogisticRegression(**params)
        )
        grid = GridSearchCV(
            estimator=base_pipeline,
            param_grid=param_grid,
            cv=cv_folds,
            scoring="f1_macro",
            n_jobs=-1,
        )
        try:
            grid.fit(X_train, y_train)
            model = grid.best_estimator_
            lr_params = model.named_steps["logisticregression"].get_params()
            model_params.update(lr_params)
        except ValueError as exc:
            error_msg = str(exc).lower()
            has_liblinear = "liblinear" in error_msg or _grid_contains_solver(param_grid, "liblinear")
            is_multiclass = len(set(y_train)) > 2
            if not (has_liblinear and is_multiclass):
                raise

            if verbose:
                print(
                    "[WARNING] liblinear is not multiclass-compatible in this sklearn build; "
                    "falling back to OneVsRest(LogisticRegression)."
                )

            ovr_pipeline = make_pipeline(
                StandardScaler(),
                OneVsRestClassifier(
                    LogisticRegression(
                        max_iter=getattr(app_config, "LR_MAX_ITER", 2000),
                        class_weight="balanced",
                    )
                ),
            )
            ovr_param_grid = _transform_grid_for_ovr(param_grid)
            ovr_grid = GridSearchCV(
                estimator=ovr_pipeline,
                param_grid=ovr_param_grid,
                cv=cv_folds,
                scoring="f1_macro",
                n_jobs=-1,
            )
            ovr_grid.fit(X_train, y_train)
            model = ovr_grid.best_estimator_
            ovr_params = model.named_steps["onevsrestclassifier"].estimator.get_params()
            model_params.update(ovr_params)
            model_params["solver"] = ovr_params.get("solver", "liblinear")
    else:
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(**model_params)
        )
        model.fit(X_train, y_train)
        if verbose:
            _debug_training_info(y_train)
            _analyze_training_setup(X_train, y_train)

    duration = time.time() - start_time

    if verbose:
        print(f"[LOGISTIC_REGRESSION] Model trained in {duration:.2f} sec.")
        _print_training_summary(y_train)

    # Initialize result structure
    results = {
        "metadata": {
            "duration": duration,
            "params": model_params
        }
    }

    # If test set provided, evaluate model
    if X_test is not None and y_test is not None:
        y_pred = model.predict(X_test)
        y_pred = np.array(y_pred)

        try:
            if "logisticregression" in model.named_steps:
                clf = model.named_steps["logisticregression"]
            else:
                clf = model.named_steps["onevsrestclassifier"]
            if hasattr(clf, "predict_proba"):
                y_prob = model.predict_proba(X_test)
                confidences = np.max(y_prob, axis=1)
            else:
                confidences = np.ones_like(y_pred)
        except Exception:
            confidences = np.ones_like(y_pred)

        if verbose:
            print("[LOGISTIC_REGRESSION] Classification Report:")
            print(classification_report(y_test, y_pred, zero_division=0))

        # Package predictions as dict if sample IDs and encoder available
        if sample_ids is not None and label_encoder is not None:
            predictions = dict(zip(sample_ids, y_pred))
            true_labels = dict(zip(sample_ids, y_test))
            metadata = dict(zip(sample_ids, [label_encoder.classes_[i] for i in y_pred]))
        else:
            predictions = y_pred
            true_labels = y_test
            metadata = [label_encoder.classes_[i] for i in y_pred] if label_encoder else ["unknown"] * len(y_pred)

        results.update({
            "predictions": predictions,
            "true_labels": true_labels,
            "confidences": confidences,
            "prediction_metadata": metadata,
            "label_encoder": label_encoder,
            "label_classes": list(label_encoder.classes_) if label_encoder else []
        })

    return model, results


# Print training distribution
def _print_training_summary(y_train):
    label_dist = Counter(int(x) for x in y_train)
    top_classes = [(cls, cnt) for cls, cnt in label_dist.most_common(5)]
    print(f"[LOGISTIC_REGRESSION] Classes trained on: {len(label_dist)}")
    print(f"[LOGISTIC_REGRESSION] Top classes: {top_classes}")


def _debug_training_info(y_train, cv_folds=None):
    label_dist = Counter(int(x) for x in y_train)
    du.print_debug(f"Class distribution: {dict(label_dist)}")
    if cv_folds is not None:
        du.print_debug(f"Using {cv_folds} CV folds")
    if label_dist:
        total = sum(label_dist.values())
        min_ratio = min(label_dist.values()) / max(label_dist.values())
        if min_ratio < 0.1:
            du.print_warning("Significant class imbalance detected")


def _analyze_training_setup(X_train, y_train, param_grid=None, cv_folds=None):
    """Print higher level interpretation of the training configuration."""
    n_samples = len(X_train)
    n_features = X_train.shape[1]
    n_classes = len(set(y_train))
    print(
        f"[ANALYSIS] Samples: {n_samples}, Features: {n_features}, Classes: {n_classes}"
    )
    ratio = n_samples / float(n_features or 1)
    if ratio < 5:
        print("[ANALYSIS] Sample-to-feature ratio is low; watch for overfitting")
    else:
        print("[ANALYSIS] Sample-to-feature ratio looks sufficient")

    if cv_folds:
        combos = 1
        if param_grid:
            for vals in param_grid.values():
                combos *= len(vals)
        fits = combos * cv_folds
        print(
            f"[ANALYSIS] Grid search exploring {combos} combos x {cv_folds} folds (~{fits} fits)"
        )
        train_size = int(n_samples * (cv_folds - 1) / cv_folds)
        print(f"[ANALYSIS] Each fold trains on about {train_size} samples")


def _grid_contains_solver(param_grid, solver_name):
    for key, values in param_grid.items():
        if key.endswith("__solver") and solver_name in values:
            return True
    return False


def _transform_grid_for_ovr(param_grid):
    transformed = {}
    for key, values in param_grid.items():
        if key.startswith("logisticregression__"):
            ovr_key = key.replace(
                "logisticregression__",
                "onevsrestclassifier__estimator__",
                1,
            )
            transformed[ovr_key] = values
    if "onevsrestclassifier__estimator__solver" not in transformed:
        transformed["onevsrestclassifier__estimator__solver"] = ["liblinear"]
    return transformed


# Accessor for default logistic regression parameters
def get_default_lr_params():
    return {
        "max_iter": getattr(app_config, "LR_MAX_ITER", 2000),
        "solver": getattr(app_config, "LR_SOLVER", "lbfgs"),
        "class_weight": "balanced"
    }


# Return model name
def get_model_name():
    return "logistic_regression"
