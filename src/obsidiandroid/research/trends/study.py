"""The pre-registered study (T1–T8, TB, scorecard) and its sensitivity arms. Descriptive statistics only.

v1.1 corrections (each is recorded in table metadata and in ``selection_ledger.json``):
- bands use the registered estimator ``cluster_unit_recomputed`` (weights recomputed on every resampled population);
  ``fixed_design`` is retained only as the explicit sensitivity arm S13;
- the year range is derived from the data (v1 hard-coded 2011–2026 and dropped the single 2010 row);
- the dangerous-tier permission set is the full registered set (``registered_full``); the v1 ≥ 1 %-in-either-arm cutoff is
  the explicit exploratory arm S12;
- matched strata and capacities are conditioned on dictionary presence, the population the matched estimate uses;
- every table metadata block carries unit, estimand, estimator, denominator, n_rows and a real n_clusters;
- TB (top-30 per year, D0 table b) is produced with its heatmap keeping not-ranked cells missing, never zero.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from obsidiandroid.research.trends import figures as F
from obsidiandroid.research.trends.bootstrap import DEFAULT_RESAMPLES, DEFAULT_SEED, ESTIMATORS, bands_for
from obsidiandroid.research.trends.dataset import TrendDataset
from obsidiandroid.research.trends.matching import assign_band, fixed_target_gap_bootstrap, load_band_config, matched_malware_band_bootstrap_v1_1, matched_malware_bootstrap_registered, matched_prevalence, strata
from obsidiandroid.research.trends.metrics import herfindahl, indicator_matrix, pairwise_jsd, prevalence_table, top_k_share, top_permissions, type_profile_vectors
from obsidiandroid.research.trends.weighting import weights_for_mode

AP = "android.permission."
SMS_SET = [AP + x for x in ["READ_SMS", "RECEIVE_SMS", "SEND_SMS", "RECEIVE_MMS", "RECEIVE_WAP_PUSH", "READ_CALL_LOG", "WRITE_CALL_LOG", "PROCESS_OUTGOING_CALLS"]]
CAP3 = [AP + x for x in ["BIND_ACCESSIBILITY_SERVICE", "BIND_NOTIFICATION_LISTENER_SERVICE", "SYSTEM_ALERT_WINDOW"]]
COMPONENT_SET = CAP3 + [AP + x for x in ["BIND_DEVICE_ADMIN", "REQUEST_INSTALL_PACKAGES", "QUERY_ALL_PACKAGES"]]
LEGACY_SET = [AP + x for x in ["READ_PHONE_STATE", "GET_TASKS", "READ_LOGS", "WRITE_SETTINGS", "INSTALL_PACKAGES", "MOUNT_UNMOUNT_FILESYSTEMS", "RESTART_PACKAGES", "WRITE_EXTERNAL_STORAGE"]]
YEARS_TREND = list(range(2018, 2026)); YEARS_MATCH = list(range(2018, 2022))
REGISTRY_ROW = "NOV15_ANALYTICAL_DATASET_V1"
DANGEROUS_SELECTIONS = ("registered_full", "exploratory_1pct_either_arm")
STUDY_VERSION = "trend-study-v1.2"


@dataclass(frozen=True)
class StudyConfig:
    arm: str = "primary"
    weighting: str = "cluster"          # raw | cluster | one_per_cluster | signer_cluster
    estimator: str = "cluster_unit_recomputed"   # registered | fixed_design (S13)
    dangerous_selection: str = "registered_full"  # registered_full | exploratory_1pct_either_arm (S12)
    seed: int = DEFAULT_SEED
    n_resamples: int = DEFAULT_RESAMPLES
    include_2017: bool = False          # S2
    exclude_test_key: bool = False      # S3
    detection_floor: int = 4            # S4
    max_report_age_days: int | None = None  # S5
    time_axis: str = "year"             # S6: year | target_sdk_band | min_sdk_band
    batch_drop: str | None = None       # S7
    batch_only: str | None = None       # S7: mh100k_only | no_mh100k
    type_source: str = "v2"             # S8: v2 | v1_1 | avclass
    band_variant: str = "primary"       # S9: primary | tight | loose | unmatched_all_in
    casefold: bool = False              # S10
    matched_band_design: str = "registered_year_profile"   # v1.2 default | within_band_v1_1 (S14)
    description: str = "pre-registered primary analysis"
    registered: bool = True             # False for arms that are not in the pre-registration (exploratory)

    def __post_init__(self):
        if self.estimator not in ESTIMATORS:
            raise ValueError(f"unknown estimator {self.estimator!r}")
        if self.dangerous_selection not in DANGEROUS_SELECTIONS:
            raise ValueError(f"unknown dangerous_selection {self.dangerous_selection!r}")


def arm_catalog(batches: list[str]) -> dict[str, StudyConfig]:
    base = StudyConfig(); arms = {"primary": base}
    arms["S1_raw"] = replace(base, arm="S1_raw", weighting="raw", description="S1 weighting: raw rows", registered=False)
    for s in range(5):
        arms[f"S1_one_per_cluster_seed{s}"] = replace(base, arm=f"S1_one_per_cluster_seed{s}", weighting="one_per_cluster", seed=DEFAULT_SEED + s, description=f"S1 weighting: one row per cluster, seed {DEFAULT_SEED + s}", registered=False)
    arms["S2_include_2017"] = replace(base, arm="S2_include_2017", include_2017=True, description="S2: 2017 re-signed corpus included", registered=False)
    arms["S3_exclude_test_key"] = replace(base, arm="S3_exclude_test_key", exclude_test_key=True, description="S3: AOSP test key / Marco rows excluded", registered=False)
    arms["S4_floor2"] = replace(base, arm="S4_floor2", detection_floor=2, description="S4 detection floor 2 engines", registered=False); arms["S4_floor6"] = replace(base, arm="S4_floor6", detection_floor=6, description="S4 detection floor 6 engines", registered=False)
    arms["S5_age_le_365"] = replace(base, arm="S5_age_le_365", max_report_age_days=365, description="S5: analyses within 365 days of fetch only", registered=False)
    arms["S6_target_sdk_band"] = replace(base, arm="S6_target_sdk_band", time_axis="target_sdk_band", description="S6 time axis: target-SDK band", registered=False); arms["S6_min_sdk_band"] = replace(base, arm="S6_min_sdk_band", time_axis="min_sdk_band", description="S6 time axis: min-SDK band", registered=False)
    for b in batches:
        key = "S7_drop_" + "".join(ch if ch.isalnum() else "_" for ch in b)[:48]; arms[key] = replace(base, arm=key, batch_drop=b, description=f"S7 leave-one-out: drop batch {b}", registered=False)
    arms["S7_mh100k_only"] = replace(base, arm="S7_mh100k_only", batch_only="mh100k_only", description="S7: mh100k batch only", registered=False); arms["S7_no_mh100k"] = replace(base, arm="S7_no_mh100k", batch_only="no_mh100k", description="S7: all batches except mh100k", registered=False)
    arms["S8_type_v1_1"] = replace(base, arm="S8_type_v1_1", type_source="v1_1", description="S8 type from v1.1 where present", registered=False); arms["S8_type_avclass"] = replace(base, arm="S8_type_avclass", type_source="avclass", description="S8 type from AVClass class token only", registered=False)
    arms["S9_bands_tight"] = replace(base, arm="S9_bands_tight", band_variant="tight", description="S9 tight target-SDK bands", registered=False); arms["S9_bands_loose"] = replace(base, arm="S9_bands_loose", band_variant="loose", description="S9 loose bands", registered=False)
    arms["S9_unmatched_all_in_WRONG_REFERENCE"] = replace(base, arm="S9_unmatched_all_in_WRONG_REFERENCE", band_variant="unmatched_all_in", description="S9 deliberately wrong reference arm: no matching", registered=False)
    arms["S10_casefold"] = replace(base, arm="S10_casefold", casefold=True, description="S10 permission identity: lexical casefold", registered=False)
    arms["S11_signer_clusters"] = replace(base, arm="S11_signer_clusters", weighting="signer_cluster", description="S11 signer clusters as the unit", registered=False)
    arms["S12_dangerous_1pct_either_arm"] = replace(base, arm="S12_dangerous_1pct_either_arm", dangerous_selection="exploratory_1pct_either_arm", description="S12 exploratory: dangerous tier restricted to permissions with >= 1 % prevalence in either arm (v1 behaviour; not pre-registered)", registered=False)
    arms["S13_fixed_design_bootstrap"] = replace(base, arm="S13_fixed_design_bootstrap", estimator="fixed_design", description="S13 estimator: fixed original design weights inside the bootstrap (D0 / v1 behaviour; not the registered unit)", registered=False)
    arms["S14_matched_within_band_v1_1"] = replace(base, arm="S14_matched_within_band_v1_1", matched_band_design="within_band_v1_1", description="S14 matched-band design of v1.1: profile weights recomputed within SDK band, fixed capacities (not the registered year-population unit)", registered=False)
    return arms


def _type_column(frame: pd.DataFrame, source: str) -> pd.Series:
    if source == "v2":
        return frame["label_v2_type_v2"].replace("", np.nan)
    if source == "v1_1":
        return frame["label_v1_1_type_v1_1"].replace("", np.nan)
    if source == "avclass":
        def first_class(tok):
            if not isinstance(tok, str) or not tok:
                return np.nan
            first = tok.split(";")[0]
            return first.split(":", 1)[1].split("|")[0] if first.startswith("CLASS:") else np.nan
        return frame["label_v2_avclass_class_tokens"].apply(first_class)
    raise ValueError(source)


def _axis(frame: pd.DataFrame, cfg: StudyConfig, band_cfg: dict) -> pd.Series:
    if cfg.time_axis == "year":
        return frame["year"]
    col = "sdk_catalog_target" if cfg.time_axis == "target_sdk_band" else "sdk_catalog_min"
    return assign_band(frame[col], band_cfg)


def _filter(ds: TrendDataset, cfg: StudyConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Apply the arm's filters and return (malware, benign, ledger) where the ledger records every step's row count."""
    ledger = {"steps": []}
    def step(name, mal_n, ben_n, note=""):
        ledger["steps"].append({"step": name, "malware_rows": int(mal_n), "benign_rows": int(ben_n), "note": note})
    all_det = ds.detected(cfg.detection_floor, eligible_only=False); ben = ds.benign().copy()
    step("detected (floor) / benign source", len(all_det), len(ben), f"det_malicious >= {cfg.detection_floor} AND source_class_state != 'BENIGN_0'; label_v2_provenance == 'BENIGN_SOURCE_LABELED'")
    mal = ds.detected(cfg.detection_floor, eligible_only=not cfg.include_2017).copy()
    step("trend_year_eligible filter", len(mal), len(ben), "skipped (S2)" if cfg.include_2017 else "corpus_resigned_2017 rows removed")
    if cfg.exclude_test_key:
        mal = mal[~mal["test_key"]]; step("test-key rows removed (S3)", len(mal), len(ben))
    if cfg.max_report_age_days is not None:
        mal = mal[pd.to_numeric(mal["report_age_days"], errors="coerce") <= cfg.max_report_age_days]; ben = ben[pd.to_numeric(ben["report_age_days"], errors="coerce") <= cfg.max_report_age_days]
        step(f"report age <= {cfg.max_report_age_days} d (S5)", len(mal), len(ben))
    if cfg.batch_drop is not None:
        mal = mal[mal["batch"] != cfg.batch_drop]; ben = ben[ben["batch"] != cfg.batch_drop]; step(f"batch dropped (S7): {cfg.batch_drop}", len(mal), len(ben))
    if cfg.batch_only == "mh100k_only":
        mal = mal[mal["batch"].str.contains("mh100k", na=False)]; ben = ben[ben["batch"].str.contains("mh100k", na=False)]; step("mh100k batches only (S7)", len(mal), len(ben))
    if cfg.batch_only == "no_mh100k":
        mal = mal[~mal["batch"].str.contains("mh100k", na=False)]; ben = ben[~ben["batch"].str.contains("mh100k", na=False)]; step("mh100k batches excluded (S7)", len(mal), len(ben))
    step("with provider permission dictionary", mal["has_dict"].sum(), ben["has_dict"].sum(), "rows without a dictionary are counted here and excluded from permission statistics")
    return mal, ben, ledger


