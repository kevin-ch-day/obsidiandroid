"""Tests for leakage-safe vendor scoring integration."""

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.feature_engineering import compute_vendor_scores


def test_compute_leakage_safe_score_excludes_non_included_vendors() -> None:
    """Leakage Safe Score should be zero when included_in_model is false."""
    df = pd.DataFrame(
        {
            "Vendor": ["a", "b"],
            "Enrichment Score": [10.0, 10.0],
            "Family Match Accuracy (%)": [10.0, 10.0],
            "Detection Diversity": [5.0, 8.0],
            "Unknown Parsed (%)": [10.0, 10.0],
            "Unique Labels": [20, 20],
            "Generic Family Ratio": [0.1, 0.1],
            "Avg Genericity Score": [0.2, 0.2],
            "Final ML Score": [0.4, 0.4],
            "unknown_ratio": [0.1, 0.1],
            "generic_ratio": [0.1, 0.1],
            "entropy": [0.6, 0.6],
            "included_in_model": [1, 0],
        }
    )

    out = compute_vendor_scores.compute_leakage_safe_score(df.copy())
    assert "Leakage Safe Score" in out.columns
    assert "Leakage Safe Score Raw" in out.columns
    assert out.loc[out["Vendor"] == "b", "Leakage Safe Score Raw"].iloc[0] > 0
    assert out.loc[out["Vendor"] == "a", "Leakage Safe Score"].iloc[0] > 0
    assert out.loc[out["Vendor"] == "b", "Leakage Safe Score"].iloc[0] == 0.0
