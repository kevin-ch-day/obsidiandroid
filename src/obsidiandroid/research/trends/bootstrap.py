"""Batch-resampled 95 % bands, vectorized and deterministic.

Statistics are ratios Σ(indicator·weight)/Σ(weight) over rows. Per-batch numerators and denominators are precomputed once,
then batches are resampled with replacement (``n_resamples`` draws, ``numpy.random.default_rng(seed)``). Fewer than
``min_batches`` distinct batches → no band (NaN) and ``n_batches`` reported.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_RESAMPLES = 1000
DEFAULT_SEED = 20261115


def per_batch_sums(indicators: np.ndarray, weights: np.ndarray, batches: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """indicators: (n_rows, k) 0/1 matrix; weights: (n_rows,); batches: (n_rows,) labels.
    Returns (labels, num (B,k), den (B,))."""
    labels, inverse = np.unique(batches, return_inverse=True)
    num = np.zeros((len(labels), indicators.shape[1])); den = np.zeros(len(labels))
    np.add.at(num, inverse, indicators * weights[:, None]); np.add.at(den, inverse, weights)
    return labels, num, den


def ratio_bands(num: np.ndarray, den: np.ndarray, n_resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED, min_batches: int = 2) -> dict:
    """Bands for k statistics at once. Returns dict(lo, hi, point, n_batches)."""
    b = num.shape[0]
    point = num.sum(axis=0) / den.sum() if den.sum() > 0 else np.full(num.shape[1], np.nan)
    if b < min_batches:
        return {"lo": np.full(num.shape[1], np.nan), "hi": np.full(num.shape[1], np.nan), "point": point, "n_batches": int(b)}
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, b, size=(n_resamples, b))
    counts = np.zeros((n_resamples, b))
    for r in range(n_resamples):
        counts[r] = np.bincount(picks[r], minlength=b)
    res_num = counts @ num; res_den = counts @ den
    with np.errstate(invalid="ignore", divide="ignore"):
        stats = res_num / res_den[:, None]
    return {"lo": np.nanpercentile(stats, 2.5, axis=0), "hi": np.nanpercentile(stats, 97.5, axis=0), "point": point, "n_batches": int(b)}


def frame_bands(frame: pd.DataFrame, indicator_cols: list[str], weight_col: str, batch_col: str = "batch", **kw) -> pd.DataFrame:
    """Convenience: bands for indicator columns of a frame restricted to rows with a weight."""
    sub = frame[frame[weight_col].notna()]
    if len(sub) == 0:
        return pd.DataFrame({"indicator": indicator_cols, "point": np.nan, "lo": np.nan, "hi": np.nan, "n_batches": 0})
    labels, num, den = per_batch_sums(sub[indicator_cols].to_numpy(dtype=float), sub[weight_col].to_numpy(dtype=float), sub[batch_col].to_numpy())
    out = ratio_bands(num, den, **kw)
    return pd.DataFrame({"indicator": indicator_cols, "point": out["point"], "lo": out["lo"], "hi": out["hi"], "n_batches": out["n_batches"]})