def _meta(ds: TrendDataset, cfg: StudyConfig, prereg_hash: str, denominator: str, n_rows: int, n_clusters: int, *, unit: str, estimand: str, extra: dict | None = None) -> dict:
    m = {"study_version": STUDY_VERSION, "dataset_sha256": ds.digest, "registry_row": REGISTRY_ROW, "denominator_entry": denominator, "n_rows": int(n_rows), "n_clusters": int(n_clusters),
         "unit": unit, "estimand": estimand, "estimator": cfg.estimator, "weighting_mode": cfg.weighting, "preregistration_sha256": prereg_hash, "arm": cfg.arm, "arm_description": cfg.description,
         "registered_arm": cfg.registered, "detection_floor": cfg.detection_floor, "seed": cfg.seed, "n_resamples": cfg.n_resamples, "dangerous_selection": cfg.dangerous_selection}
    if extra:
        m.update(extra)
    return m


def _write(out: Path, name: str, table: pd.DataFrame, meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True); table.to_csv(out / f"{name}.csv", index=False); (out / f"{name}.meta.json").write_text(json.dumps(meta, indent=1, default=str))


def _set_indicator(perms: pd.Series, members: list[str], casefold: bool) -> pd.Series:
    mem = {m.casefold() if casefold else m for m in members}
    return perms.apply(lambda ps: float(any((p.casefold() if casefold else p) in mem for p in (ps or []))))


