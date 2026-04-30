# Filename: av_feature_engineering.py
# Purpose  : Normalize AV engine scores and compute ML feature weights for scoring AV engines

import pandas as pd
from ml_classification.engine_weights import build_classification_weights
from analysis.feature_engineering.assign_tier_scores import assign_tier_scores

EXPORT_NORMALIZED_METRICS_PATH = "output/normalized_engine_metrics.xlsx"
EXPORT_WEIGHT_TABLE_PATH = "output/engine_feature_weights.xlsx"

WEIGHT_SCORE_FIELD = "ML Weight Score"
ENGINE_ID_FIELD = "Engine"

# Main entry function to compute weights for AV engines based on coverage and detection performance
def compute_vendor_scores(pipeline_results: dict, verbose: bool = False) -> pd.DataFrame:
    engine_scores_df = pipeline_results.get("engine_scores")
    engine_summary_df = pipeline_results.get("engine_summary")

    if engine_scores_df is None or engine_summary_df is None:
        return pd.DataFrame()

    merged_df = _prepare_combined_metrics(engine_scores_df, engine_summary_df)
    if merged_df.empty:
        return pd.DataFrame()

    merged_df = _apply_tier_assignment(merged_df)
    merged_df = _apply_quality_flags(merged_df)

    _export_dataframe(merged_df, EXPORT_NORMALIZED_METRICS_PATH)

    try:
        weight_table = build_classification_weights.build_av_engine_classification_weights(
            performance_df=merged_df,
            label_metadata=None,
            normalize=True,
            verbose=False
        )
    except Exception:
        return pd.DataFrame()

    if weight_table.empty:
        return pd.DataFrame()

    _export_dataframe(weight_table, EXPORT_WEIGHT_TABLE_PATH)
    return weight_table

# Prepare and merge detection rate and coverage % into a unified DataFrame
def _prepare_combined_metrics(engine_scores_df: pd.DataFrame, engine_summary_df: pd.DataFrame) -> pd.DataFrame:
    left = engine_scores_df.rename(columns={"Engine Name": "Engine", "Detection %": "Detection Rate"})[
        ["Engine", "Detection Rate"]
    ]
    right = engine_summary_df.rename(columns={"engine_name": "Engine", "coverage_pct": "Coverage %"})[
        ["Engine", "Coverage %"]
    ]
    return pd.merge(left, right, on="Engine", how="inner")

# Assign scoring tier labels based on performance thresholds
def _apply_tier_assignment(df: pd.DataFrame) -> pd.DataFrame:
    return assign_tier_scores(df, verbose=False)

# Flag engines with poor visibility (<20% coverage)
def _apply_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    df["low_coverage_flag"] = (df["Coverage %"] < 20.0).astype(int)
    return df

# Export the DataFrame to an Excel file silently
def _export_dataframe(df: pd.DataFrame, path: str):
    try:
        df.to_excel(path, index=False)
    except Exception:
        pass
