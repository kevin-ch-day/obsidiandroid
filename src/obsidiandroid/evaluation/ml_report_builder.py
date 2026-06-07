# Filename: ml_report_builder.py
# Purpose : Structured reporting and interpretation of ML classification results

import pandas as pd
from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from . import accuracy_band_utils


def build_classification_summary(report_dict, label_key_map: dict, include_rank: bool = True) -> pd.DataFrame:
    """Build a summary DataFrame from sklearn classification_report output."""
    if ml_console.is_debug():
        du.print_info("Generating per-family classification metrics")
    summary_rows = []
    missing_keys = []
    available_keys = list(report_dict.keys())

    for str_idx, family_label in label_key_map.items():
        metrics = report_dict.get(str(str_idx))
        if not isinstance(metrics, dict):
            missing_keys.append((str_idx, family_label))
            continue

        precision = round(metrics.get("precision", 0.0), 4)
        recall = round(metrics.get("recall", 0.0), 4)
        f1 = round(metrics.get("f1-score", 0.0), 4)
        support = int(metrics.get("support", 0))
        status = classify_f1_status(f1, support, include_score_rank=include_rank)

        summary_rows.append(
            {
                "Family": family_label,
                "Precision": precision,
                "Recall": recall,
                "F1-Score": f1,
                "Support": support,
                "Status": status,
            }
        )

    if missing_keys:
        du.print_warning(f"[WARNING] Metrics not found for {len(missing_keys)} label(s):")
        for str_idx, label in missing_keys:
            du.print_warning(f" - [{str_idx}] {label}")
        du.print_debug(f"Valid keys in classification report: {available_keys}")

    if not summary_rows:
        du.print_error("[ERROR] No valid per-family metrics extracted from classification report.")
        return pd.DataFrame()

    df = pd.DataFrame(summary_rows)
    if include_rank and "F1-Score" in df.columns:
        df["Rank"] = df["F1-Score"].rank(ascending=False, method="min").astype(int)
        df = df.sort_values(by="F1-Score", ascending=False).reset_index(drop=True)

    return df


def classify_f1_status(f1: float, support: int, include_score_rank: bool = False) -> str:
    """Return tiered status text for a class-level F1 score."""
    if support == 0:
        return "T0 - Unseen Class (No Support)" if include_score_rank else "Unseen Class (No Support)"
    if support < 3:
        return "T0 - Low Sample Count" if include_score_rank else "Low Sample Count"

    tier_code = accuracy_band_utils.get_accuracy_tier_code(f1)
    description = accuracy_band_utils.get_accuracy_band_description(f1)
    return f"{tier_code} - {description}" if include_score_rank else description


