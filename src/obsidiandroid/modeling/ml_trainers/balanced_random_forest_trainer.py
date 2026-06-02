# Filename: training/ml_trainers/balanced_random_forest_trainer.py
# Purpose  : Train a Balanced Random Forest classifier for Android malware classification
#            Provides results consistent with other trainers in the suite.

import time
from collections import Counter
import warnings

import numpy as np
from imblearn.ensemble import BalancedRandomForestClassifier
from sklearn.metrics import classification_report

from config import app_config
from obsidiandroid.modeling.training_console_policy import (
    should_print_detailed_classification_report,
    should_print_training_label_summary,
)
from obsidiandroid.modeling.parallel_layout import resolve_adaptive_job_count


def train_balanced_random_forest(
    X_train,
    y_train,
    X_test=None,
    y_test=None,
    sample_ids=None,
    label_encoder=None,
    random_state=42,
    verbose=True,
    **kwargs,
):
    """Train a Balanced Random Forest model and optionally evaluate on a test set."""
    params = {
        "n_estimators": getattr(app_config, "BRF_NUM_TREES", 100),
        "max_depth": getattr(app_config, "BRF_MAX_DEPTH", None),
        "min_samples_split": getattr(app_config, "BRF_MIN_SAMPLES_SPLIT", 2),
        "min_samples_leaf": getattr(app_config, "BRF_MIN_SAMPLES_LEAF", 1),
        "oob_score": getattr(app_config, "BRF_ENABLE_OOB_SCORE", False),
        "random_state": random_state,
        "n_jobs": resolve_adaptive_job_count(-1, kind="training"),
    }
    model_params = {**params, **kwargs}

    start = time.time()
    model = BalancedRandomForestClassifier(**model_params)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=(
                "The number of unique classes is greater than 50% of the number "
                "of samples. `y` could represent a regression problem, not a "
                "classification problem."
            ),
            category=UserWarning,
        )
        model.fit(X_train, y_train)
    duration = time.time() - start

    if verbose:
        print(f"[BRF] Model trained in {duration:.2f} sec.")
        _print_training_summary(model, y_train)

    result = {
        "metadata": {
            "duration": duration,
            "params": model_params,
            "num_classes": len(set(y_train)),
            "top_classes": Counter(y_train).most_common(5),
            "oob_score": getattr(model, "oob_score_", None),
        }
    }

    if X_test is not None and y_test is not None:
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test) if hasattr(model, "predict_proba") else None
        confidences = np.max(y_prob, axis=1) if y_prob is not None else np.ones_like(y_pred)

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
            meta_dict = [
                label_encoder.classes_[pred] if label_encoder else str(pred)
                for pred in y_pred
            ]

        result.update(
            {
                "predictions": predictions_dict,
                "true_labels": labels_dict,
                "confidences": confidences,
                "metadata": {
                    **result["metadata"],
                    "classification_report": classification_report(
                        y_test, y_pred, output_dict=True, zero_division=0
                    ),
                    "average_confidence": float(np.mean(confidences)),
                },
                "label_encoder": label_encoder,
                "label_classes": list(label_encoder.classes_) if label_encoder else None,
                "enriched_labels": meta_dict,
            }
        )

        if verbose:
            if should_print_detailed_classification_report():
                print("[BRF] Classification Report:")
                print(classification_report(y_test, y_pred, zero_division=0))

    return model, result


def _print_training_summary(model, y_train):
    if not should_print_training_label_summary():
        return
    label_dist = Counter(int(x) for x in y_train)
    top = [(cls, cnt) for cls, cnt in label_dist.most_common(5)]
    print(f"[BRF] Classes trained on: {len(label_dist)}")
    print(f"[BRF] Top classes: {top}")
    print(f"[BRF] Max depth: {model.get_params().get('max_depth')}")
    print(f"[BRF] Estimators: {len(model.estimators_)}")


def get_default_brf_params():
    return {
        "n_estimators": getattr(app_config, "BRF_NUM_TREES", 100),
        "max_depth": getattr(app_config, "BRF_MAX_DEPTH", None),
        "min_samples_split": getattr(app_config, "BRF_MIN_SAMPLES_SPLIT", 2),
        "min_samples_leaf": getattr(app_config, "BRF_MIN_SAMPLES_LEAF", 1),
        "oob_score": getattr(app_config, "BRF_ENABLE_OOB_SCORE", False),
        "random_state": app_config.RANDOM_STATE,
        "n_jobs": resolve_adaptive_job_count(-1, kind="training"),
    }


def get_model_name():
    return "balanced_random_forest"
