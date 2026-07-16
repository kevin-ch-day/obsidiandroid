# Filename: training/ml_trainers/random_forest_trainer.py
# Purpose  : Train a Random Forest classifier for Android malware classification
#            Supports parameter overrides, ID alignment, and unified output formatting

import time
from collections import Counter
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import GridSearchCV
import numpy as np
from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.cli.ui import display as du
from obsidiandroid.modeling.parallel_layout import (
    grid_search_pre_dispatch,
    grid_search_job_counts,
    resolve_adaptive_job_count,
    tuning_grid_splitter,
)
from obsidiandroid.modeling.training_console_policy import (
    emit_class_imbalance_notice,
    should_print_detailed_classification_report,
    should_print_training_analysis,
    should_print_training_label_summary,
)

# Train a Random Forest model using sample-aligned output
def train_random_forest(
    X_train,
    y_train,
    X_test=None,
    y_test=None,
    sample_ids=None,
    label_encoder=None,
    random_state=42,
    verbose=True,
    grid_search=False,
    **kwargs
):
    params = {
        "n_estimators": getattr(app_config, "RF_NUM_TREES", 100),
        "max_depth": getattr(app_config, "RF_MAX_DEPTH", 12) if len(X_train) > 50 else None,
        "min_samples_split": getattr(app_config, "RF_MIN_SAMPLES_SPLIT", 2),
        "min_samples_leaf": getattr(app_config, "RF_MIN_SAMPLES_LEAF", 1),
        "oob_score": getattr(app_config, "RF_ENABLE_OOB_SCORE", False),
        "class_weight": getattr(app_config, "RF_CLASS_WEIGHT", "balanced"),
        "random_state": random_state,
        "n_jobs": resolve_adaptive_job_count(-1, kind="training"),
    }
    model_params = {**params, **kwargs}

    start = time.time()

    should_grid = bool(
        grid_search or getattr(app_config, "ENABLE_RF_GRID_SEARCH", False)
    )
    grid_search_status = "disabled"
    model: RandomForestClassifier | None = None
    if should_grid:
        label_counts = Counter(y_train)
        min_class_size = min(label_counts.values())
        cv_splitter, minimum_tuning_support = tuning_grid_splitter(
            min_class_size, random_state=random_state
        )
        if cv_splitter is None:
            grid_search_status = "skipped_insufficient_class_support"
            if verbose:
                du.print_warning(
                    "[RANDOM_FOREST] Grid search skipped: need "
                    f"≥{minimum_tuning_support} samples per class "
                    f"(minimum count was {min_class_size}). Fitting default parameters."
                )
        else:
            param_grid = getattr(app_config, "RF_PARAM_GRID", {
                "n_estimators": [150, 200, 250],
                "max_depth": [None, 12, 16, 20],
                "min_samples_split": [2, 4],
                "min_samples_leaf": [1, 2]
            })
            if getattr(app_config, "RF_ENABLE_OOB_SCORE", False):
                param_grid = dict(param_grid)
                param_grid["oob_score"] = [True]
            n_splits = cv_splitter.n_splits
            if verbose:
                _debug_training_info(y_train, n_splits)
                _analyze_training_setup(X_train, y_train, param_grid, n_splits)
            inner_jobs, grid_jobs = grid_search_job_counts()
            base_params = {key: value for key, value in model_params.items() if key not in param_grid}
            base_params["n_jobs"] = inner_jobs
            base_model = RandomForestClassifier(**base_params)
            grid = GridSearchCV(
                estimator=base_model,
                param_grid=param_grid,
                cv=cv_splitter,
                scoring="f1_macro",
                n_jobs=grid_jobs,
                pre_dispatch=grid_search_pre_dispatch(),
            )
            grid.fit(X_train, y_train)
            model = grid.best_estimator_
            model_params.update(grid.best_params_)
            grid_search_status = "completed"

    if model is None:
        model = RandomForestClassifier(**model_params)
        model.fit(X_train, y_train)
        if verbose:
            _debug_training_info(y_train)
            _analyze_training_setup(X_train, y_train)

    duration = time.time() - start

    if verbose:
        print(f"[RANDOM_FOREST] Model trained in {duration:.2f} sec.")
        _print_training_summary(model, y_train)

    feature_ranking = None
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        top_k = safe_int_config_value(getattr(app_config, "RF_TOP_FEATURE_IMPORTANCES", 20), default=20)
        indices = np.argsort(importances)[::-1][:max(1, top_k)]
        feature_ranking = [(int(idx), float(importances[idx])) for idx in indices]

    result = {
        "metadata": {
            "duration": duration,
            "params": model_params,
            "num_classes": len(set(y_train)),
            "top_classes": Counter(y_train).most_common(5),
            "grid_search_requested": should_grid,
            "grid_search_active": grid_search_status == "completed",
            "grid_search_status": grid_search_status,
            "oob_score": getattr(model, "oob_score_", None),
            "feature_importances": feature_ranking
        }
    }

    if X_test is not None and y_test is not None:
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test) if hasattr(model, "predict_proba") else None
        confidences = np.max(y_prob, axis=1) if y_prob is not None else np.ones_like(y_pred)

        # Use dict structure if sample_ids are present
        if sample_ids is not None and len(sample_ids) == len(y_pred):
            predictions_dict = {sid: int(pred) for sid, pred in zip(sample_ids, y_pred)}
            labels_dict = {sid: int(label) for sid, label in zip(sample_ids, y_test)}
            meta_dict = {
                sid: label_encoder.classes_[pred] if label_encoder else str(pred)
                for sid, pred in predictions_dict.items()
            }
        else:
            predictions_dict = list(y_pred)
            labels_dict = list(y_test)
            meta_dict = [label_encoder.classes_[pred] if label_encoder else str(pred) for pred in y_pred]

        result.update({
            "predictions": predictions_dict,
            "true_labels": labels_dict,
            "confidences": confidences,
            "metadata": {
                **result["metadata"],
                "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
                "average_confidence": float(np.mean(confidences))
            },
            "label_encoder": label_encoder,
            "label_classes": list(label_encoder.classes_) if label_encoder else None,
            "enriched_labels": meta_dict
        })

        if verbose:
            if should_print_detailed_classification_report():
                print("[RANDOM_FOREST] Classification Report:")
                print(classification_report(y_test, y_pred, zero_division=0))

    return model, result