def print_evaluation_summary(
    df,
    acc,
    prec,
    recall,
    f1,
    macro_prec: float | None = None,
    macro_recall: float | None = None,
    macro_f1: float | None = None,
    cm_path: str = None,
):
    """Print per-family and global metrics in a console-safe format."""
    if ml_console.is_minimal():
        return
    show_per_family = bool(getattr(app_config, "ML_SHOW_PER_FAMILY_TABLE", False))
    show_preview_when_hidden = bool(
        getattr(app_config, "ML_SHOW_PER_FAMILY_PREVIEW_WHEN_HIDDEN", False)
    )
    max_rows = max(
        1, safe_int_config_value(getattr(app_config, "ML_PER_FAMILY_TOP_ROWS", 12), default=12)
    )

    if not show_per_family:
        if show_preview_when_hidden:
            du.print_info(
                f"Per-family table suppressed (compact mode). Showing top {min(max_rows, len(df))} by F1 only."
            )
            df = df.head(max_rows)
            print(
                f"{'Rank':<6}{'Family':<18}{'Precision':>10}{'Recall':>10}"
                f"{'F1-Score':>10}{'Support':>10}   {'Status'}"
            )
            print("-" * 90)

            for _, row in df.iterrows():
                print(
                    f"{row['Rank']:<6}{row['Family']:<18}{row['Precision']:>10.4f}{row['Recall']:>10.4f}"
                    f"{row['F1-Score']:>10.4f}{row['Support']:>10}   {row['Status']}"
                )
        else:
            du.print_info("Per-family table suppressed (compact mode).")
    else:
        print(
            f"{'Rank':<6}{'Family':<18}{'Precision':>10}{'Recall':>10}"
            f"{'F1-Score':>10}{'Support':>10}   {'Status'}"
        )
        print("-" * 90)

        for _, row in df.iterrows():
            print(
                f"{row['Rank']:<6}{row['Family']:<18}{row['Precision']:>10.4f}{row['Recall']:>10.4f}"
                f"{row['F1-Score']:>10.4f}{row['Support']:>10}   {row['Status']}"
            )

    print("\nGlobal Classification Metrics")
    print(f"{'Metric':<20}{'Score':<10} Description")
    print(f"{'-' * 20} {'-' * 10} {'-' * 45}")
    print(f"{'Accuracy':<20}{acc:.4f}   Overall correctness of predictions")
    print(f"{'Weighted Precision':<20}{prec:.4f}   Weighted precision across families")
    print(f"{'Weighted Recall':<20}{recall:.4f}   Weighted recall across families")
    print(f"{'Weighted F1':<20}{f1:.4f}   Weighted F1 across families")
    if macro_prec is not None:
        print(f"{'Macro Precision':<20}{macro_prec:.4f}   Macro precision across families")
    if macro_recall is not None:
        print(f"{'Macro Recall':<20}{macro_recall:.4f}   Macro recall across families")
    if macro_f1 is not None:
        print(f"{'Macro F1':<20}{macro_f1:.4f}   Primary multiclass family-balance signal")

    _print_interpretation(macro_f1 if macro_f1 is not None else f1)

    # Confusion matrix path is reported by the exporter and callers.


def export_classification_summary(df: pd.DataFrame, output_path: str, file_format: str = "xlsx"):
    """Export classification summary to xlsx or txt."""
    try:
        if file_format == "xlsx":
            df.to_excel(output_path, index=False)
        elif file_format == "txt":
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("Malware Family Classification Report\n")
                f.write("=" * 90 + "\n")
                f.write(
                    f"{'Rank':<6}{'Family':<18}{'Precision':>10}{'Recall':>10}"
                    f"{'F1-Score':>10}{'Support':>10}   {'Status'}\n"
                )
                f.write("-" * 90 + "\n")
                for _, row in df.iterrows():
                    f.write(
                        f"{row['Rank']:<6}{row['Family']:<18}{row['Precision']:>10.4f}"
                        f"{row['Recall']:>10.4f}{row['F1-Score']:>10.4f}{row['Support']:>10}   {row['Status']}\n"
                    )
                f.write("\nPerformance Tiers:\n")
                for tier in accuracy_band_utils.list_accuracy_bands():
                    f.write(f" - {tier}\n")
        else:
            du.print_warning(f"Unsupported export format '{file_format}'. Use 'xlsx' or 'txt'.")
            return
        du.print_success(f"Classification report exported to: {output_path}")
    except Exception as e:
        du.print_error(f"[EXPORT FAILED] Unable to export summary: {e}")


def _print_interpretation(f1: float):
    """Print overall F1 interpretation tier."""
    from obsidiandroid.evaluation.ml_terminal_presentation import tier_code_only, tier_readable

    print("\nInterpretation Summary:")
    tier_code = tier_code_only(accuracy_band_utils.evaluate_accuracy_band(f1))
    readable = tier_readable(accuracy_band_utils.evaluate_accuracy_band(f1))
    if f1 >= 0.75:
        du.print_success(f"{tier_code} — {readable}.")
    elif f1 >= 0.60:
        du.print_warning(f"{tier_code} — {readable}.")
    else:
        du.print_warning(f"{tier_code} — {readable}; review features and label balance.")
