# Filename: model_prediction.py
# Purpose  : Predict malware family labels and compute confidence scores using a trained ML model.
#            Handles string-based family labels and logs prediction diagnostics.

import numpy as np
from typing import Tuple, List
from utils import display_utils as du
from config import app_config

# Predict labels for all samples using a trained model

def predict_all_samples(
    model,
    features_df,
    labels,
    label_encoder=None,
) -> Tuple[List[str], List[str], List[str], np.ndarray]:
    """
    Predict labels and confidence scores for every sample.

    Args:
        model: Trained classifier with ``predict`` (and optionally ``predict_proba``) support.
        features_df: Feature matrix for prediction.
        labels: Ground-truth labels corresponding to ``features_df``.
        label_encoder: Optional encoder to decode predicted class indices.

    Returns:
        Tuple consisting of predicted class indices, true labels, decoded labels (metadata),
        and confidence scores for each prediction.
    """
    try:
        y_pred = model.predict(features_df)

        if hasattr(model, "predict_proba"):
            y_conf = np.max(model.predict_proba(features_df), axis=1)
        else:
            y_conf = np.ones(len(features_df))

        y_true = labels.values if hasattr(labels, "values") else list(labels)

        y_pred = _apply_low_confidence_abstain(y_pred, y_conf, label_encoder)

        if label_encoder is not None:
            try:
                metadata = label_encoder.inverse_transform(y_pred)
            except Exception as e:
                du.print_warning(f"[PREDICT] Failed to decode predictions: {e}")
                metadata = list(y_pred)
        else:
            metadata = list(y_pred)

        return list(y_pred), list(y_true), list(metadata), y_conf

    except Exception as e:
        du.print_error(f"[PREDICT] Model prediction failed: {e}")
        return [], [], [], np.array([])

# Print overall prediction statistics including unknown rate and confidence range

def report_prediction_stats(predictions: List[str], confidences: np.ndarray) -> None:
    sample_count = len(predictions)
    unknown_count = sum(1 for label in predictions if str(label).lower() in {"unknown", "other"})
    unknown_rate = unknown_count / sample_count if sample_count else 0.0

    du.print_success(f"Structured predictions generated for {sample_count} samples.")
    if len(confidences) > 0:
        du.print_stat("Confidence Range", f"{confidences.min():.2f} -> {confidences.max():.2f}")
    du.print_stat("Unknown Predictions", f"{unknown_count} / {sample_count} ({unknown_rate:.2%})")

    if unknown_rate > 0.75:
        du.print_warning("Over 75% of predictions are 'unknown'. Check label logic, input quality, or model generalization.")


def _apply_low_confidence_abstain(y_pred, y_conf, label_encoder):
    """
    Route low-confidence predictions to an abstain class (e.g., 'other').
    """
    if not getattr(app_config, "ENABLE_LOW_CONFIDENCE_ABSTAIN", False):
        return y_pred
    if label_encoder is None or not hasattr(label_encoder, "classes_"):
        return y_pred

    classes = [str(c) for c in list(label_encoder.classes_)]
    target = str(getattr(app_config, "ABSTAIN_LABEL", "other"))
    if target not in classes:
        if "other" in classes:
            target = "other"
        elif "unknown" in classes:
            target = "unknown"
        else:
            return y_pred

    threshold = float(getattr(app_config, "LOW_CONFIDENCE_THRESHOLD", 0.30))
    abstain_idx = classes.index(target)
    y_pred_np = np.array(y_pred, copy=True)
    mask = np.array(y_conf) < threshold
    abstain_count = int(mask.sum())
    if abstain_count > 0:
        y_pred_np[mask] = abstain_idx
        du.print_info(
            f"[ABSTAIN] Routed {abstain_count} low-confidence predictions to '{target}' "
            f"(threshold={threshold:.2f})."
        )
    return y_pred_np

