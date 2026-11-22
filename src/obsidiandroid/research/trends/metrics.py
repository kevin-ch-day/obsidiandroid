"""Descriptive metrics: prevalence matrices, Jensen-Shannon distance, Herfindahl, top-k share, slope with band."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon

from obsidiandroid.research.trends.bootstrap import bands_for


def indicator_matrix(perms: pd.Series, permissions: list[str], casefold: bool = False) -> np.ndarray:
    """(n_rows, k) 0/1 matrix: row declares permission exactly (or casefolded when ``casefold``)."""
    keys = [p.casefold() if casefold else p for p in permissions]; index = {p: i for i, p in enumerate(keys)}
    mat = np.zeros((len(perms), len(permissions)))
    for r, plist in enumerate(perms):
        if not plist:
            continue
        for p in set(plist):
            j = index.get(p.casefold() if casefold else p)
            if j is not None:
                mat[r, j] = 1.0
    return mat


def prevalence_table(frame: pd.DataFrame, permissions: list[str], weights: pd.Series, years: list[int], casefold: bool = False, *, estimator: str = "cluster_unit_recomputed", cluster_col: str | None = "perm_profile_hash", **band_kw) -> pd.DataFrame:
    """Per year × permission: raw prevalence, weighted prevalence, band, n_rows, n_clusters, n_batches, observed_any, estimator.

    Rows are emitted for every requested permission including those never observed in a year (weighted_prevalence 0 with
    observed_any False), so a registered permission set is reported completely rather than silently dropped."""
    rows = []; weights = weights.reindex(frame.index)
    for year in years:
        g = frame[(frame["year"] == year) & weights.notna()]
        if len(g) == 0:
            continue
        ind = indicator_matrix(g["perms"], permissions, casefold); w = weights[g.index].to_numpy(dtype=float)
        clusters = g[cluster_col].to_numpy() if cluster_col else None
        bands = bands_for(estimator, ind, w, clusters, g["batch"].to_numpy(), **band_kw)
        raw = ind.mean(axis=0); observed = ind.sum(axis=0) > 0
        for j, p in enumerate(permissions):
            rows.append({"year": year, "permission": p, "raw_prevalence": float(raw[j]), "weighted_prevalence": float(bands["point"][j]), "lo95": float(bands["lo"][j]), "hi95": float(bands["hi"][j]),
                         "diff_pp": 100 * (float(raw[j]) - float(bands["point"][j])), "n_rows": int(len(g)), "n_clusters": int(g[cluster_col].nunique()) if cluster_col else 0, "n_batches": bands["n_batches"],
                         "observed_any": bool(observed[j]), "estimator": bands["estimator"]})
    return pd.DataFrame(rows)


def top_permissions(frame: pd.DataFrame, weights: pd.Series, k: int = 30) -> list[str]:
    g = frame[weights.notna()]; counts: dict[str, int] = {}
    for plist in g["perms"]:
        for p in set(plist or []):
            counts[p] = counts.get(p, 0) + 1
    return [p for p, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def type_profile_vectors(frame: pd.DataFrame, weights: pd.Series, type_col: str, types: list[str]) -> tuple[list[str], dict[str, np.ndarray], dict[str, int]]:
    g = frame[weights.notna()]; vocab = sorted({p for plist in g["perms"] for p in (plist or [])}); idx = {p: i for i, p in enumerate(vocab)}
    vectors: dict[str, np.ndarray] = {}; rows: dict[str, int] = {}
    for t in types:
        gt = g[g[type_col] == t]; v = np.zeros(len(vocab))
        for plist, w in zip(gt["perms"], weights[gt.index]):
            for p in set(plist or []):
                v[idx[p]] += w
        vectors[t] = v / v.sum() if v.sum() > 0 else None; rows[t] = int(len(gt))
    return vocab, vectors, rows


def js_distance(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon distance, base 2 (0 for identical profiles, 1 for disjoint)."""
    return float(jensenshannon(p, q, base=2))


def pairwise_jsd(vectors: dict[str, np.ndarray], rows: dict[str, int], thin_below: int = 30) -> pd.DataFrame:
    types = list(vectors); out = []
    for i, a in enumerate(types):
        for b in types[i + 1:]:
            if vectors[a] is None or vectors[b] is None:
                continue
            out.append({"type_a": a, "type_b": b, "js_distance": js_distance(vectors[a], vectors[b]), "rows_a": rows[a], "rows_b": rows[b], "thin": rows[a] < thin_below or rows[b] < thin_below})
    return pd.DataFrame(out)


def herfindahl(groups: pd.Series) -> float:
    counts = groups.value_counts(); n = counts.sum()
    return float(((counts / n) ** 2).sum()) if n else float("nan")


def top_k_share(groups: pd.Series, k: int = 10) -> float:
    counts = groups.value_counts(); n = counts.sum()
    return float(counts.head(k).sum() / n) if n else float("nan")


def slope_with_band(years: np.ndarray, values: np.ndarray, lo: np.ndarray | None = None, hi: np.ndarray | None = None) -> dict:
    """OLS slope per year of a yearly series; band = slopes of the lower/upper envelopes (descriptive, not inferential)."""
    mask = ~np.isnan(values)
    if mask.sum() < 2:
        return {"slope_per_year": float("nan"), "slope_lo": float("nan"), "slope_hi": float("nan"), "n_years": int(mask.sum())}
    x = years[mask].astype(float); s = float(np.polyfit(x, values[mask], 1)[0])
    s_lo = float(np.polyfit(x, lo[mask], 1)[0]) if lo is not None and not np.isnan(lo[mask]).any() else float("nan")
    s_hi = float(np.polyfit(x, hi[mask], 1)[0]) if hi is not None and not np.isnan(hi[mask]).any() else float("nan")
    return {"slope_per_year": s, "slope_lo": min(s_lo, s_hi), "slope_hi": max(s_lo, s_hi), "n_years": int(mask.sum())}
