# Filename: ml_classification/classification_weight_inspector.py
# Description: Evaluation and insight generation for ML-scored AV engines

import pandas as pd
from utils import display_utils as du

def print_engine_weight_summary(df: pd.DataFrame):
    if df.empty or "ML Weight Score" not in df.columns:
        print("[ERROR] Missing 'ML Weight Score' — cannot summarize.")
        return

    print("\n[SUMMARY] AV Engine ML Scoring Metrics")
    print("=" * 110)

    du.print_metric_summary({
        "Total Engines Evaluated": len(df),
        "ML Score Range": f"{df['ML Weight Score'].min():.4f} → {df['ML Weight Score'].max():.4f}",
        "Average ML Score": df["ML Weight Score"].mean(),
        "ML Score Std Dev": df["ML Weight Score"].std(),
        "Average Detection Rate (%)": df["Detection Rate"].mean(),
        "Average Coverage %": df["Coverage %"].mean(),
        "Tier Score Range": f"{df['Tier Score'].min()} → {df['Tier Score'].max()}" if "Tier Score" in df else "N/A"
    })
    
    print("=" * 110)


def print_top_ranked_engines(df: pd.DataFrame, top_n: int = 10):
    if df.empty or "ML Weight Score" not in df.columns:
        print("[WARNING] Cannot show top engines — missing 'ML Weight Score'")
        return

    top = df.sort_values(by="ML Weight Score", ascending=False).head(top_n).reset_index(drop=True)

    print(f"\n[TOP ENGINES] ML-Ranked Antivirus Engines (Top {top_n})")
    print("-" * 100)
    print(f"{'Rank':<5} {'Engine':<24} {'Score':>10}   {'Tier Label':<18} {'Reliability'}")
    print("-" * 100)

    for i, row in top.iterrows():
        print(f"{i+1:<5} {row['Engine']:<24} {row['ML Weight Score']:>10.4f}   "
              f"{row.get('Tier Label', 'N/A'):<18} {row.get('Reliability', 'N/A')}")
    print("-" * 100)


def print_ml_tier_quality_insights(df: pd.DataFrame):
    if df.empty or "ML Weight Score" not in df.columns:
        print("[ERROR] Cannot segment quality tiers — 'ML Weight Score' missing.")
        return

    high = df[df["ML Weight Score"] >= 0.75]
    mid = df[(df["ML Weight Score"] >= 0.25) & (df["ML Weight Score"] < 0.75)]
    low = df[df["ML Weight Score"] < 0.25]

    print("\n[INSIGHTS] ML-Based Engine Tier Segmentation")
    print("-" * 80)
    print(f"  High-Quality Engines  (≥ 0.75) : {len(high)}")
    print(f"  Medium-Quality Engines         : {len(mid)}")
    print(f"  Low-Quality Engines    (< 0.25): {len(low)}")

    if not low.empty:
        print("  → Recommendation: Consider filtering or penalizing low-performing engines.")
    print("-" * 80)


def print_outlier_engines(df: pd.DataFrame, lower: float = 0.1, upper: float = 0.9):
    if df.empty or "ML Weight Score" not in df.columns:
        print("[WARNING] Cannot evaluate outliers — missing 'ML Weight Score'")
        return

    below = df[df["ML Weight Score"] < lower]
    above = df[df["ML Weight Score"] > upper]

    print("\n[OUTLIERS] ML Scoring Extremes")
    print("-" * 90)
    print(f"  Engines < {lower:.2f} Score Threshold : {len(below)}")
    print(f"  Engines > {upper:.2f} Score Threshold : {len(above)}")

    if not below.empty:
        print("\n  → Low-Scoring Engines (Noise Risks):")
        print(below[["Engine", "ML Weight Score", "Reliability"]].to_string(index=False))

    if not above.empty:
        print("\n  → High-Scoring Engines (Top Contributors):")
        print(above[["Engine", "ML Weight Score", "Reliability"]].to_string(index=False))

    print("-" * 90)
