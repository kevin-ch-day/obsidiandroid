# Helper utilities for training workflows
# Provides common validation, cross-validation, and SMOTE operations.

from __future__ import annotations

from collections import Counter
import os
import warnings
from typing import Optional, Union

import numpy as np
import pandas as pd
import xgboost as xgb
from imblearn.ensemble import BalancedRandomForestClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import (
    RepeatedStratifiedKFold,
    StratifiedKFold,
    cross_val_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from imblearn.pipeline import Pipeline as ImbPipeline

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.modeling.parallel_layout import coerce_stratified_cv_folds_config

from .ml_trainers.balanced_random_forest_trainer import (
    get_default_brf_params,
    train_balanced_random_forest,
)
from .ml_trainers.logistic_regression_trainer import (
    get_default_lr_params,
    train_logistic_regression,
)
from .ml_trainers.random_forest_trainer import (
    get_default_rf_params,
    train_random_forest,
)
from .ml_trainers.svm_trainer import (
    get_default_svm_params,
    train_svm,
)
from .ml_trainers.xgboost_trainer import (
    get_default_xgboost_params,
    train_xgboost,
)


def _force_estimator_single_thread(estimator) -> tuple[object, dict[str, int]]:
    """Force estimator/pipeline n_jobs to 1 to avoid nested parallelism."""
    try:
        params = estimator.get_params(deep=True)
    except Exception:
        return estimator, {}

    updates: dict[str, int] = {}
    for key in ("n_jobs", "model__n_jobs", "logisticregression__n_jobs"):
        if key in params:
            updates[key] = 1
    if updates:
        try:
            estimator.set_params(**updates)
        except Exception:
            return estimator, {}
    return estimator, updates


def validate_training_inputs(features_df: pd.DataFrame, labels: Union[list, pd.Series]) -> None:
    """Raise ValueError if training inputs are invalid."""
    if features_df is None or features_df.empty:
        raise ValueError("Feature matrix is empty.")
    if labels is None or len(labels) == 0:
        raise ValueError("Label vector is empty.")
    if len(features_df) != len(labels):
        raise ValueError(f"Feature/label size mismatch: {len(features_df)} vs {len(labels)}")
    if features_df.isna().values.any() or pd.isna(labels).any():
        raise ValueError("Training data contains NaN values.")
    if np.isinf(features_df.to_numpy()).any():
        raise ValueError("Training data contains infinite values.")


def get_model_trainer(model_type: str):
    """Return the trainer function for the requested model type."""
    trainers = {
        "random_forest": train_random_forest,
        "balanced_random_forest": train_balanced_random_forest,
        "logistic_regression": train_logistic_regression,
        "svm": train_svm,
        "xgboost": train_xgboost,
    }
    if model_type not in trainers:
        raise ValueError(f"Unsupported model type: '{model_type}'")
    return trainers[model_type]


def build_base_estimator(
    model_type: str,
    random_state: int = 42,
    n_classes: int | None = None,
):
    """Return a sklearn-compatible estimator for cross-validation."""
    if model_type == "random_forest":
        params = get_default_rf_params()
        params["random_state"] = random_state
        return RandomForestClassifier(**params)
    if model_type == "balanced_random_forest":
        params = get_default_brf_params()
        params["random_state"] = random_state
        return BalancedRandomForestClassifier(**params)
    if model_type == "svm":
        params = get_default_svm_params()
        return SVC(**params)
    if model_type == "logistic_regression":
        params = get_default_lr_params()
        return make_pipeline(StandardScaler(), LogisticRegression(**params))
    if model_type == "xgboost":
        params = get_default_xgboost_params()
        params["random_state"] = random_state
        if n_classes == 2:
            params["objective"] = "binary:logistic"
            params["eval_metric"] = "logloss"
            params.pop("num_class", None)
        else:
            params["objective"] = "multi:softprob"
            params["eval_metric"] = "mlogloss"
            if n_classes and n_classes > 2:
                params["num_class"] = int(n_classes)
            else:
                params.pop("num_class", None)
        return xgb.XGBClassifier(**params)
    raise ValueError(f"Unsupported model type for estimator: {model_type}")


def perform_cross_validation(
    X: pd.DataFrame,
    y: Union[list, pd.Series],
    model_type: str,
    random_state: int,
) -> Optional[np.ndarray]:
    """Run stratified cross-validation and return macro-F1 scores."""
    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    label_counts = Counter(y)
    min_count = min(label_counts.values())
    if min_count < 2:
        du.print_warning(
            f"[CROSS-VAL] Skipped; class counts {label_counts} contain <2 samples"
        )
        return None

    # ``StratifiedKFold`` / ``RepeatedStratifiedKFold`` require ``n_splits >= 2``; some
    # configs historically set ``CV_FOLDS`` to 1, which would otherwise crash CV.
    configured = coerce_stratified_cv_folds_config(getattr(app_config, "CV_FOLDS", 5))
    folds = min(configured, min_count)
    if model_type == "xgboost":
        xgb_cv_max_folds = int(getattr(app_config, "XGB_CV_MAX_FOLDS", 0) or 0)
        if xgb_cv_max_folds > 1:
            folds = min(folds, xgb_cv_max_folds)
    repeats = max(1, int(getattr(app_config, "CV_REPEATS", 1)))
    estimator = build_base_estimator(
        model_type=model_type,
        random_state=random_state,
        n_classes=len(label_counts),
    )
    cv_rebalancing = bool(getattr(app_config, "ENABLE_CV_REBALANCING", True))
    if model_type == "xgboost":
        cv_rebalancing = cv_rebalancing and bool(
            getattr(app_config, "ENABLE_CV_REBALANCING_XGBOOST", False)
        )

    if cv_rebalancing and bool(getattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True)):
        # Mirror the training-time rebalance behavior inside each CV fold.
        if model_type != "balanced_random_forest":
            # In K-fold CV, a class with global count=2 can have only 1 sample
            # inside a training fold. SMOTE cannot run with n_samples_fit=1.
            approx_train_min_count = int(np.floor(min_count * (folds - 1) / folds))
            if min_count > 2 and approx_train_min_count > 1:
                from imblearn.over_sampling import SMOTE

                # Use per-fold effective minimum class support to avoid
                # n_neighbors > n_samples_fit failures inside CV folds.
                k_neighbors = min(5, max(1, approx_train_min_count - 1))
                estimator = ImbPipeline(
                    steps=[
                        ("resample", SMOTE(random_state=random_state, k_neighbors=k_neighbors)),
                        ("model", estimator),
                    ]
                )
            else:
                from imblearn.over_sampling import RandomOverSampler

                estimator = ImbPipeline(
                    steps=[
                        ("resample", RandomOverSampler(random_state=random_state)),
                        ("model", estimator),
                    ]
                )

    if repeats > 1:
        cv = RepeatedStratifiedKFold(
            n_splits=folds,
            n_repeats=repeats,
            random_state=random_state,
        )
    else:
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)

    cv_n_jobs = int(getattr(app_config, "CV_N_JOBS", 1 if os.name == "nt" else -1))
    if bool(getattr(app_config, "CV_AVOID_NESTED_PARALLELISM", True)) and cv_n_jobs != 1:
        estimator, updated = _force_estimator_single_thread(estimator)
        if updated and not quiet:
            du.print_info(
                "[CROSS-VAL] Nested parallelism guard enabled; "
                f"forcing estimator threads to 1 ({', '.join(sorted(updated.keys()))})."
            )
    try:
        with warnings.catch_warnings():
            if model_type == "balanced_random_forest":
                warnings.filterwarnings(
                    "ignore",
                    message=(
                        "The number of unique classes is greater than 50% of the "
                        "number of samples. `y` could represent a regression "
                        "problem, not a classification problem."
                    ),
                    category=UserWarning,
                )
            scores = cross_val_score(
                estimator,
                X,
                y,
                cv=cv,
                scoring="f1_macro",
                n_jobs=cv_n_jobs,
            )
        score_list = [float(s) for s in scores]
        if quiet:
            pass
        elif ml_console.is_debug():
            du.print_info(
                f"[CROSS-VAL] {folds} folds x {repeats} repeat(s) - F1 scores: "
                f"{', '.join(f'{s:.4f}' for s in score_list)}"
            )
            if cv_rebalancing and model_type != "balanced_random_forest":
                du.print_info("[CROSS-VAL] Rebalancing enabled inside folds (SMOTE/ROS auto).")
            du.print_info(f"[CROSS-VAL] n_jobs={cv_n_jobs}")
        elif not ml_console.is_minimal():
            du.print_info(
                f"[CROSS-VAL] {folds} folds x {repeats} repeat(s) "
                f"| mean={np.mean(score_list):.4f} | std={np.std(score_list):.4f}"
            )
        if not quiet and ml_console.is_debug():
            du.print_info(f"[CROSS-VAL] Mean F1: {np.mean(score_list):.4f}")
            du.print_info(f"[CROSS-VAL] Std F1: {np.std(score_list):.4f}")
        return scores
    except Exception as exc:
        # CV must never hard-fail model training; continue without CV metrics.
        du.print_warning(f"[CROSS-VAL] Failed; continuing without CV metrics. Reason: {exc}")
        return None


