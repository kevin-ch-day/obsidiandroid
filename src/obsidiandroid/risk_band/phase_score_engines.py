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

NEAR_MISS_RELATIVE_MARGIN = 0.8

def assign_detection_tier(coverage_pct, detection_pct):
    for tier, limits in TIER_LEVELS.items():
        if coverage_pct >= limits["min_coverage"] and detection_pct >= limits["min_detection"]:
            return tier
    return "Tier 5"


def _check_threshold_failures(
    *,
    coverage: int,
    coverage_pct: float,
    detections: int,
    detection_pct: float,
    min_required: int,
    min_coverage_pct: float,
    min_positive_flags: int,
    min_detection_pct: float,
    exclude_zero_detection: bool,
) -> list[str]:
    failures: list[str] = []
    if coverage < min_required:
        failures.append("samples_scanned")
    if coverage_pct < min_coverage_pct:
        failures.append("coverage_pct")
    if exclude_zero_detection and detections <= 0:
        failures.append("zero_detections")
    if detections < min_positive_flags:
        failures.append("positive_flags")
    if detection_pct < min_detection_pct:
        failures.append("detection_pct")
    return failures


def _is_near_miss(
    *,
    threshold_failures: list[str],
    coverage: int,
    coverage_pct: float,
    detections: int,
    detection_pct: float,
    min_required: int,
    min_coverage_pct: float,
    min_positive_flags: int,
    min_detection_pct: float,
    exclusion_reason: str,
) -> bool:
    if exclusion_reason in {"metadata_filter", "zero_detections"}:
        return False
    if len(threshold_failures) != 1:
        return False
    failure = threshold_failures[0]
    if failure == "samples_scanned":
        return min_required > 0 and coverage >= max(1, int(min_required * NEAR_MISS_RELATIVE_MARGIN))
    if failure == "coverage_pct":
        return min_coverage_pct > 0 and coverage_pct >= (min_coverage_pct * NEAR_MISS_RELATIVE_MARGIN)
    if failure == "positive_flags":
        return min_positive_flags > 0 and detections >= max(1, int(min_positive_flags * NEAR_MISS_RELATIVE_MARGIN))
    if failure == "detection_pct":
        return min_detection_pct > 0 and detection_pct >= (min_detection_pct * NEAR_MISS_RELATIVE_MARGIN)
    return False

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
        threshold_failures = _check_threshold_failures(
            coverage=coverage,
            coverage_pct=coverage_pct,
            detections=detections,
            detection_pct=detection_pct,
            min_required=min_required,
            min_coverage_pct=min_coverage_pct,
            min_positive_flags=min_positive_flags,
            min_detection_pct=min_detection_pct,
            exclude_zero_detection=exclude_zero_detection,
        )
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
        near_miss = _is_near_miss(
            threshold_failures=threshold_failures,
            coverage=coverage,
            coverage_pct=coverage_pct,
            detections=detections,
            detection_pct=detection_pct,
            min_required=min_required,
            min_coverage_pct=min_coverage_pct,
            min_positive_flags=min_positive_flags,
            min_detection_pct=min_detection_pct,
            exclusion_reason=exclusion_reason,
        )

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
            "Threshold Fail Count": len(threshold_failures),
            "Threshold Failed Checks": "|".join(threshold_failures) if threshold_failures else "",
            "Near Miss": bool(near_miss),
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
