"""The pre-registered study (T1–T8 + scorecard) and its sensitivity arms. Descriptive statistics only."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from obsidiandroid.research.trends import figures as F
from obsidiandroid.research.trends.bootstrap import DEFAULT_RESAMPLES, DEFAULT_SEED, per_batch_sums, ratio_bands
from obsidiandroid.research.trends.dataset import TrendDataset
from obsidiandroid.research.trends.matching import assign_band, load_band_config, matched_malware_band_bootstrap, matched_prevalence, strata
from obsidiandroid.research.trends.metrics import herfindahl, indicator_matrix, pairwise_jsd, prevalence_table, slope_with_band, top_k_share, top_permissions, type_profile_vectors
from obsidiandroid.research.trends.weighting import weights_for_mode

AP = "android.permission."
SMS_SET = [AP + x for x in ["READ_SMS", "RECEIVE_SMS", "SEND_SMS", "RECEIVE_MMS", "RECEIVE_WAP_PUSH", "READ_CALL_LOG", "WRITE_CALL_LOG", "PROCESS_OUTGOING_CALLS"]]
CAP3 = [AP + x for x in ["BIND_ACCESSIBILITY_SERVICE", "BIND_NOTIFICATION_LISTENER_SERVICE", "SYSTEM_ALERT_WINDOW"]]
COMPONENT_SET = CAP3 + [AP + x for x in ["BIND_DEVICE_ADMIN", "REQUEST_INSTALL_PACKAGES", "QUERY_ALL_PACKAGES"]]
LEGACY_SET = [AP + x for x in ["READ_PHONE_STATE", "GET_TASKS", "READ_LOGS", "WRITE_SETTINGS", "INSTALL_PACKAGES", "MOUNT_UNMOUNT_FILESYSTEMS", "RESTART_PACKAGES", "WRITE_EXTERNAL_STORAGE"]]
YEARS_ALL = list(range(2011, 2027)); YEARS_TREND = list(range(2018, 2026)); YEARS_MATCH = list(range(2018, 2022))
REGISTRY_ROW = "NOV15_ANALYTICAL_DATASET_V1"


@dataclass(frozen=True)
class StudyConfig:
    arm: str = "primary"
    weighting: str = "cluster"          # raw | cluster | one_per_cluster | signer_cluster
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
    description: str = "pre-registered primary analysis"


def arm_catalog(batches: list[str]) -> dict[str, StudyConfig]:
    base = StudyConfig(); arms = {"primary": base}
    arms["S1_raw"] = replace(base, arm="S1_raw", weighting="raw", description="S1 weighting: raw rows")
    for s in range(5):
        arms[f"S1_one_per_cluster_seed{s}"] = replace(base, arm=f"S1_one_per_cluster_seed{s}", weighting="one_per_cluster", seed=DEFAULT_SEED + s, description=f"S1 weighting: one row per cluster, seed {DEFAULT_SEED + s}")
    arms["S2_include_2017"] = replace(base, arm="S2_include_2017", include_2017=True, description="S2: 2017 re-signed corpus included")
    arms["S3_exclude_test_key"] = replace(base, arm="S3_exclude_test_key", exclude_test_key=True, description="S3: AOSP test key / Marco rows excluded")
    arms["S4_floor2"] = replace(base, arm="S4_floor2", detection_floor=2, description="S4 detection floor 2 engines"); arms["S4_floor6"] = replace(base, arm="S4_floor6", detection_floor=6, description="S4 detection floor 6 engines")
    arms["S5_age_le_365"] = replace(base, arm="S5_age_le_365", max_report_age_days=365, description="S5: analyses within 365 days of fetch only")
    arms["S6_target_sdk_band"] = replace(base, arm="S6_target_sdk_band", time_axis="target_sdk_band", description="S6 time axis: target-SDK band"); arms["S6_min_sdk_band"] = replace(base, arm="S6_min_sdk_band", time_axis="min_sdk_band", description="S6 time axis: min-SDK band")
    for b in batches:
        key = "S7_drop_" + "".join(ch if ch.isalnum() else "_" for ch in b)[:48]; arms[key] = replace(base, arm=key, batch_drop=b, description=f"S7 leave-one-out: drop batch {b}")
    arms["S7_mh100k_only"] = replace(base, arm="S7_mh100k_only", batch_only="mh100k_only", description="S7: mh100k batch only"); arms["S7_no_mh100k"] = replace(base, arm="S7_no_mh100k", batch_only="no_mh100k", description="S7: all batches except mh100k")
    arms["S8_type_v1_1"] = replace(base, arm="S8_type_v1_1", type_source="v1_1", description="S8 type from v1.1 where present"); arms["S8_type_avclass"] = replace(base, arm="S8_type_avclass", type_source="avclass", description="S8 type from AVClass class token only")
    arms["S9_bands_tight"] = replace(base, arm="S9_bands_tight", band_variant="tight", description="S9 tight target-SDK bands"); arms["S9_bands_loose"] = replace(base, arm="S9_bands_loose", band_variant="loose", description="S9 loose bands")
    arms["S9_unmatched_all_in_WRONG_REFERENCE"] = replace(base, arm="S9_unmatched_all_in_WRONG_REFERENCE", band_variant="unmatched_all_in", description="S9 deliberately wrong reference arm: no matching")
    arms["S10_casefold"] = replace(base, arm="S10_casefold", casefold=True, description="S10 permission identity: lexical casefold")
    arms["S11_signer_clusters"] = replace(base, arm="S11_signer_clusters", weighting="signer_cluster", description="S11 signer clusters as the unit")
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
    mal = ds.detected(cfg.detection_floor, eligible_only=not cfg.include_2017).copy(); ben = ds.benign().copy(); notes = {}
    if cfg.exclude_test_key:
        notes["test_key_rows_removed"] = int(mal["test_key"].sum()); mal = mal[~mal["test_key"]]
    if cfg.max_report_age_days is not None:
        keep = pd.to_numeric(mal["report_age_days"], errors="coerce") <= cfg.max_report_age_days; notes["report_age_rows_removed"] = int((~keep).sum()); mal = mal[keep]
        keepb = pd.to_numeric(ben["report_age_days"], errors="coerce") <= cfg.max_report_age_days; ben = ben[keepb]
    if cfg.batch_drop is not None:
        notes["batch_dropped_rows_mal"] = int((mal["batch"] == cfg.batch_drop).sum()); notes["batch_dropped_rows_ben"] = int((ben["batch"] == cfg.batch_drop).sum())
        mal = mal[mal["batch"] != cfg.batch_drop]; ben = ben[ben["batch"] != cfg.batch_drop]
    if cfg.batch_only == "mh100k_only":
        mal = mal[mal["batch"].str.contains("mh100k", na=False)]; ben = ben[ben["batch"].str.contains("mh100k", na=False)]
    if cfg.batch_only == "no_mh100k":
        mal = mal[~mal["batch"].str.contains("mh100k", na=False)]; ben = ben[~ben["batch"].str.contains("mh100k", na=False)]
    return mal, ben, notes


def _meta(ds: TrendDataset, cfg: StudyConfig, prereg_hash: str, denominator: str, n_rows: int, n_clusters: int, extra: dict | None = None) -> dict:
    m = {"dataset_sha256": ds.digest, "registry_row": REGISTRY_ROW, "denominator_entry": denominator, "n_rows": int(n_rows), "n_clusters": int(n_clusters), "weighting_mode": cfg.weighting, "preregistration_sha256": prereg_hash, "arm": cfg.arm, "arm_description": cfg.description, "detection_floor": cfg.detection_floor, "seed": cfg.seed}
    if extra:
        m.update(extra)
    return m


def _write(out: Path, name: str, table: pd.DataFrame, meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True); table.to_csv(out / f"{name}.csv", index=False); (out / f"{name}.meta.json").write_text(json.dumps(meta, indent=1, default=str))


def _set_indicator(perms: pd.Series, members: list[str], casefold: bool) -> pd.Series:
    mem = {m.casefold() if casefold else m for m in members}
    return perms.apply(lambda ps: float(any((p.casefold() if casefold else p) in mem for p in (ps or []))))


def _series_with_bands(frame: pd.DataFrame, weights: pd.Series, indicator: pd.Series, axis: pd.Series, cfg: StudyConfig) -> pd.DataFrame:
    rows = []
    for level in sorted(axis.dropna().unique(), key=lambda v: (isinstance(v, str), v)):
        g = frame[(axis == level) & weights.notna()]
        if len(g) == 0:
            continue
        ind = indicator[g.index].to_numpy(dtype=float)[:, None]; w = weights[g.index].to_numpy(dtype=float)
        _, num, den = per_batch_sums(ind, w, g["batch"].to_numpy()); b = ratio_bands(num, den, n_resamples=cfg.n_resamples, seed=cfg.seed)
        rows.append({"axis": level, "weighted": float(b["point"][0]), "raw": float(ind.mean()), "lo95": float(b["lo"][0]), "hi95": float(b["hi"][0]), "n_rows": int(len(g)), "n_clusters": int(g["perm_profile_hash"].nunique()), "n_batches": b["n_batches"]})
    return pd.DataFrame(rows)


def run_study(ds: TrendDataset, cfg: StudyConfig, out: Path, prereg_hash: str, annotations: dict | None, dangerous: list[str], band_config_path: str | Path | None = None, tables: tuple[str, ...] = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "scorecard"), make_figures: bool = True) -> dict:
    t0 = time.time(); out.mkdir(parents=True, exist_ok=True); figs = out / "figures"
    band_cfg = load_band_config(band_config_path, "primary" if cfg.band_variant == "unmatched_all_in" else cfg.band_variant)
    mal, ben, notes = _filter(ds, cfg)
    w_m = weights_for_mode(mal, cfg.weighting, cfg.seed); w_b = weights_for_mode(ben, cfg.weighting, cfg.seed)
    axis_m = _axis(mal, cfg, band_cfg); axis_b = _axis(ben, cfg, band_cfg)
    mal = mal.assign(_axis=axis_m); ben = ben.assign(_axis=axis_b)
    typecol = _type_column(mal, cfg.type_source); mal = mal.assign(_type=typecol)
    six = typecol[w_m.notna()].dropna().value_counts().head(6).index.tolist()
    den_rows = f"DETECTED_V2 (floor {cfg.detection_floor}; eligible={'all years' if cfg.include_2017 else 'trend_year_eligible'})"
    manifest = {"config": asdict(cfg), "filters": notes, "rows_malware": int(len(mal)), "rows_malware_with_dict": int(w_m.notna().sum()), "rows_benign": int(len(ben)), "rows_benign_with_dict": int(w_b.notna().sum()), "six_types": six, "tables": {}}
    perm_universe = [p for p in dangerous if (_set_indicator(mal["perms"], [p], cfg.casefold)[w_m.notna()].mean() >= 0.01 or _set_indicator(ben["perms"], [p], cfg.casefold)[w_b.notna()].mean() >= 0.01)]
    comp = list(COMPONENT_SET); t2t3 = perm_universe + [p for p in comp if p not in perm_universe]
    levels_trend = YEARS_TREND if cfg.time_axis == "year" else sorted(axis_m.dropna().unique(), key=str)
    # T1
    if "T1" in tables:
        full = ds.detected(cfg.detection_floor, eligible_only=False); rows = []
        for y in YEARS_ALL:
            g = full[full["year"] == y]; d = g[g["has_dict"]]
            rows.append({"year": y, "rows": len(g), "rows_with_dict": len(d), "clusters": int(d["perm_profile_hash"].nunique()), "with_family": int(g["label_has_family_v2"].fillna(False).astype(bool).sum()), "type_only": int((g["label_has_type_v2"].fillna(False).astype(bool) & ~g["label_has_family_v2"].fillna(False).astype(bool)).sum()),
                         "test_key_rows": int(g["test_key"].sum()), "resigned_2017_rows": int(g["corpus_resigned_2017"].fillna(False).astype(bool).sum()), "trend_eligible_rows": int(g["trend_year_eligible"].fillna(False).astype(bool).sum()), "trend_eligible_year": bool(g["trend_year_eligible"].fillna(False).astype(bool).all()) if len(g) else False, "report_age_median_days": float(pd.to_numeric(g["report_age_days"], errors="coerce").median()) if len(g) else np.nan})
        t1 = pd.DataFrame(rows); _write(out, "T1_detected_per_year", t1, _meta(ds, cfg, prereg_hash, f"DETECTED_V2 (floor {cfg.detection_floor}; all years shown; eligibility marked)", len(full), full[full["has_dict"]]["perm_profile_hash"].nunique()))
        if make_figures: manifest["tables"]["T1"] = F.fig_rows_clusters(t1, figs)
    # T2 / T3 / T8
    def prev_by_axis(frame, weights, perms, levels):
        f2 = frame.assign(year=frame["_axis"]); return prevalence_table(f2, perms, weights, levels, casefold=cfg.casefold, n_resamples=cfg.n_resamples, seed=cfg.seed)
    if "T2" in tables:
        t2 = prev_by_axis(mal, w_m, perm_universe, levels_trend); _write(out, "T2_dangerous_prevalence", t2, _meta(ds, cfg, prereg_hash, den_rows + " ∩ PROVIDER_DICT_PRESENT", w_m.notna().sum(), mal[w_m.notna()]["perm_profile_hash"].nunique(), {"axis": cfg.time_axis, "permissions": perm_universe}))
        if make_figures and len(t2): manifest["tables"]["T2"] = F.fig_prevalence_lines(t2[t2["permission"].isin(t2.groupby("permission")["raw_prevalence"].mean().nlargest(8).index)], figs, "T2_dangerous_prevalence", annotations if cfg.time_axis == "year" else None, title="T2 dangerous-tier prevalence (cluster-weighted, top 8 shown)")
    if "T3" in tables:
        t3 = prev_by_axis(mal, w_m, comp, levels_trend); _write(out, "T3_component_prevalence", t3, _meta(ds, cfg, prereg_hash, den_rows + " ∩ PROVIDER_DICT_PRESENT", w_m.notna().sum(), mal[w_m.notna()]["perm_profile_hash"].nunique(), {"axis": cfg.time_axis, "permissions": comp}))
        if make_figures and len(t3): manifest["tables"]["T3"] = F.fig_prevalence_lines(t3, figs, "T3_component_prevalence", annotations if cfg.time_axis == "year" else None, title="T3 component-bound capability prevalence")
    if "T8" in tables and cfg.time_axis == "year":
        band_axis = assign_band(mal["sdk_catalog_target"], band_cfg); levels = [b["name"] for b in band_cfg["bands"]] + [band_cfg["null_band"]]
        t8 = prev_by_axis(mal.assign(_axis=band_axis), w_m, t2t3, levels); t8 = t8.rename(columns={"year": "target_sdk_band"})
        _write(out, "T8_sdk_era_prevalence", t8, _meta(ds, cfg, prereg_hash, den_rows + " ∩ PROVIDER_DICT_PRESENT", w_m.notna().sum(), mal[w_m.notna()]["perm_profile_hash"].nunique(), {"axis": "target_sdk_band"}))
        if make_figures and len(t8): manifest["tables"]["T8"] = F.fig_heatmap(t8, figs, "T8_sdk_era_prevalence", "permission", "target_sdk_band", "weighted_prevalence", "T8 prevalence by target-SDK band (cluster-weighted)")
    # T4
    if "T4" in tables:
        rows = []; st = strata(mal, ben, YEARS_MATCH, band_cfg)
        for p in t2t3 + ["SET:SMS_OR_CALL_LOG_ANY", "SET:CAPABILITY3_ANY", "SET:LEGACY_ANY"]:
            members = {"SET:SMS_OR_CALL_LOG_ANY": SMS_SET, "SET:CAPABILITY3_ANY": CAP3, "SET:LEGACY_ANY": LEGACY_SET}.get(p, [p])
            im = _set_indicator(mal["perms"], members, cfg.casefold); ib = _set_indicator(ben["perms"], members, cfg.casefold)
            for y in YEARS_MATCH:
                r = matched_prevalence(mal, ben, im, ib, w_m, w_b, y, band_cfg, unmatched_all_in=cfg.band_variant == "unmatched_all_in")
                # malware band: batch resampling within the matched bands (capacities fixed at the point estimate); benign is one batch here
                caps = {}
                if cfg.band_variant != "unmatched_all_in":
                    stt = st[(st["year"] == y) & (~st["dropped"])]; caps = dict(zip(stt["band"], stt["matched_capacity"].astype(float)))
                lo, hi, nb = matched_malware_band_bootstrap(mal, im, w_m, y, band_cfg, caps, cfg.n_resamples, cfg.seed) if caps else (np.nan, np.nan, int(mal[(mal["year"] == y)]["batch"].nunique()))
                vals = None; labels = range(nb)
                rows.append({"permission": p, "year": y, "malware": r["malware"], "benign": r["benign"], "difference": (r["malware"] - r["benign"]) if not (pd.isna(r["malware"]) or pd.isna(r["benign"])) else np.nan, "malware_lo95": lo, "malware_hi95": hi, "matched_capacity": r["capacity"], "bands_used": "|".join(map(str, r["bands_used"])), "bands_dropped": "|".join(map(str, r["bands_dropped"])), "malware_batches": int(len(labels)), "benign_batches": int(ben[(ben["year"] == y) & w_b.notna()]["batch"].nunique())})
        t4 = pd.DataFrame(rows); _write(out, "T4_matched_benign_vs_malware", t4, _meta(ds, cfg, prereg_hash, den_rows + " ∩ 2018-2021 vs BENIGN_SOURCE_V2; matched year × target-SDK band (" + cfg.band_variant + ")", int((mal["year"].isin(YEARS_MATCH) & w_m.notna()).sum()) + int(w_b.notna().sum()), 0, {"band_variant": cfg.band_variant, "malware_band_resamples": cfg.n_resamples}))
        _write(out, "T4_strata", st, _meta(ds, cfg, prereg_hash, "matching strata", len(st), 0))
        if make_figures and len(t4): manifest["tables"]["T4"] = F.fig_matched(t4[t4["permission"].isin(["SET:SMS_OR_CALL_LOG_ANY", "SET:CAPABILITY3_ANY", AP + "SYSTEM_ALERT_WINDOW", AP + "READ_PHONE_STATE", AP + "READ_SMS", AP + "ACCESS_FINE_LOCATION"])], figs)
    # T5
    if "T5" in tables:
        rows = []
        for t in six:
            sub = mal[mal["_type"] == t]; tab = prev_by_axis(sub, w_m[sub.index], t2t3, levels_trend); tab["type"] = t; rows.append(tab)
        t5 = pd.concat(rows) if rows else pd.DataFrame(); _write(out, "T5_type_prevalence", t5, _meta(ds, cfg, prereg_hash, den_rows + " ∩ six types", w_m.notna().sum(), 0, {"six_types": six, "type_source": cfg.type_source}))
        if make_figures and len(t5): manifest["tables"]["T5"] = F.fig_heatmap(t5[t5["year"] == (2025 if cfg.time_axis == "year" else t5["year"].iloc[-1])], figs, "T5_type_prevalence_last", "permission", "type", "weighted_prevalence", "T5 per-type prevalence (last axis level)")
    # T6
    if "T6" in tables:
        rows = []
        for level in sorted(mal["_axis"].dropna().unique(), key=str):
            g = mal[(mal["_axis"] == level) & w_m.notna() & mal["_type"].isin(six)]
            if len(g) == 0: continue
            _, vec, nrows = type_profile_vectors(g, w_m[g.index], "_type", six); tab = pairwise_jsd(vec, nrows); tab.insert(0, "year", level); rows.append(tab)
        t6 = pd.concat(rows) if rows else pd.DataFrame(); _write(out, "T6_type_jsd", t6, _meta(ds, cfg, prereg_hash, den_rows + " ∩ six types ∩ PROVIDER_DICT_PRESENT", int((w_m.notna() & mal["_type"].isin(six)).sum()), 0, {"six_types": six}))
        if make_figures and len(t6): manifest["tables"]["T6"] = F.fig_jsd(t6, figs)
    # T7
    if "T7" in tables:
        rows = []
        for y in YEARS_ALL:
            g = mal[mal["year"] == y]
            if len(g) == 0: continue
            sig = g["signer_thumbprint_raw"].dropna(); prof = g[g["has_dict"]]["perm_profile_hash"].dropna()
            rows.append({"year": y, "rows": len(g), "rows_with_signer": len(sig), "signers": int(sig.nunique()), "top10_signer_share": top_k_share(sig), "signer_herfindahl": herfindahl(sig), "rows_with_profile": len(prof), "profiles": int(prof.nunique()), "top10_profile_share": top_k_share(prof), "profile_herfindahl": herfindahl(prof), "test_key_share": float(g["test_key"].mean())})
        t7 = pd.DataFrame(rows); _write(out, "T7_concentration", t7, _meta(ds, cfg, prereg_hash, den_rows, len(mal), mal[mal["has_dict"]]["perm_profile_hash"].nunique()))
        if make_figures and len(t7): manifest["tables"]["T7"] = F.fig_concentration(t7, figs)
    # scorecard (pre-registered rules; always on the year axis)
    if "scorecard" in tables:
        yaxis = mal["year"]; series = {}
        for name, members in [("SMS_OR_CALL_LOG_ANY", SMS_SET), ("CAPABILITY3_ANY", CAP3), ("LEGACY_ANY_eligible", LEGACY_SET)]:
            series[name] = _series_with_bands(mal, w_m, _set_indicator(mal["perms"], members, cfg.casefold), yaxis, cfg).set_index("axis")
        full = ds.detected(cfg.detection_floor, eligible_only=False); wf = weights_for_mode(full, cfg.weighting, cfg.seed)
        series["LEGACY_ANY_all_detected"] = _series_with_bands(full, wf, _set_indicator(full["perms"], LEGACY_SET, cfg.casefold), full["year"], cfg).set_index("axis")
        for n, s in series.items(): s.reset_index().to_csv(out / f"series_{n}.csv", index=False)
        t4p = pd.read_csv(out / "T4_matched_benign_vs_malware.csv") if (out / "T4_matched_benign_vs_malware.csv").exists() else None
        t2p = pd.read_csv(out / "T2_dangerous_prevalence.csv") if (out / "T2_dangerous_prevalence.csv").exists() else None
        t6p = pd.read_csv(out / "T6_type_jsd.csv") if (out / "T6_type_jsd.csv").exists() else None
        sc = scorecard(series, t4p, mal, w_m, t6p, cfg)
        _write(out, "scorecard", sc, _meta(ds, cfg, prereg_hash, "pre-registered rules", len(mal), 0))
        if make_figures: manifest["tables"]["scorecard"] = F.fig_scorecard(sc, figs)
    manifest["wall_clock_seconds"] = round(time.time() - t0, 1); (out / "run_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    return manifest


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
        rows.append({"prediction": "P3", "verdict": "SUPPORTED" if diffs[j] > 10 else "NOT SUPPORTED", "decided_by": "2024 top-10 raw vs weighted", "evidence": f"largest |raw-weighted| = {diffs[j]:.1f} pp ({top[j]}); raw={raw[j]:.3f}, weighted={wt[j]:.3f}, n={len(g)}"})
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
