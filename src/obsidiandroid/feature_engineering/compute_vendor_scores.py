# Filename: compute_vendor_scores.py
# Purpose : Derive ML-compatible scores from vendor classification evaluation summary

import pandas as pd
from obsidiandroid.cli.ui import display as du
from config import app_config
from obsidiandroid.common import ml_console
from obsidiandroid.common.cv_fold_config import safe_float_config_value, safe_int_config_value

REQUIRED_COLUMNS = [
    "Vendor", "Enrichment Score", "Family Match Accuracy (%)",
    "Detection Diversity", "Unknown Parsed (%)", "Unique Labels",
    "Generic Family Ratio", "Avg Genericity Score",
]

def run_score_analysis(summary_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Entry point for vendor scoring logic.
    Applies normalization, computes composite metrics, and tags vendors.
    Returns a DataFrame with final ML scores and vendor categories.
    """
    if verbose:
        du.print_info("[SCORING] Starting vendor ML score computation...")

    # Step 1: Validate input structure
    try:
        validate_input(summary_df)
    except Exception as e:
        raise ValueError(f"[SCORING] Input validation failed: {e}")

    # Step 2: Normalize required fields
    try:
        summary_df = normalize_numeric_fields(summary_df)
    except Exception as e:
        raise RuntimeError(f"[SCORING] Failed to normalize fields: {e}")

    # Step 3: Compute composite scores
    try:
        summary_df = compute_composite_scores(summary_df)
    except Exception as e:
        raise RuntimeError(f"[SCORING] Failed to compute composite scores: {e}")

    # Step 4: Add specificity and noise metrics
    try:
        summary_df = compute_specificity_and_noise(summary_df)
    except Exception as e:
        raise RuntimeError(f"[SCORING] Failed to compute specificity/noise scores: {e}")

    # Step 5: Compute genericity-derived features
    try:
        summary_df = compute_genericity_features(summary_df)
    except Exception as e:
        raise RuntimeError(f"[SCORING] Failed to compute genericity features: {e}")

    # Step 6: Final ML score calculation
    try:
        summary_df = compute_final_score(summary_df)
    except Exception as e:
        raise RuntimeError(f"[SCORING] Failed to compute final ML score: {e}")

    # Step 6b: Apply parser quality gates and effective weighting
    try:
        summary_df = apply_parser_quality_gates(summary_df)
    except Exception as e:
        raise RuntimeError(f"[SCORING] Failed to apply parser quality gates: {e}")

    # Step 7: Tag vendor classification categories
    try:
        summary_df = tag_vendor_categories(summary_df)
    except Exception as e:
        raise RuntimeError(f"[SCORING] Failed to tag vendor categories: {e}")

    # Step 8: Compute leakage-safe vendor score (label-independent)
    try:
        summary_df = compute_leakage_safe_score(summary_df)
    except Exception as e:
        raise RuntimeError(f"[SCORING] Failed to compute leakage-safe score: {e}")

    # Step 9: Display score distribution and top vendors
    if verbose:
        print_score_distribution(summary_df)
        print_debug_top_vendors(summary_df)

    return summary_df

# -----------------------------------------------------------------------------
# Step 1: Input Validation
# -----------------------------------------------------------------------------
def validate_input(df: pd.DataFrame):
    if df is None or not isinstance(df, pd.DataFrame):
        raise ValueError("[ERROR] Vendor summary must be a valid DataFrame.")
    if df.empty:
        raise ValueError("[ERROR] Vendor summary is empty. Cannot compute scores.")
    
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    for col in missing:
        df[col] = 0.0
        du.print_warning(f"[SCORING] Missing column '{col}' added with default 0.0")


# -----------------------------------------------------------------------------
# Step 2: Normalize Numeric Fields
# -----------------------------------------------------------------------------
def normalize_numeric_fields(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = [
        "Enrichment Score", "Family Match Accuracy (%)",
        "Detection Diversity", "Unknown Parsed (%)", "Unique Labels",
        "Generic Family Ratio", "Avg Genericity Score",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


# -----------------------------------------------------------------------------
# Step 3: Composite Score Computation
# -----------------------------------------------------------------------------
def compute_composite_scores(df: pd.DataFrame) -> pd.DataFrame:
    df["Score"] = (df["Enrichment Score"] / 100).round(4)

    df["Composite Score"] = (
        0.5 * df["Enrichment Score"] +
        0.3 * df["Family Match Accuracy (%)"] +
        0.2 * df["Detection Diversity"]
    ) / 100.0
    df["Composite Score"] = df["Composite Score"].round(4)

    return df


# -----------------------------------------------------------------------------
# Step 4: Specificity & Noise
# -----------------------------------------------------------------------------
def compute_specificity_and_noise(df: pd.DataFrame) -> pd.DataFrame:
    df["Specificity Score"] = (
        df["Detection Diversity"] / df["Unique Labels"]
    ).round(4).replace([float('inf'), -float('inf')], 0).fillna(0)

    df["Noise Penalty"] = (
        df["Unknown Parsed (%)"] + (100 - df["Family Match Accuracy (%)"])
    ) / 200.0

    return df


def compute_genericity_features(df: pd.DataFrame) -> pd.DataFrame:
    df["Genericity Penalty"] = (
        df.get("Generic Family Ratio", 0.0) + df.get("Avg Genericity Score", 0.0) / 100.0
    )
    return df


# -----------------------------------------------------------------------------
# Step 5: Final ML Score
# -----------------------------------------------------------------------------
def compute_final_score(df: pd.DataFrame) -> pd.DataFrame:
    df["Final ML Score"] = (
        0.6 * df["Composite Score"] +
        0.2 * df["Specificity Score"] -
        0.2 * df["Noise Penalty"] -
        0.1 * df.get("Genericity Penalty", 0.0)
    ).round(4)
    return df


def apply_parser_quality_gates(df: pd.DataFrame) -> pd.DataFrame:
    """Apply governance parser quality gates and effective weights."""
    unknown_cut = safe_float_config_value(
        getattr(app_config, "PARSER_UNKNOWN_EXCLUDE_THRESHOLD", 0.70), default=0.70
    )
    mapped_cut = safe_float_config_value(
        getattr(app_config, "PARSER_MAPPED_MIN_THRESHOLD", 0.30), default=0.30
    )
    generic_cut = safe_float_config_value(
        getattr(app_config, "PARSER_GENERIC_DOWNWEIGHT_THRESHOLD", 0.60), default=0.60
    )
    downweight = safe_float_config_value(
        getattr(app_config, "PARSER_GENERIC_DOWNWEIGHT_FACTOR", 0.50), default=0.50
    )
    min_included = safe_int_config_value(
        getattr(app_config, "PARSER_MIN_INCLUDED_VENDORS", 8), default=8
    )
    allow_relax_mapped = bool(getattr(app_config, "PARSER_ALLOW_RELAXED_MAPPED_GATE", True))
    strict_evidence_mode = bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False))

    df["mapped_ratio"] = (pd.to_numeric(df["Family Match Accuracy (%)"], errors="coerce").fillna(0.0) / 100.0).round(4)
    df["unknown_ratio"] = (pd.to_numeric(df["Unknown Parsed (%)"], errors="coerce").fillna(0.0) / 100.0).round(4)
    df["generic_ratio"] = pd.to_numeric(df.get("Generic Family Ratio", 0.0), errors="coerce").fillna(0.0).round(4)
    if "Normalized Entropy" not in df.columns:
        df["Normalized Entropy"] = 0.0
    df["entropy"] = pd.to_numeric(df["Normalized Entropy"], errors="coerce").fillna(0.0).round(4)

    effective_mapped_cut = float(mapped_cut)
    parser_gate_status = pd.Series("included", index=df.index, dtype="object")
    parser_gate_status.loc[df["unknown_ratio"] > unknown_cut] = "excluded_high_unknown"
    parser_gate_status.loc[df["mapped_ratio"] < effective_mapped_cut] = "excluded_low_mapped"

    if allow_relax_mapped and not strict_evidence_mode and min_included > 0:
        included_now = int((parser_gate_status == "included").sum())
        if included_now < min_included:
            candidates = df[df["unknown_ratio"] <= unknown_cut].copy()
            if not candidates.empty:
                target = min(min_included, int(candidates.shape[0]))
                relaxed_cut = float(candidates["mapped_ratio"].nlargest(target).min())
                if relaxed_cut < effective_mapped_cut:
                    effective_mapped_cut = max(0.0, relaxed_cut - 1e-6)
                    parser_gate_status = pd.Series("included", index=df.index, dtype="object")
                    parser_gate_status.loc[df["unknown_ratio"] > unknown_cut] = "excluded_high_unknown"
                    parser_gate_status.loc[df["mapped_ratio"] < effective_mapped_cut] = "excluded_low_mapped"
                    relaxed_mask = (
                        (df["unknown_ratio"] <= unknown_cut)
                        & (df["mapped_ratio"] >= effective_mapped_cut)
                        & (df["mapped_ratio"] < mapped_cut)
                    )
                    parser_gate_status.loc[relaxed_mask] = "included_relaxed_mapped"

    df["parser_mapped_cut_effective"] = round(float(effective_mapped_cut), 6)
    df["parser_gate_status"] = parser_gate_status
    df["downweight_factor"] = 1.0
    include_status_mask = df["parser_gate_status"].astype(str).str.startswith("included")
    mask_generic = (df["generic_ratio"] > generic_cut) & include_status_mask
    df.loc[mask_generic, "downweight_factor"] = downweight

    df["effective_weight"] = (
        pd.to_numeric(df["Final ML Score"], errors="coerce").fillna(0.0) * df["downweight_factor"]
    ).round(6)
    df.loc[df["parser_gate_status"] != "included", "effective_weight"] = 0.0
    include_mask = include_status_mask
    df["included_in_model"] = include_mask.astype(int)
    df.loc[~include_mask, "effective_weight"] = 0.0
    return df


def _minmax_scale(series: pd.Series) -> pd.Series:
    """Min-max scale a numeric series to [0, 1] with safe degenerate handling."""
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    min_v = float(values.min()) if not values.empty else 0.0
    max_v = float(values.max()) if not values.empty else 0.0
    if max_v <= min_v:
        return pd.Series([0.0] * len(values), index=values.index, dtype="float64")
    return ((values - min_v) / (max_v - min_v)).astype("float64")


def compute_leakage_safe_score(df: pd.DataFrame) -> pd.DataFrame:
    """Compute a vendor selection score that does not use ground-truth match fields.

    This score intentionally excludes family-match-derived columns such as
    ``Family Match Accuracy (%)`` and ``Enrichment Score``.
    """
    unknown_ratio = pd.to_numeric(df.get("unknown_ratio", 0.0), errors="coerce").fillna(0.0)
    generic_ratio = pd.to_numeric(df.get("generic_ratio", 0.0), errors="coerce").fillna(0.0)
    entropy = pd.to_numeric(df.get("entropy", 0.0), errors="coerce").fillna(0.0)
    diversity_norm = _minmax_scale(df.get("Detection Diversity", 0.0))
    specificity = (
        pd.to_numeric(df.get("Detection Diversity", 0.0), errors="coerce").fillna(0.0)
        / pd.to_numeric(df.get("Unique Labels", 1.0), errors="coerce").replace(0, 1).fillna(1.0)
    ).clip(lower=0.0, upper=1.0)

    # Weighted blend of parser behavior and signal diversity without truth labels.
    raw_score = (
        0.35 * (1.0 - unknown_ratio.clip(lower=0.0, upper=1.0))
        + 0.30 * (1.0 - generic_ratio.clip(lower=0.0, upper=1.0))
        + 0.20 * diversity_norm
        + 0.10 * entropy.clip(lower=0.0, upper=1.0)
        + 0.05 * specificity
    ).clip(lower=0.0, upper=1.0)
    df["Leakage Safe Score Raw"] = raw_score.round(6)
    df["Leakage Safe Score"] = raw_score

    # Respect parser inclusion contract for downstream feature selection.
    if "included_in_model" in df.columns:
        include_mask = pd.to_numeric(df["included_in_model"], errors="coerce").fillna(0).astype(int) == 1
        df.loc[~include_mask, "Leakage Safe Score"] = 0.0

    df["Leakage Safe Score"] = df["Leakage Safe Score"].round(6)
    return df


# -----------------------------------------------------------------------------
# Step 6: Vendor Category Tagging
# -----------------------------------------------------------------------------
def tag_vendor_categories(df: pd.DataFrame) -> pd.DataFrame:
    def classify(row):
        if row["Unknown Parsed (%)"] > 40:
            return "Too Generic"
        if row["Family Match Accuracy (%)"] < 10:
            return "Low Precision"
        if row["Detection Diversity"] > 20:
            return "High Diversity"
        return "Reliable"

    df["Vendor Category"] = df.apply(classify, axis=1)
    return df


# -----------------------------------------------------------------------------
# Step 8: Optional Debug Print
# -----------------------------------------------------------------------------
def print_debug_top_vendors(df: pd.DataFrame):
    if ml_console.is_compact():
        top = df.sort_values("Final ML Score", ascending=False)["Vendor"].astype(str).head(5).tolist()
        if top:
            du.print_info(f"[SCORING] Top vendors by Final ML Score: {', '.join(top)}")
        return
    du.print_section("Top Vendors by Final ML Score")
    du.print_table(
        df.sort_values("Final ML Score", ascending=False)[[
            "Vendor",
            "Final ML Score",
            "Composite Score",
            "Enrichment Score",
            "Family Match Accuracy (%)",
            "Detection Diversity",
            "Specificity Score",
            "Genericity Penalty",
            "Vendor Category",
        ]].head(10),
        show_index=False,
    )


def print_score_distribution(df: pd.DataFrame) -> None:
    """Display quartile statistics for final scores."""
    if "Final ML Score" not in df.columns or df.empty:
        du.print_warning("[SCORING] No score data to summarize.")
        return

    metrics = {
        "Min Score": df["Final ML Score"].min(),
        "25th Percentile": df["Final ML Score"].quantile(0.25),
        "Median Score": df["Final ML Score"].median(),
        "75th Percentile": df["Final ML Score"].quantile(0.75),
        "Max Score": df["Final ML Score"].max(),
    }
    du.print_metric_summary(metrics, title="Score Distribution")
