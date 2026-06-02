# Filename: obsidiandroid/modeling/model_prediction.py
# Purpose  : Predict malware family labels and compute confidence scores using a trained ML model.
#            Handles string-based family labels and logs prediction diagnostics.

import numpy as np
from typing import Any, Tuple, List
from obsidiandroid.cli.ui import display as du
from config import app_config
from obsidiandroid.common.cv_fold_config import safe_float_config_value

# Predict labels for all samples using a trained model

def predict_all_samples(
    model,
    features_df,
    labels,
    label_encoder=None,
) -> Tuple[List[str], List[str], List[str], np.ndarray, list[dict[str, Any]]]:
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

        y_prob = None
        if hasattr(model, "predict_proba"):
            y_prob = model.predict_proba(features_df)
            y_conf = np.max(y_prob, axis=1)
        else:
            y_conf = np.ones(len(features_df))

        y_true = labels.values if hasattr(labels, "values") else list(labels)

        y_pred, abstain_meta = _apply_low_confidence_abstain(
            y_pred,
            y_conf,
            label_encoder,
            y_prob=y_prob,
        )

        if label_encoder is not None:
            try:
                metadata = label_encoder.inverse_transform(y_pred)
            except Exception as e:
                du.print_warning(f"[PREDICT] Failed to decode predictions: {e}")
                metadata = list(y_pred)
        else:
            metadata = list(y_pred)

        return list(y_pred), list(y_true), list(metadata), y_conf, abstain_meta

    except Exception as e:
        du.print_error(f"[PREDICT] Model prediction failed: {e}")
        return [], [], [], np.array([]), []

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


def _benchmark_family_abstain_guardrail_enabled() -> bool:
    """Return whether benchmark family runs should auto-enable abstain guardrails."""
    training_label_field = str(
        getattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "family_id") or "family_id"
    ).strip().lower()
    support_floor_mode = str(
        getattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "membership_gate") or "membership_gate"
    ).strip().lower()
    return bool(
        getattr(app_config, "ENABLE_BENCHMARK_ABSTAIN_GUARDRAIL", True)
        and support_floor_mode == "benchmark_eligibility"
        and training_label_field in {"family_id", "family_canonical_default"}
    )


def _apply_low_confidence_abstain(y_pred, y_conf, label_encoder, *, y_prob=None):
    """
    Route low-confidence predictions to an abstain class (e.g., 'other').
    """
    benchmark_guardrail = _benchmark_family_abstain_guardrail_enabled()
    if not getattr(app_config, "ENABLE_LOW_CONFIDENCE_ABSTAIN", False) and not benchmark_guardrail:
        return y_pred, []
    if label_encoder is None or not hasattr(label_encoder, "classes_"):
        return y_pred, []

    classes = [str(c) for c in list(label_encoder.classes_)]
    target = str(getattr(app_config, "ABSTAIN_LABEL", "other"))
    if target not in classes:
        if "other" in classes:
            target = "other"
        elif "unknown" in classes:
            target = "unknown"
        else:
            return y_pred, []

    threshold_default = getattr(app_config, "LOW_CONFIDENCE_THRESHOLD", 0.30)
    margin_default = getattr(app_config, "LOW_CONFIDENCE_MARGIN_THRESHOLD", 0.0)
    if benchmark_guardrail and not getattr(app_config, "ENABLE_LOW_CONFIDENCE_ABSTAIN", False):
        threshold_default = getattr(app_config, "BENCHMARK_LOW_CONFIDENCE_THRESHOLD", 0.45)
        margin_default = getattr(app_config, "BENCHMARK_LOW_CONFIDENCE_MARGIN_THRESHOLD", 0.15)

    threshold = safe_float_config_value(threshold_default, default=0.30)
    margin_threshold = safe_float_config_value(margin_default, default=0.0)
    abstain_idx = classes.index(target)
    y_pred_np = np.array(y_pred, copy=True)
    raw_y_pred_np = np.array(y_pred, copy=True)
    y_conf_np = np.array(y_conf, copy=False)
    confidence_mask = y_conf_np < threshold
    margin_mask = np.zeros(len(y_pred_np), dtype=bool)
    top1_margin = np.full(len(y_pred_np), np.nan, dtype=float)
    if y_prob is not None:
        try:
            y_prob_np = np.array(y_prob, copy=False)
            if y_prob_np.ndim == 2 and y_prob_np.shape[1] >= 2:
                # Largest and runner-up class probabilities define ambiguity.
                sorted_prob = np.sort(y_prob_np, axis=1)
                top1_margin = sorted_prob[:, -1] - sorted_prob[:, -2]
                if margin_threshold > 0:
                    margin_mask = top1_margin < margin_threshold
        except Exception:
            margin_mask = np.zeros(len(y_pred_np), dtype=bool)
            top1_margin = np.full(len(y_pred_np), np.nan, dtype=float)

    mask = confidence_mask | margin_mask
    abstain_count = int(mask.sum())
    metadata: list[dict[str, Any]] = []
    for idx in range(len(y_pred_np)):
        meta: dict[str, Any] = {
            "abstained": bool(mask[idx]),
            "confidence": float(y_conf_np[idx]) if len(y_conf_np) > idx else None,
            "raw_prediction_index": raw_y_pred_np[idx].item() if hasattr(raw_y_pred_np[idx], "item") else raw_y_pred_np[idx],
        }
        if np.isfinite(top1_margin[idx]):
            meta["confidence_margin"] = float(top1_margin[idx])
        reasons: list[str] = []
        if bool(confidence_mask[idx]):
            reasons.append("low_confidence")
        if bool(margin_mask[idx]):
            reasons.append("low_margin")
        if reasons:
            meta["abstain_reasons"] = reasons
        if bool(mask[idx]):
            try:
                if hasattr(label_encoder, "inverse_transform"):
                    meta["raw_prediction_label"] = str(label_encoder.inverse_transform([raw_y_pred_np[idx]])[0])
                else:
                    raw_idx = int(raw_y_pred_np[idx])
                    if 0 <= raw_idx < len(classes):
                        meta["raw_prediction_label"] = str(classes[raw_idx])
            except Exception:
                pass
        metadata.append(meta)

    if abstain_count > 0:
        y_pred_np[mask] = abstain_idx
        mode = "benchmark guardrail" if benchmark_guardrail and not getattr(app_config, "ENABLE_LOW_CONFIDENCE_ABSTAIN", False) else "configured abstain"
        du.print_info(
            f"[ABSTAIN] Routed {abstain_count} predictions to '{target}' "
            f"({mode}; threshold={threshold:.2f}, margin<{margin_threshold:.2f})."
        )
    return y_pred_np, metadata