def _cluster_col(cfg: StudyConfig) -> str | None:
    return {"cluster": "perm_profile_hash", "signer_cluster": "signer_thumbprint_raw"}.get(cfg.weighting)


def _series_with_bands(frame: pd.DataFrame, weights: pd.Series, indicator: pd.Series, axis: pd.Series, cfg: StudyConfig) -> pd.DataFrame:
    rows = []; ccol = _cluster_col(cfg)
    for level in sorted(axis.dropna().unique(), key=lambda v: (isinstance(v, str), v)):
        g = frame[(axis == level) & weights.notna()]
        if len(g) == 0:
            continue
        ind = indicator[g.index].to_numpy(dtype=float)[:, None]; w = weights[g.index].to_numpy(dtype=float)
        b = bands_for(cfg.estimator, ind, w, g[ccol].to_numpy() if ccol else None, g["batch"].to_numpy(), n_resamples=cfg.n_resamples, seed=cfg.seed)
        rows.append({"axis": level, "weighted": float(b["point"][0]), "raw": float(ind.mean()), "lo95": float(b["lo"][0]), "hi95": float(b["hi"][0]), "n_rows": int(len(g)), "n_clusters": int(g["perm_profile_hash"].nunique()), "n_batches": b["n_batches"], "estimator": b["estimator"]})
    return pd.DataFrame(rows)


def _dangerous_universe(mal: pd.DataFrame, ben: pd.DataFrame, w_m: pd.Series, w_b: pd.Series, dangerous: list[str], cfg: StudyConfig) -> tuple[list[str], dict]:
    """registered_full: every dangerous-tier permission of the fixture (unobserved ones are reported with observed_any False).
    exploratory_1pct_either_arm: v1 behaviour, kept only as the labelled exploratory arm S12."""
    im = indicator_matrix(mal.loc[w_m.notna(), "perms"], dangerous, cfg.casefold).mean(axis=0) if w_m.notna().any() else np.zeros(len(dangerous))
    ib = indicator_matrix(ben.loc[w_b.notna(), "perms"], dangerous, cfg.casefold).mean(axis=0) if w_b.notna().any() else np.zeros(len(dangerous))
    observed = [p for p, a, b in zip(dangerous, im, ib) if a > 0 or b > 0]
    if cfg.dangerous_selection == "registered_full":
        universe = list(dangerous)
    else:
        universe = [p for p, a, b in zip(dangerous, im, ib) if a >= 0.01 or b >= 0.01]
    return universe, {"rule": cfg.dangerous_selection, "fixture_dangerous_total": len(dangerous), "observed_in_either_arm": len(observed), "selected": len(universe),
                      "omitted": sorted(set(dangerous) - set(universe)), "registered": cfg.dangerous_selection == "registered_full"}


