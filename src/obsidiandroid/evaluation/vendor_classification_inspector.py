# Filename: vendor_classifications_inspector.py
# Description: Vendor score dashboard with summary analytics (production version)

import os
import pandas as pd

EXPORT_RESULTS = False  # Set to True to enable export
EXPORT_PATH = "output/diagnostics/vendor_score_dashboard.txt"

# Fixed console width for consistent formatting
CONSOLE_WIDTH = 99
HLINE = "=" * CONSOLE_WIDTH

# ------------------ Core Analysis Functions ------------------

def resolve_score_column(df: pd.DataFrame) -> str:
    for col in ["Final ML Score", "Composite Score", "Enrichment Score", "Intelligence Score"]:
        if col in df.columns:
            return col
    return None


def print_summary_table(summary_df: pd.DataFrame, top_n=None, sort_by=None, descending=True, verbose=False):
    if summary_df is None or summary_df.empty:
        return

    score_col = resolve_score_column(summary_df)
    if not score_col:
        return

    df = summary_df.copy()

    if sort_by is None:
        sort_by = score_col
    if sort_by in df.columns:
        df = df.sort_values(by=sort_by, ascending=not descending)
    if top_n:
        df = df.head(top_n)

    df["Tier"] = pd.cut(
        df[score_col],
        bins=[-1, 0.25, 0.7, 1.0],
        labels=["Tier 3 (Low)", "Tier 2 (Acceptable)", "Tier 1 (High)"]
    )

    if EXPORT_RESULTS:
        export_summary(df)

def export_summary(df: pd.DataFrame):
    try:
        os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)
        with open(EXPORT_PATH, "w", encoding="utf-8") as f:
            f.write("Vendor Score Dashboard Export\n")
            f.write("=" * 40 + "\n\n")
            f.write(df.to_string(index=False))
    except Exception:
        pass

