# Filename: phase_score_engines.py
# Description: Score AV engine performance and generate diagnostics for ML model contribution

import pandas as pd

# --------------------------------------------------------------------
# Tier definitions (customizable)
# --------------------------------------------------------------------
TIER_LEVELS = {
    "Tier 1": {"min_coverage": 95, "min_detection": 90},
    "Tier 2": {"min_coverage": 85, "min_detection": 75},
    "Tier 3": {"min_coverage": 60, "min_detection": 50},
    "Tier 4": {"min_coverage": 30, "min_detection": 25},
    "Tier 5": {"min_coverage": 0,  "min_detection": 0}
}

def assign_detection_tier(coverage_pct, detection_pct):
    for tier, limits in TIER_LEVELS.items():
        if coverage_pct >= limits["min_coverage"] and detection_pct >= limits["min_detection"]:
            return tier
    return "Tier 5"

# --------------------------------------------------------------------
# Core Scoring Logic
# --------------------------------------------------------------------
def compute_engine_scores(binary_df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
    engines = binary_df.drop(columns=["sample_id"])
    total_samples = len(binary_df)
    scan_counts = binary_df.attrs.get("engine_scan_counts", {}) if hasattr(binary_df, "attrs") else {}

    min_required = int(config.get("min_engine_detections", 10))
    min_coverage_pct = float(config.get("min_coverage_pct", 20.0))
    min_positive_flags = int(config.get("min_positive_flags", 5))
    min_detection_pct = float(config.get("min_detection_pct", 1.0))
    exclude_zero_detection = bool(config.get("exclude_zero_detection", True))
    trusted_only = config.get("trusted_only", False)
    active_only = config.get("active_only", True)

    engine_metadata = config.get("engine_metadata", {})
    stats = []

    for engine in engines.columns:
        col = engines[engine]
        detections = int(col.sum())
        coverage = int(scan_counts.get(engine, col.notnull().sum()))
        detection_pct = round((detections / coverage) * 100, 2) if coverage else 0.0
        coverage_pct = round((coverage / total_samples) * 100, 2)

        metadata = engine_metadata.get(engine, {})
        is_trusted = metadata.get("is_trusted_vendor", 1)
        is_active = metadata.get("is_engine_active", 1)

        skip = (trusted_only and not is_trusted) or (active_only and not is_active)
        exclusion_reason = ""
        if skip:
            exclusion_reason = "metadata_filter"
        elif coverage < min_required:
            exclusion_reason = "low_coverage"
        elif coverage_pct < min_coverage_pct:
            exclusion_reason = "low_coverage_pct"
        elif exclude_zero_detection and detections <= 0:
            exclusion_reason = "zero_detections"
        elif detections < min_positive_flags:
            exclusion_reason = "low_positive_flags"
        elif detection_pct < min_detection_pct:
            exclusion_reason = "low_detection_pct"

        included = exclusion_reason == ""
        ml_score = round((detection_pct / 100) * (coverage_pct / 100), 4) if included else 0.0
        tier = assign_detection_tier(coverage_pct, detection_pct) if included else "Excluded"

        stats.append({
            "Engine Name": engine,
            "Coverage %": coverage_pct,
            "Detection %": detection_pct,
            "Samples Scanned": coverage,
            "Malicious Flags": int(detections),
            "ML Weight Score": ml_score,
            "Detection Tier": tier,
            "Included": included,
            "Trusted": is_trusted,
            "Active": is_active,
            "Exclusion Reason": exclusion_reason if exclusion_reason else "included",
        })

    df = pd.DataFrame(stats)

    if not df.empty:
        ml_scores = df["ML Weight Score"]
        if ml_scores.max() > 0:
            df["Normalized Score"] = (ml_scores - ml_scores.min()) / (ml_scores.max() - ml_scores.min())
        else:
            df["Normalized Score"] = 0.0
        std = ml_scores.std(ddof=0)
        if std and std > 0:
            df["Z-Score"] = (ml_scores - ml_scores.mean()) / std
        else:
            df["Z-Score"] = 0.0
        df["Is Outlier"] = df["Z-Score"].abs() > 2

    return df

# --------------------------------------------------------------------
# Entry Point
# --------------------------------------------------------------------
def score_av_engines_from_matrix(binary_df: pd.DataFrame, config: dict = None, verbose: bool = False) -> pd.DataFrame:
    if config is None:
        config = {}

    if binary_df.empty or "sample_id" not in binary_df.columns:
        return pd.DataFrame()

    score_df = compute_engine_scores(binary_df, config=config)
    return score_df
