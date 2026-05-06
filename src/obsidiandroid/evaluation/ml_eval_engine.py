# ml_eval_engine.py
# Purpose: Evaluate ML classifiers and export performance metrics for ObsidianDroid

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)
import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.reporting import export_manager
from obsidiandroid.common import ml_console
from . import accuracy_band_utils
from . import ml_report_builder


def evaluate_model_performance(
    model,
    X_test,
    y_test,
    label_encoder=None,
    model_name: str | None = None,
    verbose=True,
) -> dict:
    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    if not quiet and (ml_console.is_debug() or not ml_console.is_minimal()):
        du.print_section("[EVAL] Starting Evaluation Process")

    if model is None or X_test is None or y_test is None or len(X_test) != len(y_test):
        du.print_error("[EVAL] Invalid evaluation input - check model, X_test, y_test")
        return {}

    try:
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, average="weighted", zero_division=0)
        rec = recall_score(y_test, y_pred, average="weighted", zero_division=0)
        f1 = f1_score(y_test, y_pred, average="weighted", zero_division=0)
        macro_prec = precision_score(y_test, y_pred, average="macro", zero_division=0)
        macro_rec = recall_score(y_test, y_pred, average="macro", zero_division=0)
        macro_f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)

        unique_labels = sorted(set(y_test).union(set(y_pred)))
        report_dict = classification_report(
            y_test, y_pred, output_dict=True, labels=unique_labels, zero_division=0
        )
        conf_matrix = confusion_matrix(y_test, y_pred, labels=unique_labels)

        y_true_dec, y_pred_dec, class_labels = _decode_labels(
            y_test, y_pred, unique_labels, label_encoder
        )
        class_labels = _project_class_labels(class_labels)

        cm_path = export_manager.export_confusion_matrix(
            cm=conf_matrix,
            class_labels=class_labels,
            model_name=model_name or _get_model_name(model),
            mode="color",
        )

        label_key_map = {str(lbl): name for lbl, name in zip(unique_labels, class_labels)}
        summary_df = ml_report_builder.build_classification_summary(
            report_dict, label_key_map, include_rank=True
        )

        if verbose:
            ml_report_builder.print_evaluation_summary(
                df=summary_df,
                acc=acc,
                prec=prec,
                recall=rec,
                f1=f1,
                cm_path=cm_path,
            )
            _display_confidence_stats(model, X_test)

        return {
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "f1_score": f1,
            "macro_precision": macro_prec,
            "macro_recall": macro_rec,
            "macro_f1_score": macro_f1,
            "report": report_dict,
            "summary_table": summary_df,
            "confusion_matrix": conf_matrix,
            "confusion_matrix_path": cm_path,
            "y_true": y_true_dec,
            "y_pred": y_pred_dec,
            "accuracy_band": accuracy_band_utils.evaluate_accuracy_band(acc),
            "num_classes": len(class_labels),
            "class_labels": list(class_labels),
            "samples_tested": len(X_test),
            "label_encoder": label_encoder,
            "decoded_labels": list(class_labels),
        }

    except Exception as e:
        du.print_error(f"[EVAL] Evaluation failed: {e}")
        return {}


def _decode_labels(y_true, y_pred, label_ids, label_encoder):
    if label_encoder is None:
        return y_true, y_pred, label_ids
    try:
        return (
            label_encoder.inverse_transform(y_true),
            label_encoder.inverse_transform(y_pred),
            label_encoder.inverse_transform(label_ids),
        )
    except Exception as e:
        du.print_warning(f"[DECODE] Label decoding failed: {e}")
        return y_true, y_pred, label_ids


def _display_confidence_stats(model, X_test):
    if not hasattr(model, "predict_proba"):
        du.print_info("[CONFIDENCE] Model does not support probability estimates.")
        return
    try:
        proba = model.predict_proba(X_test)
        max_conf = proba.max(axis=1)
        du.print_stat("Confidence Range", f"{max_conf.min():.2f} -> {max_conf.max():.2f}")
        du.print_stat("Average Confidence", f"{max_conf.mean():.4f}")
    except Exception as e:
        du.print_warning(f"[CONFIDENCE] Failed to compute confidence scores: {e}")


def _runtime_family_label_map() -> dict[str, str]:
    """Build family-id to display-name map from runtime sample metadata."""
    meta = getattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", None)
    if not isinstance(meta, pd.DataFrame) or meta.empty:
        return {}
    if "family_id" not in meta.columns:
        return {}

    name_col = None
    for candidate in ("family_canonical", "family_name"):
        if candidate in meta.columns:
            name_col = candidate
            break
    if name_col is None:
        return {}

    working = meta[["family_id", name_col]].copy()
    working["family_id"] = pd.to_numeric(working["family_id"], errors="coerce")
    working = working.dropna(subset=["family_id"])
    if working.empty:
        return {}

    working["family_id"] = working["family_id"].astype(int).astype(str)
    working[name_col] = working[name_col].astype(str).str.strip()
    working = working[working[name_col] != ""]
    if working.empty:
        return {}

    dedup = working.drop_duplicates(subset=["family_id"], keep="first")
    return {str(row["family_id"]): str(row[name_col]) for _, row in dedup.iterrows()}


def _project_class_labels(class_labels):
    """Project numeric family IDs to readable family names when mapping exists."""
    label_map = _runtime_family_label_map()
    if not label_map:
        return list(class_labels)

    projected: list[str] = []
    for label in class_labels:
        token = str(label).strip()
        if token in label_map:
            projected.append(label_map[token])
            continue
        try:
            normalized = str(int(float(token)))
            projected.append(label_map.get(normalized, token))
        except (TypeError, ValueError):
            projected.append(token)
    return projected


def _get_model_name(model):
    class_name = type(model).__name__.lower()
    if "random" in class_name:
        return "random_forest"
    if "xgb" in class_name or "xgboost" in class_name:
        return "xgboost"
    if "svm" in class_name:
        return "svm"
    if "logistic" in class_name:
        return "logistic_regression"
    return class_name
