# Filename: obsidiandroid/evaluation/ml_comparator_summary.py
# Purpose  : Summarize and rank ML models with clean formatting and interpretability for research clarity

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.evaluation import accuracy_band_utils

TARGET_F1_THRESHOLD = 0.80

_MODEL_DISPLAY_ALIASES = {
    "logistic_regression": "log_reg",
    "balanced_random_forest": "bal_rf",
    "random_forest": "rf",
    "xgboost": "xgb",
}

_RANK_METRIC_SPECS = {
    "macro_f1_score": ("Macro F1-Score", "MacroF1"),
    "f1_score": ("F1-Score", "WeightedF1"),
    "accuracy": ("Accuracy", "Accuracy"),
}


def _model_display_name(model_name: str, max_len: int = 16) -> str:
    """Return a compact, readable model label for terminal tables."""
    label = _MODEL_DISPLAY_ALIASES.get(model_name, model_name)
    if len(label) <= max_len:
        return label
    return f"{label[: max_len - 1]}…"


def _resolve_primary_metric_spec(rank_metric: str) -> tuple[str, str]:
    """Return dataframe column name and display label for the active primary metric."""
    return _RANK_METRIC_SPECS.get(rank_metric, _RANK_METRIC_SPECS["macro_f1_score"])


def compare_model_performance(results: dict) -> pd.DataFrame:
    """Build and print a ranked model comparison summary."""
    if not results or not isinstance(results, dict):
        du.print_error("No valid results dictionary provided. Aborting model comparison.")
        return pd.DataFrame()

    headline_split_meta = getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", None)
    split_hash_contract = ""
    if isinstance(headline_split_meta, dict):
        split_hash_contract = str(headline_split_meta.get("split_hash", "") or "")
    feature_hash_headline = str(getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or "")

    summary_rows = []
    for model_name, result in results.items():
        if not isinstance(result, dict):
            du.print_warning(f"Skipped '{model_name}': result is not a dictionary.")
            continue

        eval_data = result.get("evaluation")
        if not eval_data or not isinstance(eval_data, dict):
            du.print_warning(f"Skipped '{model_name}': missing or invalid evaluation block.")
            continue

        try:
            mdl = result.get("model") if isinstance(result, dict) else None
            fit_h = ""
            if mdl is not None and hasattr(mdl, "feature_names_in_"):
                fit_h = hash_payload(sorted(str(x) for x in mdl.feature_names_in_))
            summary_rows.append(
                {
                    "Model": model_name,
                    "Accuracy": round(eval_data.get("accuracy", 0.0), 4),
                    "Precision": round(eval_data.get("precision", 0.0), 4),
                    "Recall": round(eval_data.get("recall", 0.0), 4),
                    "F1-Score": round(eval_data.get("f1_score", 0.0), 4),
                    "Macro F1-Score": round(eval_data.get("macro_f1_score", 0.0), 4),
                    "Samples": eval_data.get("samples_tested", 0),
                    "Classes": eval_data.get("num_classes", "-"),
                    "split_hash": split_hash_contract,
                    "headline_feature_column_hash": feature_hash_headline,
                    "fit_feature_column_hash": fit_h,
                }
            )
        except Exception as exc:
            du.print_warning(f"Could not process metrics for '{model_name}': {exc}")

    if not summary_rows:
        du.print_error("No valid evaluation data found. Skipping comparison output.")
        return pd.DataFrame()

    df = pd.DataFrame(summary_rows)
    rank_metric = str(
        getattr(app_config, "MODEL_RANK_PRIMARY_METRIC", "macro_f1_score")
    ).strip().lower()
    if rank_metric not in _RANK_METRIC_SPECS:
        du.print_warning(
            f"Unknown MODEL_RANK_PRIMARY_METRIC='{rank_metric}'. Falling back to macro_f1_score."
        )
        rank_metric = "macro_f1_score"
    rank_col, rank_label = _resolve_primary_metric_spec(rank_metric)
    df["RankScore"] = df[rank_col]

    df["Rank"] = df["RankScore"].rank(ascending=False, method="min").astype(int)
    df.drop(columns=["RankScore"], inplace=True)
    df.sort_values("Rank", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df["Top"] = df["Rank"].apply(lambda r: "*" if r == 1 else "")
    df["Primary Metric"] = rank_metric
    df["Primary Metric Label"] = rank_label
    df["Primary Metric Score"] = df[rank_col]
    df["Primary Tier"] = df["Primary Metric Score"].map(accuracy_band_utils.evaluate_accuracy_band)
    df["Weighted Tier"] = df["F1-Score"].map(accuracy_band_utils.evaluate_accuracy_band)
    df["Accuracy Tier"] = df["Accuracy"].map(accuracy_band_utils.evaluate_accuracy_band)
    compact = bool(getattr(app_config, "ML_TERMINAL_COMPACT", True))
    show_guide = bool(getattr(app_config, "ML_SHOW_METRIC_GUIDE", False))

    du.print_section("Model Performance Summary (Ranked by Primary Metric)")
    display_df = df.copy()
    display_df["Model Label"] = display_df["Model"].astype(str).map(_model_display_name)
    display_df.rename(
        columns={
            "Macro F1-Score": "MacroF1",
            "F1-Score": "F1",
            "Accuracy": "Acc",
            "Primary Metric Label": "Metric",
            "Primary Tier": "Primary Tier",
            "Weighted Tier": "Weighted Tier",
            "Accuracy Tier": "Accuracy Tier",
        },
        inplace=True,
    )
    for col in ("Primary Tier", "Weighted Tier", "Accuracy Tier"):
        display_df[col] = (
            display_df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        )
    display_df["PrimaryTierCode"] = display_df["Primary Tier"].str.split(" - ", n=1).str[0]
    display_df["WeightedTierCode"] = display_df["Weighted Tier"].str.split(" - ", n=1).str[0]
    display_df["AccuracyTierCode"] = display_df["Accuracy Tier"].str.split(" - ", n=1).str[0]

    if compact:
        du.print_table(
            display_df[
                [
                    "Rank",
                    "Model Label",
                    "Metric",
                    "MacroF1",
                    "F1",
                    "Acc",
                    "PrimaryTierCode",
                    "Top",
                ]
            ],
            show_index=False,
            max_col_width=None,
            tablefmt="github",
        )
    else:
        du.print_table(
            display_df[["Rank", "Model Label", "MacroF1", "F1", "Top"]],
            show_index=False,
            max_col_width=18,
            tablefmt="github",
        )
        du.print_table(
            display_df[
                [
                    "Model Label",
                    "Metric",
                    "Acc",
                    "Precision",
                    "Recall",
                    "Primary Tier",
                    "Weighted Tier",
                    "Accuracy Tier",
                ]
            ],
            show_index=False,
            max_col_width=None,
            tablefmt="github",
        )

    if show_guide:
        du.print_info("Metric Guide:")
        du.print_info(" - Accuracy: Correct predictions across all labels.")
        du.print_info(" - Precision: Reliability of positive predictions.")
        du.print_info(" - Recall   : Sensitivity to true labels.")
        du.print_info(" - Macro F1 : Class-balanced F1 (recommended for imbalanced datasets).")
        du.print_info(
            " - F1-Score : Balance between Precision and Recall (preferred when class imbalance exists)."
        )

    top = df.iloc[0]
    runner_up_delta = None
    if len(df) > 1:
        runner_up_delta = float(top["Macro F1-Score"]) - float(df.iloc[1]["Macro F1-Score"])
    delta_txt = (
        f"  |  Gap(MacroF1 vs #2): {runner_up_delta:.4f}"
        if runner_up_delta is not None
        else ""
    )
    du.print_success(
        f"Top: {top['Model']}  |  "
        f"Primary metric: {rank_label}={float(top[rank_col]):.4f}  |  "
        f"Primary tier: {' '.join(str(top['Primary Tier']).split())}  |  "
        f"Weighted F1={top['F1-Score']:.4f} ({' '.join(str(top['Weighted Tier']).split())})  |  "
        f"Acc={top['Accuracy']:.4f} ({' '.join(str(top['Accuracy Tier']).split())})"
        f"{delta_txt}"
    )

    if bool(getattr(app_config, "ML_SHOW_IMPROVEMENT_OUTLOOK", False)):
        _print_improvement_outlook(df)

    return df


def _print_improvement_outlook(df: pd.DataFrame, threshold: float = TARGET_F1_THRESHOLD) -> None:
    """Display simple guidance showing how close each model is to the target F1 score."""
    du.print_section("Model Improvement Outlook")
    for _, row in df.iterrows():
        model = row["Model"]
        f1 = row["F1-Score"]
        delta = f1 - threshold
        if delta >= 0:
            du.print_success(f"{model}: meets target F1 (>={threshold:.2f}) with {f1:.2f}")
        else:
            du.print_warning(f"{model}: improve by {abs(delta):.2f} to reach {threshold:.2f}")