def apply_smote(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Apply oversampling during training.

    If every class has more than one sample, apply SMOTE.
    Otherwise, use RandomOverSampler to duplicate extremely rare classes.
    """
    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    original_n = int(len(X_train))
    before_counts = {str(int(k)): int(v) for k, v in Counter(y_train).items()}
    method_used = "none"
    k_neighbors_used: int | None = None
    try:
        from imblearn.over_sampling import RandomOverSampler, SMOTE

        label_counts = Counter(y_train)
        min_count = min(label_counts.values())
        if min_count > 1:
            k_neighbors = min(5, max(1, min_count - 1))
            k_neighbors_used = int(k_neighbors)
            sm = SMOTE(random_state=random_state, k_neighbors=k_neighbors)
            try:
                X_res, y_res = sm.fit_resample(X_train, y_train)
                method_used = "SMOTE"
                if not quiet:
                    du.print_info(
                        f"[SMOTE] Applied with k_neighbors={k_neighbors}; new size: {len(X_res)}"
                    )
            except ValueError as smote_exc:
                if not quiet:
                    du.print_warning(
                        f"[SMOTE] Fallback to ROS due to sparse class in split: {smote_exc}"
                    )
                ros = RandomOverSampler(random_state=random_state)
                X_res, y_res = ros.fit_resample(X_train, y_train)
                method_used = "ROS_fallback"
                if not quiet:
                    du.print_info(f"[ROS] Applied fallback oversampling; new size: {len(X_res)}")
        else:
            rare_classes = {cls: 2 for cls, cnt in label_counts.items() if cnt <= 1}
            ros = RandomOverSampler(random_state=random_state, sampling_strategy=rare_classes)
            X_res, y_res = ros.fit_resample(X_train, y_train)
            method_used = "ROS_rare_class_replication"
            if not quiet:
                du.print_info(f"[ROS] Replicated rare classes; new size: {len(X_res)}")

        dist = {int(k): int(v) for k, v in Counter(y_res).items()}
        du.print_debug(f"[RESAMPLE] Class distribution: {dist}")
        after_counts = {str(int(k)): int(v) for k, v in Counter(y_res).items()}
        setattr(
            app_config,
            "RUNTIME_SMOTE_AUDIT_LAST",
            {
                "original_train_n": original_n,
                "post_resample_train_n": int(len(X_res)),
                "method": method_used,
                "k_neighbors": k_neighbors_used,
                "class_counts_before": before_counts,
                "class_counts_after": after_counts,
            },
        )
        return pd.DataFrame(X_res, columns=X_train.columns), pd.Series(y_res)
    except Exception as exc:
        raise RuntimeError(f"SMOTE/ROS oversampling failed: {exc}")
