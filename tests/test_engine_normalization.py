"""Tests for engine canonicalization logic."""

from obsidiandroid.pipeline import engine_normalization
from obsidiandroid.engine_weights import classification_weight_utils as cwutils
from obsidiandroid.engine_weights import compute_reliability_score as crs
import pandas as pd


def test_canonicalize_engine_name_basic_rules() -> None:
    """Normalization should collapse casing/punctuation/version suffix."""
    aliases = {}
    assert engine_normalization.canonicalize_engine_name("Avast-Mobile", aliases) == "avast_mobile"
    assert engine_normalization.canonicalize_engine_name("AVAST mobile", aliases) == "avast_mobile"
    assert engine_normalization.canonicalize_engine_name("kaspersky 2", aliases) == "kaspersky"


def test_engine_hash_is_stable() -> None:
    """Engine hash must be deterministic for canonical slug."""
    h1 = engine_normalization.compute_engine_hash("kaspersky")
    h2 = engine_normalization.compute_engine_hash("kaspersky")
    assert h1 == h2
    assert len(h1) == 12


def test_alias_can_preserve_numeric_vendor_key() -> None:
    """Alias targets that include numeric tokens should not be stripped."""
    aliases = {"qihoo": "qihoo_360"}
    assert engine_normalization.canonicalize_engine_name("qihoo", aliases) == "qihoo_360"


def test_legitimate_numeric_suffix_is_preserved() -> None:
    """Numeric vendor keys with meaningful suffixes should remain intact."""
    assert engine_normalization.canonicalize_engine_name("qihoo_360", {}) == "qihoo_360"


def test_zscore_columns() -> None:
    df = pd.DataFrame({"A": [1, 2, 3, 4]})
    df = cwutils.zscore_columns(df, {"A": "A_z"})
    assert "A_z" in df.columns
    assert abs(df["A_z"].mean()) < 1e-6
    assert round(df["A_z"].iloc[0], 4) == round((1 - df["A"].mean()) / df["A"].std(), 4)


def test_compute_reliability_with_zscore() -> None:
    data = {
        "Detection Rate (Norm)": [0.8],
        "Coverage % (Norm)": [0.7],
        "Tier Score (Norm)": [0.6],
        "Detection Rate (Z)": [0.5],
        "Coverage % (Z)": [0.2],
        "Tier Score (Z)": [0.1],
    }
    df = pd.DataFrame(data)
    result = crs.compute_reliability(df.copy(), verbose=False)
    assert "Reliability" in result.columns
    assert result["Reliability"].iloc[0] > 0
