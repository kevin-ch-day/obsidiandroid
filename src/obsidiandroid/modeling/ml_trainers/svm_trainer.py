# Filename: training/ml_trainers/svm_trainer.py
# Purpose  : Train a Support Vector Machine (SVM) classifier for Android malware classification
#            Includes probability support, result packaging, and diagnostics

import time
from collections import Counter
from sklearn.svm import SVC
from sklearn.metrics import classification_report
from sklearn.model_selection import GridSearchCV
import numpy as np
from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.modeling.parallel_layout import (
    grid_search_job_counts,
    stratified_kfold_for_grid_search,
)
from obsidiandroid.modeling.training_console_policy import (
    emit_class_imbalance_notice,
    should_print_detailed_classification_report,
    should_print_training_analysis,
    should_print_training_label_summary,
)


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

# Train an SVM model with sample-aware outputs
def train_svm(
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
    _validate_inputs(X_train, y_train)
    params = {
        "kernel": getattr(app_config, "SVM_KERNEL", "rbf"),
        "C": getattr(app_config, "SVM_C", 1.0),
        "class_weight": "balanced",
        "probability": True,
        "random_state": random_state,
    }
    model_params = {**params, **kwargs}

    if verbose:
        print("[SVM] Training started...")

    start = time.time()

    should_grid = bool(
        grid_search or getattr(app_config, "ENABLE_SVM_GRID_SEARCH", False)
    )
    model = None
    if should_grid:
        param_grid = getattr(app_config, "SVM_PARAM_GRID", {
            "kernel": ["linear", "rbf"],
            "C": [0.1, 1.0, 10.0],
            "gamma": ["scale", "auto"],
        })
        label_counts = Counter(y_train)
        min_class_size = min(label_counts.values())
        cv_splitter = stratified_kfold_for_grid_search(
            min_class_size, random_state=random_state
        )
        if cv_splitter is None:
            if verbose:
                du.print_warning(
                    "[SVM] Grid search skipped: need ≥2 samples per class "
                    f"(minimum count was {min_class_size}). Fitting default parameters."
                )
        else:
            n_splits = cv_splitter.n_splits
            if verbose:
                _debug_training_info(y_train, n_splits)
                _analyze_training_setup(X_train, y_train, param_grid, n_splits)
            _, grid_jobs = grid_search_job_counts()
            base_model = SVC(class_weight="balanced", probability=True)
            grid = GridSearchCV(
                estimator=base_model,
                param_grid=param_grid,
                cv=cv_splitter,
                scoring="f1_macro",
                n_jobs=grid_jobs,
            )
            grid.fit(X_train, y_train)
            model = grid.best_estimator_
            model_params.update(grid.best_params_)

    if model is None:
        model = SVC(**model_params)
        model.fit(X_train, y_train)
        if verbose:
            _debug_training_info(y_train)
            _analyze_training_setup(X_train, y_train)
    duration = time.time() - start

    if verbose:
        print(f"[SVM] Training completed in {duration:.2f} sec.")
        _print_training_summary(y_train)

    results = {
        "metadata": {
            "duration": duration,
            "params": model_params
        }
    }

    if X_test is not None and y_test is not None:
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)
        confidences = np.max(y_prob, axis=1)

        # Prepare outputs using sample_ids
        if sample_ids and len(sample_ids) == len(y_pred):
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

        # Verbose classification report
        if verbose:
            if should_print_detailed_classification_report():
                print("[SVM] Classification Report:")
                print(classification_report(y_test, y_pred, zero_division=0))

        results.update({
            "predictions": predictions_dict,
            "true_labels": labels_dict,
            "confidences": confidences,
            "metadata": {
                **results["metadata"],
                "classification_report": classification_report(y_test, y_pred, output_dict=True, zero_division=0),
                "average_confidence": float(np.mean(confidences))
            },
            "label_encoder": label_encoder,
            "label_classes": list(label_encoder.classes_) if label_encoder else None,
            "enriched_labels": meta_dict
        })

    return model, results


def _print_training_summary(y_train):
    if not should_print_training_label_summary():
        return
    label_dist = Counter(int(x) for x in y_train)
    top_classes = [(cls, cnt) for cls, cnt in label_dist.most_common(5)]
    print(f"[SVM] Classes trained on: {len(label_dist)}")
    print(f"[SVM] Top classes: {top_classes}")


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
        print("[ANALYSIS] Sample-to-feature ratio is low; consider dimensionality reduction")
    else:
        print("[ANALYSIS] Sample-to-feature ratio looks reasonable")

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


def get_default_svm_params():
    return {
        "kernel": "rbf",
        "C": 1.0,
        "class_weight": "balanced",
        "probability": True,
        "random_state": 42,
    }


def get_model_name():
    return "svm"
