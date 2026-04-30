# Filename: analysis/matrix/enrich_score_features.py
# Purpose  : Adds enriched risk score features and insight labels to AV detection matrix

import pandas as pd
from analysis.risk_band import assign_risk_band

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
        # Parse required numeric fields with safety
        df["malicious_engines"] = pd.to_numeric(df["malicious_engines"], errors="coerce").fillna(0.0)
        df["total_engines"] = pd.to_numeric(df["total_engines"], errors="coerce").replace(0, 1)
        df["malicious_pct"] = pd.to_numeric(df["malicious_pct"], errors="coerce").fillna(0.0)

        # Derived ratio and detection labels
        df["malicious_ratio"] = df["malicious_engines"] / df["total_engines"]
        df["is_high_consensus"] = (df["malicious_pct"] >= 90).astype(int)
        df["detection_band"] = df["malicious_pct"].apply(_pct_to_label)
        df["detection_flag"] = (df["malicious_engines"] > 0).astype(int)
        df["detection_density"] = df["malicious_engines"] / df["total_engines"]
        df["engine_diversity"] = df["total_engines"].apply(lambda x: "Broad" if x > 60 else "Limited")

        # Risk scoring formula (weighted)
        confidence_weights = {"High": 3, "Medium": 2, "Low": 1, "Minimal": 0}
        df["risk_score"] = (
            df["malicious_engines"] * 2 +
            df["detection_confidence"].map(confidence_weights).fillna(0)
        )

        # Apply band/rank from analysis.risk_band
        df["risk_band"] = assign_risk_band.compute_risk_bands_from_scores(df)
        df["risk_rank"] = df["risk_score"].rank(method="dense", ascending=False).astype(int)

        # Reorder columns: base + derived
        derived = [
            "malicious_ratio", "is_high_consensus", "detection_band", "detection_flag",
            "detection_density", "engine_diversity", "risk_score", "risk_band", "risk_rank"
        ]
        base = [col for col in df.columns if col not in derived]
        df = df[base + derived]

        validate_score_enrichment(df)

    except Exception as e:
        raise RuntimeError(f"Score feature enrichment failed: {e}")

    return df