def run_study(ds: TrendDataset, cfg: StudyConfig, out: Path, prereg_hash: str, annotations: dict | None, dangerous: list[str], band_config_path: str | Path | None = None, tables: tuple[str, ...] = ("T1", "TB", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "scorecard"), make_figures: bool = True) -> dict:
    t0 = time.time(); started = datetime.now(timezone.utc).isoformat(); out.mkdir(parents=True, exist_ok=True); figs = out / "figures"
    band_cfg = load_band_config(band_config_path, "primary" if cfg.band_variant == "unmatched_all_in" else cfg.band_variant)
    mal, ben, ledger = _filter(ds, cfg)
    w_m = weights_for_mode(mal, cfg.weighting, cfg.seed); w_b = weights_for_mode(ben, cfg.weighting, cfg.seed); ccol = _cluster_col(cfg)
    axis_m = _axis(mal, cfg, band_cfg); axis_b = _axis(ben, cfg, band_cfg)
    mal = mal.assign(_axis=axis_m); ben = ben.assign(_axis=axis_b)
    typecol = _type_column(mal, cfg.type_source); mal = mal.assign(_type=typecol)
    six = typecol[w_m.notna()].dropna().value_counts().head(6).index.tolist()
    den_rows = f"DETECTED_V2 (floor {cfg.detection_floor}; eligible={'all years' if cfg.include_2017 else 'trend_year_eligible'})"
    unit = {"cluster": "permission-profile cluster within year x population (perm_profile_hash)", "signer_cluster": "signer cluster within year x population", "raw": "row", "one_per_cluster": "one sampled row per cluster"}[cfg.weighting]
    manifest = {"study_version": STUDY_VERSION, "code_commit": _code_commit(), "started_utc": started, "config": asdict(cfg), "rows_malware": int(len(mal)), "rows_malware_with_dict": int(w_m.notna().sum()), "rows_benign": int(len(ben)), "rows_benign_with_dict": int(w_b.notna().sum()), "six_types": six, "tables": {}}
    perm_universe, dang_ledger = _dangerous_universe(mal, ben, w_m, w_b, dangerous, cfg)
    comp = list(COMPONENT_SET); t2t3 = perm_universe + [p for p in comp if p not in perm_universe]
    full = ds.detected(cfg.detection_floor, eligible_only=False)
    years_all = sorted(int(y) for y in full["year"].dropna().unique())            # data-derived: v1 hard-coded 2011..2026 and lost 2010
    levels_trend = YEARS_TREND if cfg.time_axis == "year" else sorted(axis_m.dropna().unique(), key=str)
    ledger.update({"dangerous_selection": dang_ledger, "years_in_detected_population": years_all, "stored_group_cross_check": ds.check_stored_groups(), "unit": unit, "estimator": cfg.estimator})
    (out / "selection_ledger.json").write_text(json.dumps(ledger, indent=1, default=str))
    band_kw = {"estimator": cfg.estimator, "cluster_col": ccol, "n_resamples": cfg.n_resamples, "seed": cfg.seed}
    # T1 (D0 table a): every year with a detected row
    if "T1" in tables:
        rows = []
        for y in years_all:
            g = full[full["year"] == y]; d = g[g["has_dict"]]
            rows.append({"year": y, "rows": len(g), "rows_with_dict": len(d), "clusters": int(d["perm_profile_hash"].nunique()), "with_family": int(g["label_has_family_v2"].fillna(False).astype(bool).sum()), "type_only": int((g["label_has_type_v2"].fillna(False).astype(bool) & ~g["label_has_family_v2"].fillna(False).astype(bool)).sum()),
                         "test_key_rows": int(g["test_key"].sum()), "resigned_2017_rows": int(g["corpus_resigned_2017"].fillna(False).astype(bool).sum()), "trend_eligible_rows": int(g["trend_year_eligible"].fillna(False).astype(bool).sum()), "trend_eligible_year": bool(g["trend_year_eligible"].fillna(False).astype(bool).all()) if len(g) else False, "report_age_median_days": float(pd.to_numeric(g["report_age_days"], errors="coerce").median())})
        t1 = pd.DataFrame(rows); assert int(t1["rows"].sum()) == len(full), "T1 must account for every detected row"
        _write(out, "T1_detected_per_year", t1, _meta(ds, cfg, prereg_hash, f"DETECTED_V2 (floor {cfg.detection_floor}; all years with rows shown; eligibility marked)", len(full), full[full["has_dict"]]["perm_profile_hash"].nunique(), unit="row (counts) and profile cluster (clusters column)", estimand="per-year counts", extra={"rows_total_check": int(t1["rows"].sum())}))
        if make_figures: manifest["tables"]["T1"] = F.fig_rows_clusters(t1, figs)
    def prev_by_axis(frame, weights, perms, levels):
        f2 = frame.assign(year=frame["_axis"]); return prevalence_table(f2, perms, weights, levels, casefold=cfg.casefold, **band_kw)
    # TB (D0 table b): top-30 per year by raw prevalence, with weighted value and rank; heatmap over the union of per-year top-10 with every displayed year measured
    if "TB" in tables and cfg.time_axis == "year":
        rows = []; union_top10 = set()
        for y in years_all:
            g = mal[(mal["year"] == y) & w_m.notna()]
            if len(g) == 0: continue
            top = top_permissions(g, w_m[g.index], 30); tab = prevalence_table(g, top, w_m, [y], casefold=cfg.casefold, **band_kw); tab["rank_raw"] = tab["raw_prevalence"].rank(ascending=False, method="first").astype(int)
            union_top10 |= set(tab[tab["rank_raw"] <= 10]["permission"]); rows.append(tab)
        tb = pd.concat(rows) if rows else pd.DataFrame()
        _write(out, "TB_top30_per_year", tb, _meta(ds, cfg, prereg_hash, den_rows + " ∩ PROVIDER_DICT_PRESENT", w_m.notna().sum(), mal[w_m.notna()]["perm_profile_hash"].nunique(), unit=unit, estimand="raw and cluster-weighted prevalence of the 30 most frequent permissions per year", extra={"ranking": "raw prevalence within year"}))
        if make_figures and len(tb):
            hm = prevalence_table(mal, sorted(union_top10), w_m, years_all, casefold=cfg.casefold, estimator="fixed_design", cluster_col=ccol, n_resamples=2, seed=cfg.seed)  # points only; bands not drawn
            manifest["tables"]["TB"] = F.fig_heatmap(hm[["permission", "year", "weighted_prevalence"]], figs, "TB_top10_union_heatmap", "permission", "year", "weighted_prevalence", "TB cluster-weighted prevalence, union of per-year top-10 (every displayed year measured)")
    # T2 / T3 / T8
    if "T2" in tables:
        t2 = prev_by_axis(mal, w_m, perm_universe, levels_trend)
        _write(out, "T2_dangerous_prevalence", t2, _meta(ds, cfg, prereg_hash, den_rows + " ∩ PROVIDER_DICT_PRESENT ∩ years " + str(levels_trend[0]) + "-" + str(levels_trend[-1]), int(mal[mal["_axis"].isin(levels_trend) & w_m.notna()].shape[0]), int(mal[mal["_axis"].isin(levels_trend) & w_m.notna()].groupby("_axis")["perm_profile_hash"].nunique().sum()), unit=unit, estimand="cluster-weighted prevalence per axis level (sum of per-level cluster counts in n_clusters)", extra={"axis": cfg.time_axis, "permissions": perm_universe, "dangerous_selection_ledger": dang_ledger}))
        if make_figures and len(t2):
            shown = t2[t2["permission"].isin(t2.groupby("permission")["raw_prevalence"].mean().nlargest(8).index)]
            manifest["tables"]["T2"] = F.fig_prevalence_lines(shown, figs, "T2_dangerous_prevalence", annotations if cfg.time_axis == "year" else None, title="T2 dangerous-tier prevalence (cluster-weighted, top 8 shown)")
    if "T3" in tables:
        t3 = prev_by_axis(mal, w_m, comp, levels_trend); _write(out, "T3_component_prevalence", t3, _meta(ds, cfg, prereg_hash, den_rows + " ∩ PROVIDER_DICT_PRESENT", int(mal[mal["_axis"].isin(levels_trend) & w_m.notna()].shape[0]), int(mal[mal["_axis"].isin(levels_trend) & w_m.notna()].groupby("_axis")["perm_profile_hash"].nunique().sum()), unit=unit, estimand="cluster-weighted prevalence per axis level", extra={"axis": cfg.time_axis, "permissions": comp, "registered_table": False, "note": "T3 is not in the pre-registration (exploratory table)"}))
        if make_figures and len(t3): manifest["tables"]["T3"] = F.fig_prevalence_lines(t3, figs, "T3_component_prevalence", annotations if cfg.time_axis == "year" else None, title="T3 component-bound capability prevalence (exploratory table)")
    if "T8" in tables and cfg.time_axis == "year":
        band_axis = assign_band(mal["sdk_catalog_target"], band_cfg); levels = [b["name"] for b in band_cfg["bands"]] + [band_cfg["null_band"]]
        t8 = prev_by_axis(mal.assign(_axis=band_axis), w_m, t2t3, levels); t8 = t8.rename(columns={"year": "target_sdk_band"})
        _write(out, "T8_sdk_era_prevalence", t8, _meta(ds, cfg, prereg_hash, den_rows + " ∩ PROVIDER_DICT_PRESENT", w_m.notna().sum(), int(mal[w_m.notna()].assign(_b=band_axis).groupby("_b")["perm_profile_hash"].nunique().sum()), unit=unit, estimand="cluster-weighted prevalence per target-SDK band", extra={"axis": "target_sdk_band", "registered_table": False}))
        if make_figures and len(t8): manifest["tables"]["T8"] = F.fig_heatmap(t8[t8["observed_any"] | True][["permission", "target_sdk_band", "weighted_prevalence"]], figs, "T8_sdk_era_prevalence", "permission", "target_sdk_band", "weighted_prevalence", "T8 prevalence by target-SDK band (cluster-weighted)")
    # T4 (D0 table c): matched year x target-SDK band, dictionary-conditioned strata
    if "T4" in tables:
        rows = []; st = strata(mal, ben, YEARS_MATCH, band_cfg, w_m=w_m, w_b=w_b)
        perms4 = t2t3 + ["SET:SMS_OR_CALL_LOG_ANY", "SET:CAPABILITY3_ANY", "SET:LEGACY_ANY"]
        members = {p: {"SET:SMS_OR_CALL_LOG_ANY": SMS_SET, "SET:CAPABILITY3_ANY": CAP3, "SET:LEGACY_ANY": LEGACY_SET}.get(p, [p]) for p in perms4}
        im_all = np.column_stack([_set_indicator(mal["perms"], members[p], cfg.casefold).to_numpy() for p in perms4]); ib_all = {p: _set_indicator(ben["perms"], members[p], cfg.casefold) for p in perms4}
        rep_clusters = 0; t4_unit_checks = {}
        for y in YEARS_MATCH:
            caps = {}; nben = {}
            if cfg.band_variant != "unmatched_all_in":
                stt = st[(st["year"] == y) & (~st["dropped"])]; caps = dict(zip(stt["band"], stt["matched_capacity"].astype(float))); nben = dict(zip(stt["band"], stt["benign_rows"].astype(int)))
                rep_clusters += int(stt["malware_clusters"].sum() + stt["benign_clusters"].sum())
            if caps and cfg.matched_band_design == "within_band_v1_1":
                lo, hi, nb = matched_malware_band_bootstrap_v1_1(mal, im_all, w_m, y, band_cfg, caps, cfg.n_resamples, cfg.seed, estimator=cfg.estimator, cluster_col=ccol); lo_f = hi_f = np.full(len(perms4), np.nan)
            elif caps:
                sub_mask = (mal["year"] == y) & w_m.notna(); res = matched_malware_bootstrap_registered(mal[sub_mask], im_all[sub_mask.to_numpy()], y, band_cfg, nben, cfg.n_resamples, cfg.seed, cluster_col=ccol or "perm_profile_hash")
                lo, hi, nb = res["lo_recomputed"], res["hi_recomputed"], res["n_batches"]; lo_f, hi_f = res["lo_fixed"], res["hi_fixed"]; t4_unit_checks[str(y)] = {"unit_mass_check": res["unit_mass_check"], "indicator_constant_within_cluster": res["indicator_constant_within_cluster"], "n_profiles": res["n_profiles"], "n_batches": res["n_batches"], "capacities_point": res["capacities_point"]}
            else:
                lo = hi = lo_f = hi_f = np.full(len(perms4), np.nan); nb = int(mal[(mal["year"] == y)]["batch"].nunique())
            for j, p in enumerate(perms4):
                r = matched_prevalence(mal, ben, pd.Series(im_all[:, j], index=mal.index), ib_all[p], w_m, w_b, y, band_cfg, unmatched_all_in=cfg.band_variant == "unmatched_all_in")
                rows.append({"permission": p, "year": y, "malware": r["malware"], "benign": r["benign"], "difference": (r["malware"] - r["benign"]) if not (pd.isna(r["malware"]) or pd.isna(r["benign"])) else np.nan, "malware_lo95": float(lo[j]), "malware_hi95": float(hi[j]), "malware_lo95_fixed_capacity": float(lo_f[j]), "malware_hi95_fixed_capacity": float(hi_f[j]), "matched_capacity": r["capacity"], "bands_used": "|".join(map(str, r["bands_used"])), "bands_dropped": "|".join(map(str, r["bands_dropped"])), "malware_batches": nb, "benign_batches": int(ben[ben["year"] == y]["batch"].nunique()), "estimator": cfg.estimator, "matched_band_design": cfg.matched_band_design})
        t4 = pd.DataFrame(rows)
        n4 = int((mal["year"].isin(YEARS_MATCH) & w_m.notna()).sum()) + int((ben["year"].isin(YEARS_MATCH) & w_b.notna()).sum())
        _write(out, "T4_matched_benign_vs_malware", t4, _meta(ds, cfg, prereg_hash, den_rows + " ∩ 2018-2021 ∩ PROVIDER_DICT_PRESENT vs BENIGN_SOURCE_V2 ∩ PROVIDER_DICT_PRESENT; matched year × target-SDK band (" + cfg.band_variant + ")", n4, rep_clusters, unit=unit, estimand="capacity-weighted standardized prevalence over year x target-SDK bands with both sides present; capacity = min(dictionary-conditioned malware rows, benign rows) per band", extra={"band_variant": cfg.band_variant, "malware_band_resamples": cfg.n_resamples, "matched_band_design": cfg.matched_band_design, "band_columns": "malware_lo95/hi95 = recomputed capacities (min(resampled malware rows, benign rows) per band); malware_lo95/hi95_fixed_capacity = original capacities; registration rule 5 is silent on which, so both are reported", "unit_checks": t4_unit_checks, "n_clusters_definition": "sum over used strata of distinct profile clusters, malware plus benign", "capacity_definition": "dictionary-conditioned (v1 reported all-rows capacity; both are in T4_strata)"}))
        _write(out, "T4_strata", st, _meta(ds, cfg, prereg_hash, "matching strata (both capacity definitions retained)", len(st), int(st["malware_clusters"].sum() + st["benign_clusters"].sum()), unit="stratum (year x band)", estimand="row and cluster counts per stratum"))
        if make_figures and len(t4): manifest["tables"]["T4"] = F.fig_matched(t4[t4["permission"].isin(["SET:SMS_OR_CALL_LOG_ANY", "SET:CAPABILITY3_ANY", AP + "SYSTEM_ALERT_WINDOW", AP + "READ_PHONE_STATE", AP + "READ_SMS", AP + "ACCESS_FINE_LOCATION"])], figs)
    # T5 per type (exploratory table)
    if "T5" in tables:
        rows = []
        for t in six:
            sub = mal[mal["_type"] == t]; tab = prev_by_axis(sub, w_m[sub.index], t2t3, levels_trend); tab["type"] = t; rows.append(tab)
        t5 = pd.concat(rows) if rows else pd.DataFrame()
        _write(out, "T5_type_prevalence", t5, _meta(ds, cfg, prereg_hash, den_rows + " ∩ six types ∩ PROVIDER_DICT_PRESENT", int((w_m.notna() & mal["_type"].isin(six)).sum()), int(mal[w_m.notna() & mal["_type"].isin(six)].groupby(["_type", "_axis"])["perm_profile_hash"].nunique().sum()), unit=unit, estimand="cluster-weighted prevalence per type x axis level", extra={"six_types": six, "type_source": cfg.type_source, "registered_table": False}))
        if make_figures and len(t5):
            last = 2025 if cfg.time_axis == "year" else t5["year"].iloc[-1]; shown = t5[(t5["year"] == last)].copy(); shown.loc[~shown["observed_any"], "weighted_prevalence"] = shown.loc[~shown["observed_any"], "weighted_prevalence"]  # true zeros stay zero; unmeasured cells are absent rows
            manifest["tables"]["T5"] = F.fig_heatmap(shown[["permission", "type", "weighted_prevalence"]], figs, "T5_type_prevalence_last", "permission", "type", "weighted_prevalence", f"T5 per-type prevalence ({last})")
    # T6 (D0 table e)
    if "T6" in tables:
        rows = []
        for level in sorted(mal["_axis"].dropna().unique(), key=str):
            g = mal[(mal["_axis"] == level) & w_m.notna() & mal["_type"].isin(six)]
            if len(g) == 0: continue
            _, vec, nrows = type_profile_vectors(g, w_m[g.index], "_type", six); tab = pairwise_jsd(vec, nrows); tab.insert(0, "year", level); rows.append(tab)
        t6 = pd.concat(rows) if rows else pd.DataFrame()
        _write(out, "T6_type_jsd", t6, _meta(ds, cfg, prereg_hash, den_rows + " ∩ six types ∩ PROVIDER_DICT_PRESENT", int((w_m.notna() & mal["_type"].isin(six)).sum()), int(mal[w_m.notna() & mal["_type"].isin(six)].groupby("_axis")["perm_profile_hash"].nunique().sum()), unit=unit, estimand="Jensen-Shannon distance (base 2) between cluster-weighted type profiles per axis level; THIN below 30 rows", extra={"six_types": six}))
        if make_figures and len(t6): manifest["tables"]["T6"] = F.fig_jsd(t6, figs)
    # T7 (D0 table d)
    if "T7" in tables:
        rows = []
        for y in years_all:
            g = mal[mal["year"] == y]
            if len(g) == 0: continue
            sig = g["signer_thumbprint_raw"].dropna(); prof = g[g["has_dict"]]["perm_profile_hash"].dropna()
            rows.append({"year": y, "rows": len(g), "rows_with_signer": len(sig), "signers": int(sig.nunique()), "top10_signer_share_of_signed_rows": top_k_share(sig), "top10_signer_share_of_all_rows": float(sig.value_counts().head(10).sum() / len(g)) if len(g) else np.nan, "signer_herfindahl": herfindahl(sig),
                         "rows_with_profile": len(prof), "profiles": int(prof.nunique()), "top10_profile_share_of_profile_rows": top_k_share(prof), "profile_herfindahl": herfindahl(prof), "test_key_share_of_all_rows": float(g["test_key"].mean())})
        t7 = pd.DataFrame(rows)
        _write(out, "T7_concentration", t7, _meta(ds, cfg, prereg_hash, den_rows, len(mal), mal[mal["has_dict"]]["perm_profile_hash"].nunique(), unit="row", estimand="share of rows in the 10 largest signer / profile groups; Herfindahl over groups; denominators named in each column", extra={"denominator_note": "rule 8 excludes rows without a thumbprint/dictionary from the group-share denominator; the *_of_all_rows columns are given for the whole detected population"}))
        if make_figures and len(t7): manifest["tables"]["T7"] = F.fig_concentration(t7.rename(columns={"top10_signer_share_of_signed_rows": "top10_signer_share", "top10_profile_share_of_profile_rows": "top10_profile_share", "test_key_share_of_all_rows": "test_key_share"}), figs)
    # scorecard (D0 table f; pre-registered rules; always on the year axis)
    if "scorecard" in tables:
        yaxis = mal["year"]; series = {}
        for name, mem in [("SMS_OR_CALL_LOG_ANY", SMS_SET), ("CAPABILITY3_ANY", CAP3), ("LEGACY_ANY_eligible", LEGACY_SET)]:
            series[name] = _series_with_bands(mal, w_m, _set_indicator(mal["perms"], mem, cfg.casefold), yaxis, cfg).set_index("axis")
        wf = weights_for_mode(full, cfg.weighting, cfg.seed)
        series["LEGACY_ANY_all_detected"] = _series_with_bands(full, wf, _set_indicator(full["perms"], LEGACY_SET, cfg.casefold), full["year"], cfg).set_index("axis")
        for n, s in series.items(): s.reset_index().to_csv(out / f"series_{n}.csv", index=False)
        t4p = pd.read_csv(out / "T4_matched_benign_vs_malware.csv") if (out / "T4_matched_benign_vs_malware.csv").exists() else None
        t6p = pd.read_csv(out / "T6_type_jsd.csv") if (out / "T6_type_jsd.csv").exists() else None
        sc = scorecard(series, t4p, mal, w_m, t6p, cfg)
        if P3_DETAIL: (out / "P3_fixed_target_detail.json").write_text(json.dumps(P3_DETAIL, indent=1, default=str))
        inputs = {"P1": {"series": "series_SMS_OR_CALL_LOG_ANY.csv", "matched": "T4 SET:SMS_OR_CALL_LOG_ANY", "denominator": den_rows + " ∩ PROVIDER_DICT_PRESENT; matched 2018-2021"}, "P2": {"series": "series_CAPABILITY3_ANY.csv", "matched": "T4 SET:CAPABILITY3_ANY"}, "P3": {"table": "2024 top-10 by raw prevalence", "n_rows": int(((mal["year"] == 2024) & w_m.notna()).sum())}, "P4": {"table": "T6 banker/rat 2019 vs 2024"}, "P5": {"series": ["series_LEGACY_ANY_all_detected.csv", "series_LEGACY_ANY_eligible.csv"]}}
        _write(out, "scorecard", sc, _meta(ds, cfg, prereg_hash, "pre-registered rules; per-prediction inputs listed in prediction_inputs", len(mal), int(mal[w_m.notna()].groupby("year")["perm_profile_hash"].nunique().sum()), unit=unit, estimand="mechanical verdicts P1-P5", extra={"prediction_inputs": inputs}))
        if make_figures: manifest["tables"]["scorecard"] = F.fig_scorecard(sc, figs)
    manifest["wall_clock_seconds"] = round(time.time() - t0, 1); manifest["finished_utc"] = datetime.now(timezone.utc).isoformat(); (out / "run_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    return manifest
P3_DETAIL: dict = {}


def _code_commit() -> str | None:
    import subprocess
    try: return subprocess.run(["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception: return None


def _get(series: pd.DataFrame, year: int, col: str):
    return float(series.loc[year, col]) if year in series.index else np.nan


def scorecard(series: dict, t4: pd.DataFrame | None, mal: pd.DataFrame, w_m: pd.Series, t6: pd.DataFrame | None, cfg: StudyConfig) -> pd.DataFrame:
    rows = []
    def t4v(perm, year, col):
        if t4 is None: return np.nan
        r = t4[(t4["permission"] == perm) & (t4["year"] == year)]; return float(r.iloc[0][col]) if len(r) else np.nan
    s = series["SMS_OR_CALL_LOG_ANY"]; m19, m25 = _get(s, 2019, "weighted"), _get(s, 2025, "weighted"); lo19, hi19, lo25, hi25 = _get(s, 2019, "lo95"), _get(s, 2019, "hi95"), _get(s, 2025, "lo95"), _get(s, 2025, "hi95")
    b18, b21, mm18, mm21 = t4v("SET:SMS_OR_CALL_LOG_ANY", 2018, "benign"), t4v("SET:SMS_OR_CALL_LOG_ANY", 2021, "benign"), t4v("SET:SMS_OR_CALL_LOG_ANY", 2018, "malware"), t4v("SET:SMS_OR_CALL_LOG_ANY", 2021, "malware")
    if any(np.isnan(x) for x in [m19, m25, lo19, hi19, lo25, hi25, b18, b21, mm18, mm21]): v, why = "INCONCLUSIVE", "missing bands or matched values"
    else:
        decl = m25 < m19 and hi25 < lo19; v = "SUPPORTED" if (decl and (b18 - b21) > (mm18 - mm21)) else "NOT SUPPORTED"
        why = f"malware weighted 2019={m19:.3f} [{lo19:.3f},{hi19:.3f}] -> 2025={m25:.3f} [{lo25:.3f},{hi25:.3f}]; decline with disjoint bands={decl}; matched 2018->2021 drop benign={b18 - b21:+.3f} vs malware={mm18 - mm21:+.3f}"
    rows.append({"prediction": "P1", "verdict": v, "decided_by": "series_SMS_OR_CALL_LOG_ANY + T4 SET:SMS_OR_CALL_LOG_ANY", "evidence": why})
    s = series["CAPABILITY3_ANY"]; m19, m24, m25 = _get(s, 2019, "weighted"), _get(s, 2024, "weighted"), _get(s, 2025, "weighted"); hi19, lo24, lo25 = _get(s, 2019, "hi95"), _get(s, 2024, "lo95"), _get(s, 2025, "lo95")
    b18, b21 = t4v("SET:CAPABILITY3_ANY", 2018, "benign"), t4v("SET:CAPABILITY3_ANY", 2021, "benign")
    if any(np.isnan(x) for x in [m19, m24, m25, hi19, lo24, lo25, b18, b21]): v, why = "INCONCLUSIVE", "missing bands or matched values"
    else:
        rise = (m24 > m19 and lo24 > hi19) and (m25 > m19 and lo25 > hi19); flat = abs(b21 - b18) < 0.02; v = "SUPPORTED" if (rise and flat) else "NOT SUPPORTED"
        why = f"malware weighted 2019={m19:.3f} (hi {hi19:.3f}), 2024={m24:.3f} (lo {lo24:.3f}), 2025={m25:.3f} (lo {lo25:.3f}); rise with disjoint bands={rise}; benign matched 2018={b18:.3f} -> 2021={b21:.3f} (|Δ|<2pp={flat})"
    rows.append({"prediction": "P2", "verdict": v, "decided_by": "series_CAPABILITY3_ANY + T4 SET:CAPABILITY3_ANY", "evidence": why})
    g = mal[(mal["year"] == 2024) & w_m.notna()]
    if len(g):
        top = top_permissions(g, w_m[g.index], 10); ind = indicator_matrix(g["perms"], top, cfg.casefold); w = w_m[g.index].to_numpy(dtype=float); raw = ind.mean(axis=0); wt = (ind * w[:, None]).sum(axis=0) / w.sum(); diffs = 100 * np.abs(raw - wt); j = int(np.argmax(diffs))
        # v1.2: the target is fixed HERE, on the original rows, before any resampling or removal; nothing below re-selects a maximum
        detail = fixed_target_gap_bootstrap(g, top[j], cfg.n_resamples, cfg.seed, cluster_col="perm_profile_hash") if cfg.weighting in ("cluster", "one_per_cluster") or True else None
        P3_DETAIL.clear(); P3_DETAIL.update(detail)
        band = f"; paired batch-resampled gap interval [{detail['gap_lo95_pp']:.2f}, {detail['gap_hi95_pp']:.2f}] pp (includes zero: {detail['gap_includes_zero']}); largest profile contribution {detail['top_contributions'][0]['contribution_pp']:.2f} pp ({detail['top_contributions'][0]['rows']} rows)" if detail.get("gap_lo95_pp") is not None else "; no batch band (fewer than 2 batches)"
        loo = detail["leave_one_batch_out_fixed_target"]; worst = min(loo, key=lambda d: d["gap_pp"]) if loo else None
        band += f"; fixed-target gap without the single most influential batch ({worst['batch_removed']}, {worst['rows_removed']} rows removed): {worst['gap_pp']:.2f} pp" if worst else ""
        rows.append({"prediction": "P3", "verdict": "SUPPORTED" if diffs[j] > 10 else "NOT SUPPORTED", "decided_by": "2024 top-10 raw vs weighted (registered point rule); interval, decomposition and fixed-target removal are reported, not part of the rule", "evidence": f"largest |raw-weighted| = {diffs[j]:.1f} pp ({top[j]}); raw={raw[j]:.3f}, weighted={wt[j]:.3f}, n={len(g)}" + band})
    else: rows.append({"prediction": "P3", "verdict": "INCONCLUSIVE", "decided_by": "2024 top-10", "evidence": "no 2024 rows in this arm"})
    if t6 is not None and len(t6):
        def js(y):
            r = t6[(t6["year"].astype(str) == str(y)) & (t6["type_a"].isin(["banker", "rat"])) & (t6["type_b"].isin(["banker", "rat"]))]; return (float(r.iloc[0]["js_distance"]), bool(r.iloc[0]["thin"])) if len(r) else (np.nan, True)
        (d19, th19), (d24, th24) = js(2019), js(2024)
        if np.isnan(d19) or np.isnan(d24): v, why = "INCONCLUSIVE", "banker/rat pair missing in 2019 or 2024"
        elif th19 or th24: v, why = "INCONCLUSIVE", f"JS(banker,rat) 2019={d19:.4f} (thin={th19}), 2024={d24:.4f} (thin={th24})"
        else: v, why = ("SUPPORTED" if d24 < d19 else "NOT SUPPORTED"), f"JS(banker,rat) 2019={d19:.4f}, 2024={d24:.4f}"
    else: v, why = "INCONCLUSIVE", "T6 not computed in this arm"
    rows.append({"prediction": "P4", "verdict": v, "decided_by": "T6 banker-rat 2019 vs 2024", "evidence": why})
    la = series["LEGACY_ANY_all_detected"]; le = series["LEGACY_ANY_eligible"]; v16, v17, v18 = _get(la, 2016, "weighted"), _get(la, 2017, "weighted"), _get(la, 2018, "weighted")
    if any(np.isnan(x) for x in [v16, v17, v18]): v, why = "INCONCLUSIVE", "missing 2016-2018"
    else:
        spike = (v17 - v16 > 0.10) and (v17 - v18 > 0.10); n_el = int(_get(le, 2017, "n_rows")) if 2017 in le.index else 0; e17 = _get(le, 2017, "weighted")
        if not spike: v, why = "NOT SUPPORTED", f"no spike: all-detected legacy share 2016={v16:.3f}, 2017={v17:.3f}, 2018={v18:.3f}"
        elif n_el < 30: v, why = "INCONCLUSIVE", f"spike exists but only {n_el} eligible 2017 rows remain"
        else: removed = abs(e17 - (v16 + v18) / 2) <= 0.10; v, why = ("SUPPORTED" if removed else "NOT SUPPORTED"), f"spike 2017={v17:.3f}; eligible-only 2017={e17:.3f} (n={n_el}); within 10pp of neighbour mean={removed}"
    rows.append({"prediction": "P5", "verdict": v, "decided_by": "series_LEGACY_ANY_all_detected vs series_LEGACY_ANY_eligible", "evidence": why})
    return pd.DataFrame(rows)
