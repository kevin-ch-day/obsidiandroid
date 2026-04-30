# Filename: vendor_classification_scoring.py
# Purpose : Analyze vendor label consistency and generate scoring metrics for ML readiness

import pandas as pd
from utils import display_utils as du
from analysis.feature_engineering import compute_vendor_scores
from . import evaluate_av_classifications


def assess_vendor_classification_quality(av_summary_df: pd.DataFrame, sample_metadata_df: pd.DataFrame, verbose: bool = True) -> tuple:
    du.print_section("Vendor Classification Scoring Workflow")

    if not _validate_inputs(av_summary_df, sample_metadata_df):
        return {}, None, None, None

    classification_report = _run_classification_analysis(av_summary_df, sample_metadata_df, verbose)
    if not classification_report:
        return {}, {}, {}, pd.DataFrame()

    vendor_records, vendor_features, vendor_summary = _unpack_classification_report(classification_report)
    if vendor_summary.empty:
        du.print_error("Vendor metrics summary is empty.")
        return {}, vendor_records, vendor_features, pd.DataFrame()

    vendor_scores = _score_vendor_performance(vendor_summary, verbose)
    return classification_report, vendor_records, vendor_features, vendor_scores


def _validate_inputs(av_summary_df: pd.DataFrame, metadata_df: pd.DataFrame) -> bool:
    if av_summary_df.empty or metadata_df.empty:
        du.print_error("One or more input DataFrames are empty.")
        return False
    required = {"sample_id", "family_name"}
    if not required.issubset(metadata_df.columns):
        du.print_error(f"Missing required columns in sample metadata: {required - set(metadata_df.columns)}")
        return False
    return True


def _run_classification_analysis(av_df: pd.DataFrame, meta_df: pd.DataFrame, verbose: bool) -> dict:
    try:
        return evaluate_av_classifications.run_vendor_classification_analysis(
            samples_df=meta_df,
            export=True,
            verbose=verbose
        )
    except Exception as e:
        du.print_error(f"Classification analysis failed: {e}")
        return {}


def _unpack_classification_report(report: dict) -> tuple:
    records = report.get("records_by_vendor", {})
    features = report.get("parsed_data", {})
    summary_df = report.get("summary_df", pd.DataFrame())
    if not records:
        du.print_error("No vendor label records were parsed.")
    return records, features, summary_df


def _score_vendor_performance(summary_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    try:
        scores_df = compute_vendor_scores.run_score_analysis(summary_df, verbose=verbose)
        if scores_df.empty:
            du.print_error("Vendor scoring returned an empty DataFrame.")
            return pd.DataFrame()

        if verbose:
            _display_score_summary(scores_df, score_col="Final ML Score", label_col="Vendor")
        return scores_df
    except Exception as e:
        du.print_error(f"Vendor scoring failed: {e}")
        return pd.DataFrame()


def _display_score_summary(df: pd.DataFrame, score_col: str, label_col: str, threshold: float = 0.10, top_n: int = 5):
    if score_col not in df.columns or label_col not in df.columns:
        du.print_warning("Missing expected score or label columns.")
        return

    du.print_info(
        f"Score Range      : {df[score_col].min():.4f} → {df[score_col].max():.4f}"
    )
    du.print_info(f"Score Mean       : {df[score_col].mean():.4f}")
    du.print_info(f"Score Std Dev    : {df[score_col].std():.4f}")
    du.print_info(f"Top {top_n} Vendors by Score:")

    top_entries = df.sort_values(score_col, ascending=False).head(top_n)
    for _, row in top_entries.iterrows():
        du.print_info(f"  - {row[label_col]:25s} → {row[score_col]:.4f}")

    low_quality = df[df[score_col] < threshold]
    if not low_quality.empty:
        du.print_warning(
            f"Vendors below score threshold (< {threshold}): {len(low_quality)}"
        )
        for label in low_quality[label_col].tolist():
            du.print_warning(f"   - {label}")
