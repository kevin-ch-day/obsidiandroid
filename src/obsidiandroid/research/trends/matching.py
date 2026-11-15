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


def strata(mal: pd.DataFrame, ben: pd.DataFrame, years: list[int], config: dict, sdk_col: str = "sdk_catalog_target") -> pd.DataFrame:
    """One row per (year, band): malware rows, benign rows, matched capacity = min, dropped flag."""
    rows = []
    mb = assign_band(mal[sdk_col], config); bb = assign_band(ben[sdk_col], config)
    names = [b["name"] for b in config["bands"]] + [config["null_band"]]
    for year in years:
        for band in names:
            n_m = int(((mal["year"] == year) & (mb == band)).sum()); n_b = int(((ben["year"] == year) & (bb == band)).sum())
            rows.append({"year": year, "band": band, "malware_rows": n_m, "benign_rows": n_b, "matched_capacity": min(n_m, n_b), "dropped": n_m == 0 or n_b == 0})
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


def matched_malware_band_bootstrap(mal: pd.DataFrame, indicator_m: pd.Series, w_m: pd.Series, year: int, config: dict, capacities: dict[str, float],
                                   n_resamples: int, seed: int, sdk_col: str = "sdk_catalog_target") -> tuple[float, float, int]:
    """Batch-resampled band for the matched malware prevalence: capacities (per band) fixed at the point estimate; within each band the
    weighted prevalence is recomputed from resampled batches (per-batch numerators/denominators, vectorized). Returns (lo, hi, n_batches)."""
    gm = mal[(mal["year"] == year).to_numpy() & w_m.notna().to_numpy()]
    if len(gm) == 0 or not capacities:
        return (np.nan, np.nan, 0)
    bands = assign_band(gm[sdk_col], config); batches = np.unique(gm["batch"].to_numpy())
    if len(batches) < 2:
        return (np.nan, np.nan, int(len(batches)))
    rng = np.random.default_rng(seed); picks = rng.integers(0, len(batches), size=(n_resamples, len(batches)))
    counts = np.zeros((n_resamples, len(batches)))
    for r in range(n_resamples):
        counts[r] = np.bincount(picks[r], minlength=len(batches))
    total = np.zeros(n_resamples); denom = np.zeros(n_resamples)
    for band, cap in capacities.items():
        im = gm.index[bands == band]
        if len(im) == 0:
            continue
        inv = np.searchsorted(batches, gm.loc[im, "batch"].to_numpy()); num = np.zeros(len(batches)); den = np.zeros(len(batches))
        np.add.at(num, inv, indicator_m[im].to_numpy(dtype=float) * w_m[im].to_numpy(dtype=float)); np.add.at(den, inv, w_m[im].to_numpy(dtype=float))
        rn = counts @ num; rd = counts @ den; ok = rd > 0
        total[ok] += cap * rn[ok] / rd[ok]; denom[ok] += cap
    with np.errstate(invalid="ignore", divide="ignore"):
        vals = total / denom
    return (float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5)), int(len(batches)))