# Print training summary
def _print_training_summary(model, y_train):
    if not should_print_training_label_summary():
        return
    label_dist = Counter(int(x) for x in y_train)
    top = [(cls, cnt) for cls, cnt in label_dist.most_common(5)]
    print(f"[RANDOM_FOREST] Classes trained on: {len(label_dist)}")
    print(f"[RANDOM_FOREST] Top classes: {top}")
    print(f"[RANDOM_FOREST] Model Depth: {model.get_params().get('max_depth')}")
    print(f"[RANDOM_FOREST] Estimators: {len(model.estimators_)}")


def _debug_training_info(y_train, cv_folds=None):
    label_dist = Counter(int(x) for x in y_train)
    du.print_debug(f"Class distribution: {dict(label_dist)}")
    if cv_folds is not None:
        du.print_debug(f"Using {cv_folds} CV folds")
    emit_class_imbalance_notice(y_train)


def _analyze_training_setup(X_train, y_train, param_grid=None, cv_folds=None):
    if not should_print_training_analysis(cv_folds=cv_folds):
        return
    n_samples = len(X_train)
    n_features = X_train.shape[1]
    n_classes = len(set(y_train))
    print(
        f"[ANALYSIS] Samples: {n_samples}, Features: {n_features}, Classes: {n_classes}"
    )
    ratio = n_samples / float(n_features or 1)
    if ratio < 5:
        print("[ANALYSIS] Sample-to-feature ratio is low; model may overfit")
    else:
        print("[ANALYSIS] Sample-to-feature ratio looks adequate")

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


def get_default_rf_params():
    return {
        "n_estimators": getattr(app_config, "RF_NUM_TREES", 100),
        "max_depth": getattr(app_config, "RF_MAX_DEPTH", 12),
        "min_samples_split": getattr(app_config, "RF_MIN_SAMPLES_SPLIT", 2),
        "min_samples_leaf": getattr(app_config, "RF_MIN_SAMPLES_LEAF", 1),
        "oob_score": getattr(app_config, "RF_ENABLE_OOB_SCORE", False),
        "class_weight": getattr(app_config, "RF_CLASS_WEIGHT", "balanced"),
        "random_state": app_config.RANDOM_STATE,
        "n_jobs": resolve_adaptive_job_count(-1, kind="training")
    }


def get_model_name():
    return "random_forest"
