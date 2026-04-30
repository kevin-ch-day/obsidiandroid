# Filename: ml_classification/build_classification_weights.py
# Purpose : Compute ML-ready AV engine weight scores using detection performance and optional label metadata

import pandas as pd
import sys
from utils import display_utils as du
from . import classification_weight_utils as cwutils
from . import classification_weight_inspector as inspector
from . import compute_reliability_score as reliability_score
from . import assign_detection_tiers as detection_tiers
from . import engine_weights_utils as ewu

# Calculate final weight score
def compute_weight_scores(df: pd.DataFrame, use_metadata: bool, use_zscore: bool = True) -> pd.DataFrame:
    return cwutils.calculate_ml_weight(df, use_metadata=use_metadata, use_zscore=use_zscore)

# Analyze and summarize final AV engine classification results
def analyze_and_display(df: pd.DataFrame, verbose: bool = True):
    if not verbose or df.empty:
        return

    du.print_section("AV Engine Classification Evaluation Summary")

    # Core breakdowns
    if "ML Weight Score" in df.columns:
        try:
            stats = df["ML Weight Score"].describe()
            du.print_metric_summary({
                "ML Score - Min": stats["min"],
                "ML Score - Max": stats["max"],
                "ML Score - Mean": stats["mean"],
                "ML Score - Std Dev": stats["std"],
                "ML Score - 25%": stats["25%"],
                "ML Score - Median": stats["50%"],
                "ML Score - 75%": stats["75%"]
            }, title="ML Weight Score Distribution")

            if stats['std'] < 0.2:
                du.print_warning("Low variance in ML scores — feature weighting may be weak or uninformative.")
        except Exception as e:
            du.print_warning(f"[SUMMARY] Failed to compute ML weight statistics: {e}")
    else:
        du.print_warning("[SUMMARY] 'ML Weight Score' column is missing.")

    # Tiers
    if "Detection Tier" in df.columns:
        du.print_distribution(df["Detection Tier"], label="Detection Tier Distribution")

    if "Tier Label" in df.columns:
        du.print_distribution(df["Tier Label"], label="Assigned Tier Labels")

    # Reliability
    if "Reliability Band" in df.columns:
        du.print_distribution(df["Reliability Band"], label="Reliability Band Distribution")

    # Submodule visual summaries
    inspector.print_engine_weight_summary(df)
    inspector.print_top_ranked_engines(df, top_n=10)
    inspector.print_ml_tier_quality_insights(df)
    inspector.print_outlier_engines(df, lower=0.1, upper=0.9)

# Build the AV engine score classification output
def build_av_engine_classification_weights(
    performance_df: pd.DataFrame,
    label_metadata: dict = None,
    normalize: bool = True,
    verbose: bool = True
) -> pd.DataFrame:
    required = {"Engine", "Detection Rate", "Coverage %", "Tier Score"}
    if not ewu.validate_input_columns(performance_df, required, context="AV Engine Performance"):
        return pd.DataFrame()

    try:
        df = performance_df.copy()

        if normalize:
            du.print_info("[STEP] Normalizing input features")
            df = ewu.normalize_base_indicators(df, use_zscore=True)

        du.print_info("[STEP] Computing reliability score")
        df = reliability_score.compute_reliability(df, verbose=verbose)

        if label_metadata:
            du.print_info("[STEP] Adding label metadata enrichment")
            df = ewu.add_metadata_fields(df, label_metadata)
            df = compute_weight_scores(df, use_metadata=True, use_zscore=True)
        else:
            du.print_info("[STEP] Computing ML weights (no metadata)")
            df = compute_weight_scores(df, use_metadata=False, use_zscore=True)

        du.print_info("[STEP] Assigning detection tiers")
        df_results = detection_tiers.classify_detection_performance(df, verbose=verbose)

        df_sorted = df_results.sort_values("ML Weight Score", ascending=False).reset_index(drop=True)
        analyze_and_display(df_sorted, verbose)

        base_cols = [
            "Engine", "Detection Rate", "Coverage %", "Tier Score",
            "Detection Rate (Norm)", "Coverage % (Norm)", "Tier Score (Norm)",
            "Detection Rate (Z)", "Coverage % (Z)", "Tier Score (Z)",
            "Reliability", "Reliability_z", "Reliability Band",
            "ML Weight Score", "Detection Tier"
        ]

        if label_metadata:
            enriched_cols = [
                "Label Diversity", "Named Family Hits",
                "Label Diversity (Norm)", "Family Specificity (Norm)"
            ]
            final_df = df_sorted[base_cols[:4] + enriched_cols + base_cols[4:]]
        else:
            final_df = df_sorted[base_cols]

        if final_df["ML Weight Score"].isnull().any():
            du.print_error("[FATAL] One or more ML scores are null. Aborting.")
            sys.exit(1)

        return final_df

    except Exception as e:
        du.print_error(f"[WEIGHTS] Exception during ML weight computation: {e}")
        return pd.DataFrame()
