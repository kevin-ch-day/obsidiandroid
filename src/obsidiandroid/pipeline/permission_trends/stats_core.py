"""Pure statistical helpers for permission-trend reporting (JSD, FDR, correlation, etc.)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def kl_div(p: np.ndarray, q: np.ndarray) -> float:
    eps = 1e-12
    p2 = np.clip(p, eps, 1.0)
    q2 = np.clip(q, eps, 1.0)
    return float(np.sum(p2 * np.log(p2 / q2)))


def js_distance(p: np.ndarray, q: np.ndarray) -> float:
    m = 0.5 * (p + q)
    return float(np.sqrt(0.5 * (kl_div(p, m) + kl_div(q, m))))


def prevalence_entropy(prevalences: list[float]) -> tuple[float, float]:
    arr = np.array([max(0.0, min(1.0, float(v))) for v in prevalences], dtype=float)
    if arr.size == 0 or float(arr.sum()) <= 0:
        return 0.0, 1.0
    probs = arr / arr.sum()
    probs = probs[probs > 0]
    entropy = float(-(probs * np.log(probs)).sum())
    return entropy, float(np.exp(entropy))


def build_jsd_matrix(prevalence_df: pd.DataFrame, row_field: str, run_id: str) -> pd.DataFrame:
    if prevalence_df.empty:
        return pd.DataFrame(columns=["run_id", row_field, "other", "js_distance"])
    pivot = prevalence_df.pivot_table(index=row_field, columns="permission", values="prevalence", fill_value=0.0)
    names = pivot.index.tolist()
    rows: list[dict[str, Any]] = []
    for i, left_name in enumerate(names):
        p = np.array(pivot.loc[left_name], dtype=float)
        p = p / p.sum() if p.sum() > 0 else np.ones_like(p) / max(len(p), 1)
        for j, right_name in enumerate(names):
            if j < i:
                continue
            q = np.array(pivot.loc[right_name], dtype=float)
            q = q / q.sum() if q.sum() > 0 else np.ones_like(q) / max(len(q), 1)
            jsd = js_distance(p, q)
            rows.append({"run_id": run_id, row_field: left_name, "other": right_name, "js_distance": round(jsd, 6)})
            if left_name != right_name:
                rows.append({"run_id": run_id, row_field: right_name, "other": left_name, "js_distance": round(jsd, 6)})
    return pd.DataFrame(rows)


def chi2_2x2_p_and_v(a: int, b: int, c: int, d: int) -> tuple[float, float]:
    table = np.array([[a, b], [c, d]], dtype=float)
    n = float(table.sum())
    if n <= 0:
        return 1.0, 0.0
    try:
        from scipy.stats import chi2_contingency

        chi2, p_value, _, _ = chi2_contingency(table, correction=False)
    except Exception:
        return 1.0, 0.0
    cramers_v = float(np.sqrt(max(chi2, 0.0) / n))
    return float(p_value), cramers_v


def bh_fdr(p_values: list[float]) -> list[float]:
    n = len(p_values)
    if n == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: (np.nan_to_num(x[1], nan=1.0), x[0]))
    out = [1.0] * n
    prev = 1.0
    for rank, (idx, p_val) in enumerate(reversed(indexed), start=1):
        true_rank = n - rank + 1
        p = float(np.nan_to_num(p_val, nan=1.0))
        q = min(prev, (p * n) / max(true_rank, 1))
        prev = q
        out[idx] = float(min(max(q, 0.0), 1.0))
    return out


def cliffs_delta(a: pd.Series, b: pd.Series) -> float:
    x = pd.to_numeric(a, errors="coerce").dropna().values
    y = pd.to_numeric(b, errors="coerce").dropna().values
    if len(x) == 0 or len(y) == 0:
        return 0.0
    gt = 0
    lt = 0
    for xv in x:
        gt += int((xv > y).sum())
        lt += int((xv < y).sum())
    return float((gt - lt) / (len(x) * len(y)))


def safe_series_mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return 0.0
    return float(values.mean())


def safe_series_median(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return 0.0
    return float(values.median())


def spearman_stat(x_vals: np.ndarray, y_vals: np.ndarray) -> tuple[float, float]:
    try:
        from scipy.stats import spearmanr

        rho, p_value = spearmanr(x_vals, y_vals)
        return float(rho), float(p_value)
    except Exception:
        x_rank = pd.Series(x_vals).rank(method="average")
        y_rank = pd.Series(y_vals).rank(method="average")
        rho = float(x_rank.corr(y_rank))
        return rho, np.nan


def spearman_with_bootstrap_ci(
    x: pd.Series,
    y: pd.Series,
    *,
    bootstrap_resamples: int = 2000,
    rng_seed: int = 42,
) -> tuple[float, float, float, float]:
    paired = pd.concat([x, y], axis=1).dropna()
    if paired.empty:
        return 0.0, np.nan, np.nan, np.nan
    x_vals = paired.iloc[:, 0].astype(float).values
    y_vals = paired.iloc[:, 1].astype(float).values
    rho, p_value = spearman_stat(x_vals, y_vals)
    n = len(x_vals)
    if n < 3:
        return rho, p_value, np.nan, np.nan
    rng = np.random.default_rng(rng_seed)
    resamples = max(int(bootstrap_resamples), 100)
    boot: list[float] = []
    try:
        from scipy.stats import rankdata

        # Rank complete batches together.  This preserves the sample-level
        # bootstrap draws and average-tie rank semantics of ``spearmanr`` but
        # avoids 2,000 Python/scipy calls for each reported association.
        batch_size = 64
        for offset in range(0, resamples, batch_size):
            batch_count = min(batch_size, resamples - offset)
            idx = rng.integers(0, n, size=(batch_count, n))
            x_rank = rankdata(x_vals[idx], axis=1, method="average")
            y_rank = rankdata(y_vals[idx], axis=1, method="average")
            x_centered = x_rank - x_rank.mean(axis=1, keepdims=True)
            y_centered = y_rank - y_rank.mean(axis=1, keepdims=True)
            denominator = np.sqrt((x_centered * x_centered).sum(axis=1) * (y_centered * y_centered).sum(axis=1))
            correlations = np.divide(
                (x_centered * y_centered).sum(axis=1),
                denominator,
                out=np.full(batch_count, np.nan, dtype=float),
                where=denominator > 0.0,
            )
            boot.extend(correlations[np.isfinite(correlations)].astype(float).tolist())
    except Exception:
        # Keep a deterministic fallback for environments without SciPy.
        for _ in range(resamples):
            idx = rng.integers(0, n, size=n)
            r, _ = spearman_stat(x_vals[idx], y_vals[idx])
            if not np.isnan(r):
                boot.append(r)
    if not boot:
        return rho, p_value, np.nan, np.nan
    low = float(np.quantile(boot, 0.025))
    high = float(np.quantile(boot, 0.975))
    return rho, p_value, low, high
