# Filename: ml_classification/labeling/label_postprocessor.py
# Purpose  : Summarize structured predictions and run post-classification diagnostics

import pandas as pd
from obsidiandroid.cli.ui import display as du
from ml_classification.inference import signal_health_checker
from config import app_config

UNKNOWN_THRESHOLD = 0.75
DIVERSITY_WARNING_THRESHOLD = 2

def _preview_unknown_predictions(df: pd.DataFrame, count: int):
    preview = df[df["predicted_family"] == "unknown"].head(count)
    du.print_info(f"[PREVIEW] Top {count} samples with 'unknown' predictions:")
    du.print_table(
        preview[["sample_id", "true_family", "classification_label", "confidence"]],
        show_index=False
    )

def _preview_prediction_table(df: pd.DataFrame):
    preview_rows = max(1, int(getattr(app_config, "CLASSIFICATION_PREVIEW_ROWS", 8)))
    cols = [
        c for c in ["sample_id", "predicted_family", "classification_label", "confidence"]
        if c in df.columns
    ]
    preview = df[cols].head(preview_rows)
    du.print_info("[PREVIEW] Classification sample overview:")
    du.print_table(preview, show_index=False)

def summarize_prediction_results(df: pd.DataFrame):
    """
    Summarize predictions from a structured classification DataFrame.
    Includes diagnostics on unknown predictions and label diversity.
    """
    try:
        total = len(df)
        if total == 0:
            du.print_warning("[SUMMARY] Empty prediction DataFrame — skipping.")
            return

        fam_counts = df["predicted_family"].value_counts()
        unknown_count = fam_counts.get("unknown", 0)
        unique_preds = df["predicted_family"].nunique()
        unknown_ratio = unknown_count / total if total > 0 else 0.0

        du.print_stat("Top Predicted Family", fam_counts.idxmax())
        du.print_stat("Unique Predicted Families", unique_preds)
        du.print_stat("Unknown Predictions", f"{unknown_count} / {total} ({unknown_ratio:.2%})")

        if unique_preds <= DIVERSITY_WARNING_THRESHOLD:
            du.print_warning("[DIAG] Low prediction diversity — possible overfitting or label collapse.")

        if unknown_ratio >= UNKNOWN_THRESHOLD:
            du.print_warning("[DIAG] High 'unknown' prediction rate (>= 75%) — check encoder, labels, or model generalization.")

        if unknown_count > 0:
            _preview_unknown_predictions(df, count=5)

        _preview_prediction_table(df)

    except Exception as e:
        du.print_error(f"[SUMMARY] Failed to summarize predictions: {type(e).__name__} — {e}")

def run_signal_health_diagnostics(vendor_records: dict):
    """
    Perform signal health analysis using trusted vendor records.
    """
    try:
        du.print_subheader("Signal Health Diagnostic Summary")
        signal_health_checker.analyze_signal_health(vendor_records, verbose=True)
        signal_health_checker.debug_signal_issues(vendor_records, top_n=5)
    except Exception as e:
        du.print_error(f"[DIAG] Vendor signal diagnostics failed: {type(e).__name__} — {e}")
