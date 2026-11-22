"""Cluster weighting modes.

cluster: weight = 1 / (rows sharing the cluster key within year × population); rows without a key get NaN.
one_per_cluster: deterministic one-row sample per (year, cluster) with a seed; sampled rows weight 1.
signer_cluster: the same with signer_thumbprint_raw as the cluster key.
raw: every row with a dictionary weight 1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MODES = ("raw", "cluster", "one_per_cluster", "signer_cluster")


def cluster_weights(frame: pd.DataFrame, cluster_col: str = "perm_profile_hash", year_col: str = "year", eligible_col: str = "has_dict") -> pd.Series:
    key = frame[year_col].astype(str) + "|" + frame[cluster_col].astype("string").fillna("∅")
    valid = frame[eligible_col].astype(bool) & frame[cluster_col].notna()
    sizes = key[valid].value_counts()
    weights = pd.Series(np.nan, index=frame.index, dtype=float)
    weights[valid] = 1.0 / key[valid].map(sizes).astype(float)
    return weights


def one_per_cluster_weights(frame: pd.DataFrame, seed: int, cluster_col: str = "perm_profile_hash", year_col: str = "year", eligible_col: str = "has_dict") -> pd.Series:
    rng = np.random.default_rng(seed)
    valid = frame[eligible_col].astype(bool) & frame[cluster_col].notna()
    sub = frame[valid]
    key = sub[year_col].astype(str) + "|" + sub[cluster_col].astype(str)
    order = pd.Series(rng.random(len(sub)), index=sub.index)
    chosen = order.groupby(key.values).idxmin()
    weights = pd.Series(np.nan, index=frame.index, dtype=float)
    weights[valid] = 0.0
    weights[chosen.values] = 1.0
    return weights


def weights_for_mode(frame: pd.DataFrame, mode: str, seed: int = 0) -> pd.Series:
    if mode == "raw":
        w = pd.Series(np.nan, index=frame.index, dtype=float); w[frame["has_dict"].astype(bool)] = 1.0; return w
    if mode == "cluster":
        return cluster_weights(frame)
    if mode == "one_per_cluster":
        return one_per_cluster_weights(frame, seed)
    if mode == "signer_cluster":
        return cluster_weights(frame, cluster_col="signer_thumbprint_raw")
    raise ValueError(f"unknown weighting mode {mode!r}; expected one of {MODES}")


def cluster_count(frame: pd.DataFrame, cluster_col: str = "perm_profile_hash", year_col: str = "year", eligible_col: str = "has_dict") -> pd.Series:
    valid = frame[eligible_col].astype(bool) & frame[cluster_col].notna()
    return frame[valid].groupby(year_col)[cluster_col].nunique()
