# Filename: analysis/assign_risk_band.py
# Purpose : Assigns a categorical risk band to each sample based on its risk_score using either quantile or range-based methods.

import pandas as pd

from obsidiandroid.risk_band.risk_band_config import RiskBandConfig

# Risk band severity scores for sorting or visualization
RISK_BAND_SEVERITY = {
    "Low": 1,
    "Moderate": 2,
    "Elevated": 3,
    "Critical": 4,
    "Unclassified": 0
}


def _resolve_quantile_labels(scores: pd.Series, config: RiskBandConfig) -> tuple:
    """
    Determine quantile bin count and corresponding labels.
    Falls back gracefully if the score distribution is too narrow.
    """
    try:
        _, bin_edges = pd.qcut(scores, q=config.fallback_bin_count, retbins=True, duplicates="drop")
        actual_bins = len(bin_edges) - 1
        expected_labels = len(config.fallback_labels)

        if actual_bins < 2:
            raise ValueError("Score range too narrow — only one bin detected.")

        if actual_bins > expected_labels:
            raise ValueError(f"Not enough fallback labels ({expected_labels}) for {actual_bins} bins.")

        return actual_bins, config.fallback_labels[:actual_bins]
    except Exception as e:
        raise ValueError(f"[Quantile Labeling] Failed to resolve bins: {e}")


def _try_quantile_binning(scores: pd.Series, config: RiskBandConfig) -> pd.Series:
    """
    Attempt to assign risk bands using quantile-based binning.
    """
    bins, labels = _resolve_quantile_labels(scores, config)
    return pd.qcut(scores, q=bins, labels=labels, duplicates="drop")


def _try_fallback_binning(scores: pd.Series, config: RiskBandConfig) -> pd.Series:
    """
    Use static or dynamic ranges to assign risk bands.
    """
    min_score, max_score = scores.min(), scores.max()

    if min_score == max_score:
        # All scores are the same, fallback to uniform label
        fallback = "Unclassified" if config.include_unclassified else "Critical"
        return pd.Series([fallback] * len(scores), index=scores.index)

    if config.use_dynamic_bins:
        # Compute equally spaced dynamic ranges
        step = (max_score - min_score) / config.fallback_bin_count
        bin_edges = [min_score - 1] + [
            min_score + i * step for i in range(1, config.fallback_bin_count)
        ] + [float("inf")]
    else:
        # Use static edges defined in config or default
        bin_edges = config.static_bin_edges or [-1, 20, 60, 100, float("inf")]

    try:
        labels = config.fallback_labels[:len(bin_edges) - 1]
        return pd.cut(scores, bins=bin_edges, labels=labels)
    except Exception:
        fallback = "Unclassified" if config.include_unclassified else "Critical"
        return pd.Series([fallback] * len(scores), index=scores.index)


def compute_risk_bands_from_scores(df: pd.DataFrame, config: RiskBandConfig = RiskBandConfig()) -> pd.Series:
    """
    Compute a categorical risk band column for a DataFrame using the 'risk_score' column.
    """
    try:
        config.validate_labels()
        scores = df["risk_score"].fillna(0).astype(float)

        if len(scores.unique()) < config.min_bins_required and config.method != "static":
            raise ValueError("Too few unique scores for quantile binning. Using fallback method.")

        if config.method in ("quantile", "auto"):
            try:
                return _try_quantile_binning(scores, config)
            except Exception as quantile_err:
                if config.method == "quantile":
                    raise ValueError(f"Quantile binning failed: {quantile_err}")
                # Fall back if 'auto' mode
                pass

        # Fallback mode
        return _try_fallback_binning(scores, config)

    except Exception:
        fallback = "Unclassified" if config.include_unclassified else "Critical"
        return pd.Series([fallback] * len(df), index=df.index)
