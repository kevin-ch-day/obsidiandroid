"""Batch-resampled 95 % bands, vectorized and deterministic.

Two estimators are available and every table records which one it used:

``cluster_unit_recomputed`` (the registered estimator, pre-registration rule 3 + 4). Within each year the analysis unit is the
cluster (permission profile by default). Batches are resampled with replacement; on each resampled population the cluster
weights 1 / (rows in cluster) are **recomputed**, so every represented cluster carries exactly unit mass. For a cluster key
that determines the indicator (perm_profile_hash does: a profile either contains the permission or not) the statistic is the
share of *represented distinct clusters* containing the permission. For other keys (signer clusters) the statistic is
Σ_clusters mean(indicator over the cluster's resampled rows) / number of represented clusters.

``fixed_design``. Weights are computed once on the original population and resampled batches keep them (the D0 / trend v1
behaviour). A repeated batch then contributes more than unit mass per cluster. Retained as a documented alternative only.

Fewer than ``min_batches`` batches gives NaN bands.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_RESAMPLES = 1000
DEFAULT_SEED = 20261115
ESTIMATORS = ("cluster_unit_recomputed", "fixed_design")


def _resample_counts(n_batches: int, n_resamples: int, seed: int) -> np.ndarray:
    """(n_resamples, n_batches) multiplicity matrix of batches drawn with replacement."""
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, n_batches, size=(n_resamples, n_batches))
    counts = np.zeros((n_resamples, n_batches))
    for r in range(n_resamples):
        counts[r] = np.bincount(picks[r], minlength=n_batches)
    return counts


def per_batch_sums(indicators: np.ndarray, weights: np.ndarray, batches: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """indicators: (n_rows, k) 0/1 matrix; weights: (n_rows,); batches: (n_rows,) labels.
    Returns (labels, num (b, k), den (b,)) with fixed weights."""
    labels, inverse = np.unique(batches, return_inverse=True)
    num = np.zeros((len(labels), indicators.shape[1])); den = np.zeros(len(labels))
    np.add.at(num, inverse, indicators * weights[:, None]); np.add.at(den, inverse, weights)
    return labels, num, den


def ratio_bands(num: np.ndarray, den: np.ndarray, n_resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED, min_batches: int = 2) -> dict:
    """FIXED-DESIGN estimator: bands for k statistics from per-batch sums. Returns dict(lo, hi, point, n_batches, estimator)."""
    b = num.shape[0]
    point = num.sum(axis=0) / den.sum() if den.sum() > 0 else np.full(num.shape[1], np.nan)
    if b < min_batches:
        return {"lo": np.full(num.shape[1], np.nan), "hi": np.full(num.shape[1], np.nan), "point": point, "n_batches": int(b), "estimator": "fixed_design"}
    counts = _resample_counts(b, n_resamples, seed)
    res_num = counts @ num; res_den = counts @ den
    with np.errstate(invalid="ignore", divide="ignore"):
        stats = res_num / res_den[:, None]
    return {"lo": np.nanpercentile(stats, 2.5, axis=0), "hi": np.nanpercentile(stats, 97.5, axis=0), "point": point, "n_batches": int(b), "estimator": "fixed_design"}


def cluster_unit_bands(indicators: np.ndarray, clusters: np.ndarray, batches: np.ndarray, n_resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED, min_batches: int = 2) -> dict:
    """REGISTERED estimator: cluster weights recomputed on every resampled population.

    indicators (n_rows, k); clusters (n_rows,) cluster keys (rows without a key must be excluded by the caller);
    batches (n_rows,). Point estimate = Σ_c mean_c(indicator) / C on the original population (identical to the fixed-weight
    point estimate, since every cluster has unit mass there). Returns dict(lo, hi, point, n_batches, n_clusters, estimator,
    unit_mass_check) where unit_mass_check is the maximum absolute deviation of the resampled total mass from the number of
    represented clusters (0 by construction; retained as an explicit witness)."""
    labels_b, inv_b = np.unique(batches, return_inverse=True); labels_c, inv_c = np.unique(clusters, return_inverse=True)
    b, C, k = len(labels_b), len(labels_c), indicators.shape[1]
    # per (batch, cluster): row counts N and indicator sums S
    N = np.zeros((b, C)); np.add.at(N, (inv_b, inv_c), 1.0)
    S = np.zeros((b, C, k)); np.add.at(S, (inv_b, inv_c), indicators)
    n_c = N.sum(axis=0); s_c = S.sum(axis=0)                    # original population per cluster
    point = (s_c / n_c[:, None]).sum(axis=0) / C if C else np.full(k, np.nan)
    if b < min_batches:
        return {"lo": np.full(k, np.nan), "hi": np.full(k, np.nan), "point": point, "n_batches": int(b), "n_clusters": int(C), "estimator": "cluster_unit_recomputed", "unit_mass_check": 0.0}
    counts = _resample_counts(b, n_resamples, seed)              # (R, b)
    RN = counts @ N                                              # (R, C) resampled rows per cluster
    represented = RN > 0; n_rep = represented.sum(axis=1)        # (R,)
    stats = np.full((n_resamples, k), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        for j in range(k):                                       # (R, C) resampled indicator sums for permission j
            RS = counts @ S[:, :, j]
            cluster_mean = np.where(represented, RS / np.where(RN > 0, RN, 1.0), 0.0)
            stats[:, j] = cluster_mean.sum(axis=1) / n_rep
    mass = np.where(represented, 1.0, 0.0).sum(axis=1)           # recomputed weights give unit mass per represented cluster
    return {"lo": np.nanpercentile(stats, 2.5, axis=0), "hi": np.nanpercentile(stats, 97.5, axis=0), "point": point, "n_batches": int(b), "n_clusters": int(C),
            "estimator": "cluster_unit_recomputed", "unit_mass_check": float(np.abs(mass - n_rep).max())}


def bands_for(estimator: str, indicators: np.ndarray, weights: np.ndarray, clusters: np.ndarray | None, batches: np.ndarray, **kw) -> dict:
    """Dispatch on the estimator name. ``weights`` are the design weights (used by fixed_design and for modes without a
    cluster key such as raw / one_per_cluster, which fall back to fixed_design because their weights are not a cluster-size
    function); ``clusters`` are the cluster keys for the recomputed estimator."""
    if estimator not in ESTIMATORS:
        raise ValueError(f"unknown estimator {estimator!r}; expected one of {ESTIMATORS}")
    if estimator == "cluster_unit_recomputed" and clusters is not None:
        return cluster_unit_bands(indicators, clusters, batches, **kw)
    _, num, den = per_batch_sums(indicators, weights, batches)
    out = ratio_bands(num, den, **kw); out["n_clusters"] = int(len(np.unique(clusters))) if clusters is not None else 0
    if estimator == "cluster_unit_recomputed":
        out["estimator"] = "fixed_design(no cluster key for this weighting mode)"
    return out


def frame_bands(frame: pd.DataFrame, indicator_cols: list[str], weight_col: str, batch_col: str = "batch", *, estimator: str = "cluster_unit_recomputed", cluster_col: str | None = "perm_profile_hash", **kw) -> dict:
    """Convenience: bands for indicator columns of a frame restricted to rows with a weight."""
    sub = frame[frame[weight_col].notna()]
    if len(sub) == 0:
        return {"lo": np.full(len(indicator_cols), np.nan), "hi": np.full(len(indicator_cols), np.nan), "point": np.full(len(indicator_cols), np.nan), "n_batches": 0, "n_clusters": 0, "estimator": estimator}
    clusters = sub[cluster_col].to_numpy() if cluster_col else None
    return bands_for(estimator, sub[indicator_cols].to_numpy(dtype=float), sub[weight_col].to_numpy(dtype=float), clusters, sub[batch_col].to_numpy(), **kw)
