"""Year × target-SDK-band matched benign/malware construction (2018–2021 primary window)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_BANDS_PATH = Path(__file__).resolve().parents[4] / "config" / "research" / "trend_study_bands_v1.json"


def load_band_config(path: str | Path | None = None, variant: str = "primary") -> dict:
    cfg = json.loads(Path(path or DEFAULT_BANDS_PATH).read_text(encoding="utf-8"))
    if variant not in cfg["variants"]:
        raise ValueError(f"unknown band variant {variant!r}")
    return {"variant": variant, "null_band": cfg["null_band"], "bands": cfg["variants"][variant]}


def assign_band(values: pd.Series, config: dict) -> pd.Series:
    out = pd.Series(config["null_band"], index=values.index, dtype=object)
    numeric = pd.to_numeric(values, errors="coerce")
    for band in config["bands"]:
        lo, hi = band["min"], band["max"]
        mask = numeric.notna() & (numeric >= lo) & ((numeric <= hi) if hi is not None else True)
        out[mask] = band["name"]
    return out


def strata(mal: pd.DataFrame, ben: pd.DataFrame, years: list[int], config: dict, sdk_col: str = "sdk_catalog_target", w_m: pd.Series | None = None, w_b: pd.Series | None = None) -> pd.DataFrame:
    """One row per (year, band): malware rows, benign rows, matched capacity = min, dropped flag.

    When ``w_m`` / ``w_b`` are given, rows are conditioned on a non-null weight (i.e. a permission dictionary is present), which
    is the population the matched prevalence is actually computed on. Both counts are kept: ``*_rows_all`` (every row in the
    stratum) and ``*_rows`` (dictionary-conditioned). ``matched_capacity`` is dictionary-conditioned; v1 reported the
    all-rows capacity (1,683 / 1,138 / 1,272 / 455) while computing on the dictionary-conditioned population (1,673 / 1,091 /
    1,183 / 419) — that discrepancy is what this change removes."""
    rows = []
    mb = assign_band(mal[sdk_col], config); bb = assign_band(ben[sdk_col], config)
    keep_m = w_m.notna() if w_m is not None else pd.Series(True, index=mal.index); keep_b = w_b.notna() if w_b is not None else pd.Series(True, index=ben.index)
    names = [b["name"] for b in config["bands"]] + [config["null_band"]]
    for year in years:
        for band in names:
            sm = (mal["year"] == year) & (mb == band); sb = (ben["year"] == year) & (bb == band)
            n_m_all, n_b_all = int(sm.sum()), int(sb.sum()); n_m, n_b = int((sm & keep_m).sum()), int((sb & keep_b).sum())
            rows.append({"year": year, "band": band, "malware_rows_all": n_m_all, "benign_rows_all": n_b_all, "malware_rows": n_m, "benign_rows": n_b,
                         "malware_clusters": int(mal.loc[sm & keep_m, "perm_profile_hash"].nunique()), "benign_clusters": int(ben.loc[sb & keep_b, "perm_profile_hash"].nunique()),
                         "matched_capacity_all_rows": min(n_m_all, n_b_all), "matched_capacity": min(n_m, n_b), "dropped": n_m == 0 or n_b == 0})
    return pd.DataFrame(rows)


def matched_prevalence(mal: pd.DataFrame, ben: pd.DataFrame, indicator_m: pd.Series, indicator_b: pd.Series, w_m: pd.Series, w_b: pd.Series,
                       year: int, config: dict, sdk_col: str = "sdk_catalog_target", unmatched_all_in: bool = False) -> dict:
    """Band-wise weighted prevalence combined with weights min(n_mal, n_ben); strata with a zero side are dropped.
    ``unmatched_all_in`` is the deliberately wrong reference arm: no banding, every row counts."""
    gm = mal[(mal["year"] == year).to_numpy() & w_m.notna().to_numpy()]; gb = ben[(ben["year"] == year).to_numpy() & w_b.notna().to_numpy()]
    if unmatched_all_in:
        pm = float((indicator_m[gm.index] * w_m[gm.index]).sum() / w_m[gm.index].sum()) if len(gm) else np.nan
        pb = float((indicator_b[gb.index] * w_b[gb.index]).sum() / w_b[gb.index].sum()) if len(gb) else np.nan
        return {"malware": pm, "benign": pb, "capacity": float(min(len(gm), len(gb))), "bands_used": ["ALL_UNMATCHED"], "bands_dropped": []}
    mb = assign_band(gm[sdk_col], config); bb = assign_band(gb[sdk_col], config)
    num_m = num_b = den = 0.0; used = []; dropped = []
    for band in [b["name"] for b in config["bands"]] + [config["null_band"]]:
        im = gm.index[mb == band]; ib = gb.index[bb == band]
        if len(im) == 0 or len(ib) == 0:
            dropped.append(band); continue
        if w_m[im].sum() <= 0 or w_b[ib].sum() <= 0:   # e.g. one-per-cluster arms where no sampled row falls in the band
            dropped.append(band); continue
        cap = min(len(im), len(ib))
        pm = (indicator_m[im] * w_m[im]).sum() / w_m[im].sum(); pb = (indicator_b[ib] * w_b[ib]).sum() / w_b[ib].sum()
        num_m += cap * pm; num_b += cap * pb; den += cap; used.append(band)
    return {"malware": num_m / den if den else np.nan, "benign": num_b / den if den else np.nan, "capacity": den, "bands_used": used, "bands_dropped": dropped}


def matched_malware_band_bootstrap(mal: pd.DataFrame, indicator_m: pd.Series | np.ndarray, w_m: pd.Series, year: int, config: dict, capacities: dict[str, float],
                                   n_resamples: int, seed: int, sdk_col: str = "sdk_catalog_target", estimator: str = "cluster_unit_recomputed", cluster_col: str | None = "perm_profile_hash") -> tuple[np.ndarray, np.ndarray, int]:
    """Batch-resampled band for the matched malware prevalence of one or several permissions at once.

    Capacities (per band) are fixed at the point estimate. Within each band the weighted prevalence is recomputed from the
    resampled batches: with ``cluster_unit_recomputed`` the cluster weights are recomputed on each resampled population (unit
    mass per represented cluster); with ``fixed_design`` the original weights are kept. ``indicator_m`` may be a Series (one
    permission) or an (n_rows, k) array aligned with ``mal.index``. Returns (lo (k,), hi (k,), n_batches)."""
    gm_mask = (mal["year"] == year).to_numpy() & w_m.notna().to_numpy(); gm = mal[gm_mask]
    ind_all = indicator_m.to_numpy(dtype=float)[:, None] if isinstance(indicator_m, pd.Series) else np.asarray(indicator_m, dtype=float)
    k = ind_all.shape[1]
    if len(gm) == 0 or not capacities:
        return (np.full(k, np.nan), np.full(k, np.nan), 0)
    pos = {idx: i for i, idx in enumerate(mal.index)}; rows_gm = np.array([pos[i] for i in gm.index])
    bands = assign_band(gm[sdk_col], config); batches = np.unique(gm["batch"].to_numpy())
    if len(batches) < 2:
        return (np.full(k, np.nan), np.full(k, np.nan), int(len(batches)))
    from obsidiandroid.research.trends.bootstrap import _resample_counts
    counts = _resample_counts(len(batches), n_resamples, seed)
    total = np.zeros((n_resamples, k)); denom = np.zeros(n_resamples)
    for band, cap in capacities.items():
        sel = (bands == band).to_numpy()
        if not sel.any():
            continue
        g = gm[sel]; ind = ind_all[rows_gm[sel]]; inv_b = np.searchsorted(batches, g["batch"].to_numpy())
        if estimator == "cluster_unit_recomputed" and cluster_col:
            _, inv_c = np.unique(g[cluster_col].to_numpy(), return_inverse=True); C = inv_c.max() + 1
            N = np.zeros((len(batches), C)); np.add.at(N, (inv_b, inv_c), 1.0); RN = counts @ N; rep = RN > 0; n_rep = rep.sum(axis=1)
            vals = np.zeros((n_resamples, k))
            for j in range(k):
                S = np.zeros((len(batches), C)); np.add.at(S, (inv_b, inv_c), ind[:, j]); RS = counts @ S
                with np.errstate(invalid="ignore", divide="ignore"):
                    vals[:, j] = np.where(rep, RS / np.where(RN > 0, RN, 1.0), 0.0).sum(axis=1) / n_rep
            ok = n_rep > 0
        else:
            w = w_m[g.index].to_numpy(dtype=float); num = np.zeros((len(batches), k)); den = np.zeros(len(batches))
            np.add.at(num, inv_b, ind * w[:, None]); np.add.at(den, inv_b, w); rn = counts @ num; rd = counts @ den; ok = rd > 0
            with np.errstate(invalid="ignore", divide="ignore"):
                vals = rn / np.where(rd > 0, rd, 1.0)[:, None]
        total[ok] += cap * vals[ok]; denom[ok] += cap
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / denom[:, None]
    return (np.nanpercentile(out, 2.5, axis=0), np.nanpercentile(out, 97.5, axis=0), int(len(batches)))
