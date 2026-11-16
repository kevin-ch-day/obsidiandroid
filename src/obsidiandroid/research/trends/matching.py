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


def matched_malware_band_bootstrap_v1_1(mal: pd.DataFrame, indicator_m: pd.Series | np.ndarray, w_m: pd.Series, year: int, config: dict, capacities: dict[str, float],
                                   n_resamples: int, seed: int, sdk_col: str = "sdk_catalog_target", estimator: str = "cluster_unit_recomputed", cluster_col: str | None = "perm_profile_hash") -> tuple[np.ndarray, np.ndarray, int]:
    """v1.1 design, retained ONLY as sensitivity arm S14. NOT the registered unit: it recomputes profile weights within each
    SDK band (registered rule 3 is profile within year and population), draws year-level batch multiplicities once and reuses
    them in every band, fixes capacities at the original point estimate, and drops a band from a draw when no profile of
    that band is represented. See the v1.2 change log.

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


def matched_malware_bootstrap_registered(mal: pd.DataFrame, indicator_m: pd.Series | np.ndarray, year: int, config: dict, benign_band_rows: dict[str, int],
                                         n_resamples: int, seed: int, sdk_col: str = "sdk_catalog_target", cluster_col: str | None = "perm_profile_hash",
                                         estimator: str = "cluster_unit_recomputed", weights: pd.Series | None = None) -> dict:
    """Batch bootstrap for the matched (SDK-band standardized) malware prevalence (v1.2.1).

    Two designs, chosen by ``estimator`` and ``cluster_col`` so that every arm's matched bounds use that arm's own unit
    (v1.2 dispatched every arm through the profile unit):

    * ``cluster_unit_recomputed`` with a cluster column — the registered unit (pre-registration rule 3): cluster within
      **year and population**. On every draw the year's batches are resampled with replacement once (rule 4); the resampled
      population is the concatenation of the drawn batches, duplicates counted as rows; cluster weights w_c = 1/(rows of c in
      the year-level resampled population) are **recomputed** on that population. Band prevalence on a draw =
      Σ_c w_c·RS_band[c] / Σ_c w_c·RN_band[c], where RN_band[c] is c's resampled row count in the band and RS_band[c] the
      resampled sum of the row indicators of c in the band. For permission profiles the indicator is constant within a cluster,
      so RS = RN·ind_c and this is exactly the v1.2 statistic; for other clusters (signer clusters, arm S11) it is the
      row-weighted statistic that ``matched_prevalence`` displays (v1.2 spread a frozen whole-year cluster mean into every band,
      which differed from the displayed point). ``point_check_max_abs_diff`` witnesses the agreement on the original data.
    * otherwise (``fixed_design``, arm S13; or a weighting without a cluster key: ``raw`` S1_raw, ``one_per_cluster`` S1 seeds)
      — per-row design ``weights`` fixed at the original data; band prevalence on a draw =
      Σ_b n_b·Σ_{rows in b∩band} w·ind / Σ_b n_b·Σ_{rows in b∩band} w with n_b the draw multiplicity of batch b.

    Standardization (rule 5) combines bands with capacity weights. Rule 5 does not say whether the capacity
    min(malware rows, benign rows) is fixed at the original data or re-estimated on each draw; both are returned: ``fixed`` uses
    the original per-band capacities (bands absent from a draw drop out of the denominator), ``recomputed`` uses
    min(resampled malware rows in band, benign rows in band). Returns dict(point, lo_fixed, hi_fixed, lo_recomputed,
    hi_recomputed, n_batches, n_profiles, design, indicator_constant_within_cluster, point_check_max_abs_diff, unit_mass_check,
    bands_point, capacities_point)."""
    from obsidiandroid.research.trends.bootstrap import _resample_counts
    design = "cluster_unit_recomputed" if (estimator == "cluster_unit_recomputed" and cluster_col) else "fixed_design"
    gm_mask = (mal["year"] == year).to_numpy().copy()
    if weights is not None:
        gm_mask &= weights.notna().to_numpy()
    gm = mal[gm_mask]
    ind_all = indicator_m.to_numpy(dtype=float)[:, None] if isinstance(indicator_m, pd.Series) else np.asarray(indicator_m, dtype=float)
    pos = {idx: i for i, idx in enumerate(mal.index)}; rows_gm = np.array([pos[i] for i in gm.index], dtype=int); ind = ind_all[rows_gm] if len(gm) else ind_all[:0]
    k = ind_all.shape[1]; names = [b["name"] for b in config["bands"]] + [config["null_band"]]
    nan = np.full(k, np.nan)
    empty = {"point": nan, "lo_fixed": nan, "hi_fixed": nan, "lo_recomputed": nan, "hi_recomputed": nan, "n_batches": 0, "n_profiles": 0, "design": design,
             "indicator_constant_within_cluster": True, "point_check_max_abs_diff": 0.0, "unit_mass_check": 0.0, "bands_point": {}, "capacities_point": {}}
    if len(gm) == 0:
        return empty
    batches, inv_b = np.unique(gm["batch"].to_numpy(), return_inverse=True); B = len(batches)
    band = assign_band(gm[sdk_col], config).to_numpy()
    w_row = np.ones(len(gm)) if weights is None else weights[gm.index].to_numpy(dtype=float)
    rows_b = {}; caps_point = {}
    for nm in names:
        sel = band == nm
        if sel.any() and benign_band_rows.get(nm, 0) > 0:
            rb = np.zeros(B); np.add.at(rb, inv_b[sel], 1.0); rows_b[nm] = rb; caps_point[nm] = float(min(rb.sum(), benign_band_rows[nm]))
    if design == "cluster_unit_recomputed":
        profiles, inv_c = np.unique(gm[cluster_col].to_numpy(), return_inverse=True); C = len(profiles)
        N = np.zeros((B, C)); np.add.at(N, (inv_b, inv_c), 1.0)                              # rows per batch x cluster (whole year)
        Nb, Sb = {}, {}
        for nm in rows_b:
            sel = band == nm
            m = np.zeros((B, C)); np.add.at(m, (inv_b[sel], inv_c[sel]), 1.0); Nb[nm] = m
            s = np.zeros((B, C, k)); np.add.at(s, (inv_b[sel], inv_c[sel]), ind[sel]); Sb[nm] = s
        indc = np.zeros((C, k)); np.add.at(indc, inv_c, ind); indc /= np.bincount(inv_c, minlength=C)[:, None]
        constant_within_cluster = bool(np.abs(indc[inv_c] - ind).max() < 1e-12) if len(gm) else True
        def standardize(counts, caps_rule):
            RN = counts @ N; w = np.where(RN > 0, 1.0 / np.where(RN > 0, RN, 1.0), 0.0)              # (R, C) year-level recomputed weights
            total = np.zeros((counts.shape[0], k)); den = np.zeros(counts.shape[0]); band_prev = {}
            for nm in rows_b:
                nben = benign_band_rows[nm]; RNb = counts @ Nb[nm]; mass = (w * RNb).sum(axis=1); present = mass > 0
                if constant_within_cluster:                                                   # permission profiles: RS = RN·ind_c exactly; keep the v1.2 arithmetic (bit-identical primary)
                    num = (w * RNb) @ indc
                else:                                                                         # e.g. signer clusters: per-band resampled indicator sums
                    num = np.empty((counts.shape[0], k))
                    for j in range(k):
                        num[:, j] = (w * (counts @ Sb[nm][:, :, j])).sum(axis=1)
                prev = num / np.where(present, mass, 1.0)[:, None]; band_prev[nm] = prev
                cap = np.where(present, (np.minimum(counts @ rows_b[nm], nben) if caps_rule == "recomputed" else caps_point[nm]), 0.0)
                total += cap[:, None] * prev; den += cap
            with np.errstate(invalid="ignore", divide="ignore"):
                return total / den[:, None], band_prev
        n_units = int(C)
    else:
        num_b, den_b = {}, {}
        for nm in rows_b:
            sel = band == nm
            nb_ = np.zeros((B, k)); np.add.at(nb_, inv_b[sel], ind[sel] * w_row[sel][:, None]); num_b[nm] = nb_
            db_ = np.zeros(B); np.add.at(db_, inv_b[sel], w_row[sel]); den_b[nm] = db_
        constant_within_cluster = True
        def standardize(counts, caps_rule):
            total = np.zeros((counts.shape[0], k)); den = np.zeros(counts.shape[0]); band_prev = {}
            for nm in rows_b:
                nben = benign_band_rows[nm]; rd = counts @ den_b[nm]; present = rd > 0
                prev = (counts @ num_b[nm]) / np.where(present, rd, 1.0)[:, None]; band_prev[nm] = prev
                cap = np.where(present, (np.minimum(counts @ rows_b[nm], nben) if caps_rule == "recomputed" else caps_point[nm]), 0.0)
                total += cap[:, None] * prev; den += cap
            with np.errstate(invalid="ignore", divide="ignore"):
                return total / den[:, None], band_prev
        n_units = int(len(gm))
    one = np.ones((1, B))
    point, band_prev0 = standardize(one, "fixed"); point = point[0]
    bands_point = {nm: float(p[0, 0]) for nm, p in band_prev0.items()} if k == 1 else {}
    # witness: the row-weighted statistic that matched_prevalence displays, computed directly on the original rows
    w_disp = w_row if design == "fixed_design" else (1.0 / np.bincount(inv_c, minlength=C)[inv_c])
    tot = np.zeros(k); dd = 0.0
    for nm, cap in caps_point.items():
        sel = band == nm; ws = w_disp[sel].sum()
        if ws > 0:
            tot += cap * (ind[sel] * w_disp[sel][:, None]).sum(axis=0) / ws; dd += cap
    point_check = float(np.nanmax(np.abs(point - tot / dd))) if dd > 0 else 0.0
    if B < 2:
        return {**empty, "point": point, "n_batches": int(B), "n_profiles": n_units, "indicator_constant_within_cluster": constant_within_cluster, "point_check_max_abs_diff": point_check, "bands_point": bands_point, "capacities_point": caps_point}
    counts = _resample_counts(B, n_resamples, seed)
    if design == "cluster_unit_recomputed":
        RN = counts @ N; mass = (np.where(RN > 0, 1.0 / np.where(RN > 0, RN, 1.0), 0.0) * RN).sum(axis=1); unit_mass_check = float(np.abs(mass - (RN > 0).sum(axis=1)).max())
    else:
        unit_mass_check = 0.0
    fx, _ = standardize(counts, "fixed"); rc, _ = standardize(counts, "recomputed")
    return {"point": point, "lo_fixed": np.nanpercentile(fx, 2.5, axis=0), "hi_fixed": np.nanpercentile(fx, 97.5, axis=0), "lo_recomputed": np.nanpercentile(rc, 2.5, axis=0), "hi_recomputed": np.nanpercentile(rc, 97.5, axis=0),
            "n_batches": int(B), "n_profiles": n_units, "design": design, "indicator_constant_within_cluster": constant_within_cluster, "point_check_max_abs_diff": point_check, "unit_mass_check": unit_mass_check, "bands_point": bands_point, "capacities_point": caps_point}


def fixed_target_gap_bootstrap(g: pd.DataFrame, permission: str, n_resamples: int, seed: int, cluster_col: str = "perm_profile_hash") -> dict:
    """v1.2 P3 detail for ONE fixed permission on the rows given (e.g. ME ∩ 2024 with dictionaries).

    Paired batch bootstrap: on each year-level batch draw both raw prevalence and profile-weighted prevalence are computed on the
    same resampled rows, with profile weights recomputed; the gap is their difference in percentage points. Also returns the
    additive profile decomposition on the original rows (contribution_h = I(perm in h)·(n_h/N − 1/K), summing to the gap) and the
    fixed-target leave-one-batch-out gaps. The target permission is fixed by the caller before any removal; nothing is re-selected."""
    from obsidiandroid.research.trends.bootstrap import _resample_counts
    hit = g["perms"].apply(lambda ps: float(permission in (ps or []))).to_numpy()
    batches, inv_b = np.unique(g["batch"].to_numpy(), return_inverse=True); profiles, inv_c = np.unique(g[cluster_col].to_numpy(), return_inverse=True)
    B, C, N = len(batches), len(profiles), len(g); Nm = np.zeros((B, C)); np.add.at(Nm, (inv_b, inv_c), 1.0); indc = np.zeros(C); indc[inv_c] = hit
    n_h = Nm.sum(axis=0); raw = hit.mean(); prof = float(indc.mean()); gap = 100 * (raw - prof)
    contrib = indc * (n_h / N - 1.0 / C) * 100
    decomposition = sorted([{"profile": profiles[i], "rows": int(n_h[i]), "contribution_pp": float(contrib[i])} for i in range(C) if indc[i] > 0], key=lambda d: -abs(d["contribution_pp"]))
    out = {"permission": permission, "rows": int(N), "profiles": int(C), "batches": int(B), "raw": float(raw), "profile_weighted": prof, "gap_pp": float(gap), "decomposition_sum_pp": float(contrib.sum()), "top_contributions": decomposition[:10]}
    if B >= 2:
        counts = _resample_counts(B, n_resamples, seed); RN = counts @ Nm; rows_r = RN.sum(axis=1); raw_r = (RN @ indc) / rows_r; present = RN > 0; prof_r = (present @ indc) / present.sum(axis=1)
        gaps = 100 * (raw_r - prof_r); out.update({"gap_lo95_pp": float(np.percentile(gaps, 2.5)), "gap_hi95_pp": float(np.percentile(gaps, 97.5)), "gap_includes_zero": bool(np.percentile(gaps, 2.5) <= 0 <= np.percentile(gaps, 97.5)), "n_resamples": int(n_resamples)})
    else: out.update({"gap_lo95_pp": None, "gap_hi95_pp": None, "gap_includes_zero": None, "n_resamples": 0})
    loo = []
    for b in range(B):
        keep = inv_b != b
        if keep.sum() == 0: continue
        prof_keep = np.unique(inv_c[keep]); loo.append({"batch_removed": batches[b], "rows_removed": int((~keep).sum()), "rows": int(keep.sum()), "profiles": int(len(prof_keep)), "raw": float(hit[keep].mean()), "profile_weighted": float(indc[prof_keep].mean()), "gap_pp": float(100 * (hit[keep].mean() - indc[prof_keep].mean()))})
    out["leave_one_batch_out_fixed_target"] = loo
    return out
