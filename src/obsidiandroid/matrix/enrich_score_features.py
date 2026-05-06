# Filename: obsidiandroid/matrix/enrich_score_features.py
# Purpose  : Adds enriched risk score features and insight labels to AV detection matrix

import pandas as pd

from obsidiandroid.risk_band import assign_risk_band

# Convert malicious detection % into qualitative detection confidence band
def _pct_to_label(pct: float) -> str:
    if pct >= 90:
        return "Critical"
    elif pct >= 70:
        return "Strong"
    elif pct >= 40:
        return "Moderate"
    elif pct > 0:
        return "Weak"
    return "None"

# Perform basic validation after enrichment
def validate_score_enrichment(df: pd.DataFrame):
    required_cols = {"sample_id", "risk_score", "risk_band"}
    if not required_cols.issubset(df.columns):
        raise ValueError("Enriched DataFrame missing one or more required fields.")
    if df["risk_score"].isnull().any():
        raise ValueError("Null values found in 'risk_score'.")
    if df["sample_id"].isnull().any():
        raise ValueError("Missing sample IDs in enriched output.")

# Main enrichment logic for detection matrix
def add_derived_score_features(df: pd.DataFrame) -> pd.DataFrame:
    try:
        # Parse required numeric fields with safety (Series to avoid repeated wide-frame inserts).
        me = pd.to_numeric(df["malicious_engines"], errors="coerce").fillna(0.0)
        te = pd.to_numeric(df["total_engines"], errors="coerce").replace(0, 1)
        mp = pd.to_numeric(df["malicious_pct"], errors="coerce").fillna(0.0)

        malicious_ratio = me / te
        is_high_consensus = (mp >= 90).astype(int)
        detection_band = mp.apply(_pct_to_label)
        detection_flag = (me > 0).astype(int)
        detection_density = me / te
        engine_diversity = te.apply(lambda x: "Broad" if x > 60 else "Limited")

        confidence_weights = {"High": 3, "Medium": 2, "Low": 1, "Minimal": 0}
        risk_score = me * 2 + df["detection_confidence"].map(confidence_weights).fillna(0)

        risk_band = assign_risk_band.compute_risk_bands_from_scores(
            pd.DataFrame({"risk_score": risk_score}, index=df.index)
        )
        risk_rank = risk_score.rank(method="dense", ascending=False).astype(int)

        enriched = pd.DataFrame(
            {
                "malicious_engines": me,
                "total_engines": te,
                "malicious_pct": mp,
                "malicious_ratio": malicious_ratio,
                "is_high_consensus": is_high_consensus,
                "detection_band": detection_band,
                "detection_flag": detection_flag,
                "detection_density": detection_density,
                "engine_diversity": engine_diversity,
                "risk_score": risk_score,
                "risk_band": risk_band,
                "risk_rank": risk_rank,
            },
            index=df.index,
        )

        replaced = {"malicious_engines", "total_engines", "malicious_pct"}
        base_cols = [c for c in df.columns if c not in replaced]
        result = pd.concat([df[base_cols], enriched], axis=1)

        # Reorder columns: base + derived (matches historical column ordering).
        derived_order = [
            "malicious_ratio",
            "is_high_consensus",
            "detection_band",
            "detection_flag",
            "detection_density",
            "engine_diversity",
            "risk_score",
            "risk_band",
            "risk_rank",
        ]
        base = [col for col in result.columns if col not in derived_order]
        result = result[base + derived_order]

        validate_score_enrichment(result)

    except Exception as e:
        raise RuntimeError(f"Score feature enrichment failed: {e}")

    return result
