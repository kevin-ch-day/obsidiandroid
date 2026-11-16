"""Synthetic-fixture tests for obsidiandroid.research.trends (no real data; no database; no pyarrow needed)."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from obsidiandroid.research.trends import bootstrap as B, metrics as M, weighting as Wt
from obsidiandroid.research.trends.dataset import REQUIRED_COLUMNS, DigestMismatch, TrendDataset, load_dataset
from obsidiandroid.research.trends.matching import assign_band, matched_prevalence, strata


def synthetic_frame(n: int = 60, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed); years = rng.choice([2018, 2019, 2020], size=n)
    perms_pool = ["android.permission.INTERNET", "android.permission.READ_SMS", "android.permission.SYSTEM_ALERT_WINDOW", "android.permission.CAMERA"]
    rows = []
    for i in range(n):
        plist = sorted(rng.choice(perms_pool, size=rng.integers(1, 4), replace=False).tolist()); has = i % 7 != 0
        rows.append({c: None for c in REQUIRED_COLUMNS} | {
            "id_sample_id": i + 1, "id_sha256": hashlib.sha256(str(i).encode()).hexdigest(), "time_first_submission_year": int(years[i]), "trend_year_eligible": True, "corpus_resigned_2017": False,
            "det_malicious": int(rng.integers(0, 40)), "det_engines_present": 70, "source_class_state": "BENIGN_0" if i % 3 == 0 else "UNKNOWN", "label_v2_provenance": "BENIGN_SOURCE_LABELED" if i % 3 == 0 else "AUTHORITY",
            "label_v2_type_v2": ["banker", "rat", "adware"][i % 3], "label_v2_family_v2": "fam", "label_has_family_v2": True, "label_has_type_v2": True, "label_v1_1_type_v1_1": None, "label_v2_avclass_class_tokens": "CLASS:banker|3",
            "pay_permission_names_raw": json.dumps(plist) if has else None, "perm_profile_hash": hashlib.sha256("\n".join(plist).encode()).hexdigest() if has else None,
            "signer_thumbprint_raw": f"tp{i % 5}", "signer_is_aosp_test_key": False, "signer_is_marco_test2014": False, "report_age_days": 100, "batch_source_label": f"batch{i % 4}",
            "sdk_catalog_target": [22, 25, 28, None][i % 4], "sdk_catalog_min": 16, "det_report_state": "PRESENT", "group_detected_v2": None, "group_benign_source_v2": None, "attack_status": "ASSESSED", "attack_assessments": None})
    return pd.DataFrame(rows)


def test_digest_refusal_before_reading(tmp_path):
    f = tmp_path / "x.parquet"; f.write_bytes(b"not a parquet file")
    called = []
    with pytest.raises(DigestMismatch):
        load_dataset(f, "0" * 64, reader=lambda p, c: called.append(p))
    assert called == []  # the reader never ran
    with pytest.raises(ValueError):
        load_dataset(f, "short", reader=lambda p, c: called.append(p))


def test_load_with_matching_digest_uses_reader(tmp_path):
    f = tmp_path / "x.parquet"; f.write_bytes(b"payload"); digest = hashlib.sha256(b"payload").hexdigest()
    ds = load_dataset(f, digest, reader=lambda p, c: synthetic_frame())
    assert ds.digest == digest and len(ds.frame) == 60 and "perms" in ds.frame


def test_masks_follow_denominator_predicates():
    ds = TrendDataset.from_frame(synthetic_frame())
    det = ds.detected_mask(); ben = ds.benign_source_mask()
    assert not (det & ben).any()                      # source-benign never detected
    assert (det == ((pd.to_numeric(ds.frame.det_malicious) >= 4) & (ds.frame.source_class_state != "BENIGN_0"))).all()
    assert ds.detected_mask(floor=2).sum() >= det.sum() >= ds.detected_mask(floor=6).sum()


def test_weight_sums_equal_cluster_counts_per_year():
    ds = TrendDataset.from_frame(synthetic_frame()); f = ds.frame
    w = Wt.cluster_weights(f); sums = w.groupby(f["year"]).sum(); counts = Wt.cluster_count(f)
    for y in counts.index:
        assert abs(sums[y] - counts[y]) < 1e-9
    opc = Wt.one_per_cluster_weights(f, seed=3); assert abs(opc.sum() - counts.sum()) < 1e-9 and set(opc.dropna().unique()) <= {0.0, 1.0}
    assert Wt.one_per_cluster_weights(f, seed=3).equals(Wt.one_per_cluster_weights(f, seed=3))


def test_matching_drops_unmatched_strata():
    ds = TrendDataset.from_frame(synthetic_frame()); f = ds.frame
    cfg = {"variant": "t", "null_band": "(null)", "bands": [{"name": "<=22", "min": 1, "max": 22}, {"name": "23-28", "min": 23, "max": 28}, {"name": "29+", "min": 29, "max": None}]}
    mal = f[ds.detected_mask()]; ben = f[ds.benign_source_mask()]
    st = strata(mal, ben, [2018, 2019, 2020], cfg); assert set(st.columns) >= {"year", "band", "matched_capacity", "dropped"}
    assert (st.loc[st.band == "29+", "dropped"]).all()      # nobody has target SDK >= 29 in the fixture
    w_m = Wt.cluster_weights(mal); w_b = Wt.cluster_weights(ben); ind_m = mal["perms"].apply(lambda p: float("android.permission.INTERNET" in (p or []))); ind_b = ben["perms"].apply(lambda p: float("android.permission.INTERNET" in (p or [])))
    r = matched_prevalence(mal, ben, ind_m, ind_b, w_m, w_b, 2018, cfg); assert "29+" in r["bands_dropped"] and 0 <= r["malware"] <= 1
    assert assign_band(pd.Series([None, 22, 23, 40]), cfg).tolist() == ["(null)", "<=22", "23-28", "29+"]


def test_bootstrap_is_deterministic_and_bounded():
    rng = np.random.default_rng(0); ind = rng.integers(0, 2, size=(200, 3)).astype(float); w = np.ones(200); batches = rng.integers(0, 6, size=200)
    labels, num, den = B.per_batch_sums(ind, w, batches); a = B.ratio_bands(num, den, n_resamples=300, seed=20261115); b = B.ratio_bands(num, den, n_resamples=300, seed=20261115)
    assert np.allclose(a["lo"], b["lo"]) and np.allclose(a["hi"], b["hi"]) and (a["lo"] <= a["point"] + 1e-12).all() and (a["hi"] >= a["point"] - 1e-12).all()
    one = B.ratio_bands(num[:1], den[:1]); assert np.isnan(one["lo"]).all() and one["n_batches"] == 1


def test_jsd_symmetric_and_zero_on_identical():
    p = np.array([0.5, 0.3, 0.2]); q = np.array([0.2, 0.3, 0.5])
    assert M.js_distance(p, p) == pytest.approx(0.0, abs=1e-12) and M.js_distance(p, q) == pytest.approx(M.js_distance(q, p)) and 0 < M.js_distance(p, q) <= 1
    assert M.herfindahl(pd.Series(["a", "a", "b", "c"])) == pytest.approx(0.375) and M.top_k_share(pd.Series(["a", "a", "b", "c"]), k=1) == pytest.approx(0.5)


def test_figure_csv_equals_table(tmp_path):
    from obsidiandroid.research.trends import figures as F
    table = pd.DataFrame({"year": [2018, 2019, 2020], "rows": [10, 20, 30], "clusters": [5, 8, 9], "resigned_2017_rows": [0, 0, 0]})
    out = F.fig_rows_clusters(table, tmp_path); back = pd.read_csv(tmp_path / out["csv"])
    pd.testing.assert_frame_equal(back, table); assert (tmp_path / out["png"]).exists() and (tmp_path / out["svg"]).exists()
    with pytest.raises(ValueError):
        F.load_annotations(_write_json(tmp_path / "bad.json", {"causal_claim_permitted": True, "events": []}))


def _write_json(path, obj):
    path.write_text(json.dumps(obj)); return path


def test_study_runs_on_synthetic(tmp_path):
    from obsidiandroid.research.trends.study import StudyConfig, run_study
    ds = TrendDataset.from_frame(synthetic_frame(n=240, seed=5)); cfg = StudyConfig(n_resamples=50)
    res = run_study(ds, cfg, tmp_path / "out", prereg_hash="0" * 64, annotations=None, dangerous=["android.permission.READ_SMS", "android.permission.CAMERA"], make_figures=False, tables=("T1", "T2", "T3", "T4", "T6", "T7", "scorecard"))
    assert (tmp_path / "out" / "scorecard.csv").exists() and (tmp_path / "out" / "T4_matched_benign_vs_malware.csv").exists()
    meta = json.loads((tmp_path / "out" / "T2_dangerous_prevalence.meta.json").read_text()); assert meta["weighting_mode"] == "cluster" and meta["preregistration_sha256"] == "0" * 64
    assert res["rows_malware"] > 0


def test_stability_effects_and_format():
    from obsidiandroid.research.trends import stability as S
    t = pd.DataFrame({"permission": ["p"] * 2, "year": [2018, 2025], "weighted_prevalence": [0.2, 0.5], "lo95": [0.1, 0.4], "hi95": [0.3, 0.6]})
    eff, excl = S._effect_T2T3(t, "p"); assert eff == pytest.approx(0.3) and excl is True and S._fmt((eff, excl)) == "+0.300*"
    assert S._effect_T2T3(t, "missing") is None and S._fmt(None) == "n/a"
    t4 = pd.DataFrame({"permission": ["q", "q"], "year": [2018, 2019], "malware": [0.5, 0.6], "benign": [0.2, 0.2], "difference": [0.3, 0.4], "malware_lo95": [0.4, 0.5], "malware_hi95": [0.6, 0.7]})
    eff, excl = S._effect_T4(t4, "q"); assert eff == pytest.approx(0.35) and excl is True
    t6 = pd.DataFrame({"year": [2019, 2024], "type_a": ["banker", "banker"], "type_b": ["rat", "rat"], "js_distance": [0.4, 0.6], "thin": [False, False]})
    assert S._effect_T6(t6, "banker", "rat") == (pytest.approx(0.2), True)


def test_prevalence_figure_accepts_band_axis(tmp_path):
    from obsidiandroid.research.trends import figures as F
    t = pd.DataFrame({"year": ["<=22", "23-25", "(null)"], "permission": ["p"] * 3, "weighted_prevalence": [0.1, 0.2, 0.3], "lo95": [np.nan] * 3, "hi95": [np.nan] * 3})
    out = F.fig_prevalence_lines(t, tmp_path, "band_axis", annotations={"events": [{"year": 2019, "label": "x"}], "causal_claim_permitted": False})
    assert (tmp_path / out["png"]).exists()


# ---------------------------------------------------------------- v1.1 corrections (one regression test per corrected defect)

def _frame_with_duplicated_profiles(n_batches: int = 4, seed: int = 11) -> pd.DataFrame:
    """Profiles repeated unevenly across batches so that fixed-design and recomputed-unit bootstraps differ."""
    rng = np.random.default_rng(seed); rows = []; profiles = [["android.permission.READ_SMS"], ["android.permission.CAMERA"], ["android.permission.READ_SMS", "android.permission.CAMERA"], ["android.permission.INTERNET"]]
    for i in range(400):
        p = profiles[0] if (i % n_batches == 0 and i % 3 != 0) else profiles[rng.integers(0, 4)]
        rows.append({c: None for c in REQUIRED_COLUMNS} | {"id_sample_id": i, "id_sha256": hashlib.sha256(str(i).encode()).hexdigest(), "time_first_submission_year": 2020 if i < 380 else 2010, "trend_year_eligible": True, "corpus_resigned_2017": False,
            "det_malicious": 10, "det_engines_present": 70, "source_class_state": "UNKNOWN", "label_v2_provenance": "AUTHORITY", "label_v2_type_v2": "banker", "label_v2_family_v2": "f", "label_has_family_v2": True, "label_has_type_v2": True,
            "pay_permission_names_raw": json.dumps(p), "perm_profile_hash": hashlib.sha256("\n".join(p).encode()).hexdigest(), "signer_thumbprint_raw": f"tp{i % 3}", "signer_is_aosp_test_key": False, "signer_is_marco_test2014": False,
            "report_age_days": 10, "batch_source_label": f"b{i % n_batches}", "sdk_catalog_target": 25, "sdk_catalog_min": 16, "det_report_state": "PRESENT", "attack_status": "ASSESSED"})
    return pd.DataFrame(rows)


def test_recomputed_unit_bootstrap_gives_unit_mass_per_represented_cluster():
    """Defect 1: fixed design weights let a repeated batch carry > 1 mass per profile. The registered estimator recomputes weights."""
    ds = TrendDataset.from_frame(_frame_with_duplicated_profiles()); f = ds.frame[ds.frame.year == 2020]
    ind = M.indicator_matrix(f["perms"], ["android.permission.READ_SMS"]); w = Wt.cluster_weights(f)[f.index].to_numpy()
    rec = B.cluster_unit_bands(ind, f["perm_profile_hash"].to_numpy(), f["batch"].to_numpy(), n_resamples=200, seed=1)
    _, num, den = B.per_batch_sums(ind, w, f["batch"].to_numpy()); fix = B.ratio_bands(num, den, n_resamples=200, seed=1)
    assert rec["estimator"] == "cluster_unit_recomputed" and rec["unit_mass_check"] == 0.0 and rec["n_clusters"] == f["perm_profile_hash"].nunique()
    assert rec["point"][0] == pytest.approx(fix["point"][0])                 # identical point estimate on the original population
    # with profile clusters the recomputed statistic is the share of represented distinct profiles containing the permission -> bounded by {k/C}
    assert not (np.allclose(rec["lo"], fix["lo"]) and np.allclose(rec["hi"], fix["hi"]))   # the two estimators are not interchangeable
    disp = B.bands_for("cluster_unit_recomputed", ind, w, f["perm_profile_hash"].to_numpy(), f["batch"].to_numpy(), n_resamples=50, seed=1); assert disp["estimator"] == "cluster_unit_recomputed"
    fb = B.bands_for("cluster_unit_recomputed", ind, np.ones(len(f)), None, f["batch"].to_numpy(), n_resamples=50, seed=1); assert fb["estimator"].startswith("fixed_design")
    with pytest.raises(ValueError):
        B.bands_for("made_up", ind, w, None, f["batch"].to_numpy())


def test_years_are_data_derived_and_t1_accounts_for_every_row(tmp_path):
    """Defect 3: v1 hard-coded 2011..2026 and lost the single 2010 detected row."""
    from obsidiandroid.research.trends.study import StudyConfig, run_study
    ds = TrendDataset.from_frame(_frame_with_duplicated_profiles()); cfg = StudyConfig(n_resamples=20)
    run_study(ds, cfg, tmp_path, "0" * 64, None, ["android.permission.READ_SMS"], make_figures=False, tables=("T1", "T7"))
    t1 = pd.read_csv(tmp_path / "T1_detected_per_year.csv"); meta = json.loads((tmp_path / "T1_detected_per_year.meta.json").read_text())
    assert 2010 in set(t1.year) and int(t1.rows.sum()) == len(ds.detected(eligible_only=False)) == meta["rows_total_check"]
    assert set(pd.read_csv(tmp_path / "T7_concentration.csv").year) == {2010, 2020}
    ledger = json.loads((tmp_path / "selection_ledger.json").read_text()); assert ledger["years_in_detected_population"] == [2010, 2020] and ledger["steps"][0]["step"].startswith("detected")


def test_dangerous_selection_registered_full_reports_unobserved_permissions(tmp_path):
    """Defect 5: the >= 1 % cutoff is not registered; the primary reports the full set and the cutoff is an explicit exploratory arm."""
    from obsidiandroid.research.trends.study import StudyConfig, arm_catalog, run_study
    ds = TrendDataset.from_frame(_frame_with_duplicated_profiles()); dangerous = ["android.permission.READ_SMS", "android.permission.CAMERA", "android.permission.NEVER_SEEN"]
    run_study(ds, StudyConfig(n_resamples=20), tmp_path / "p", "0" * 64, None, dangerous, make_figures=False, tables=("T2",))
    t2 = pd.read_csv(tmp_path / "p/T2_dangerous_prevalence.csv"); meta = json.loads((tmp_path / "p/T2_dangerous_prevalence.meta.json").read_text())
    assert set(t2.permission) == set(dangerous) and meta["dangerous_selection"] == "registered_full" and meta["n_clusters"] > 0 and meta["unit"] and meta["estimand"] and meta["estimator"] == "cluster_unit_recomputed"
    never = t2[t2.permission == "android.permission.NEVER_SEEN"]; assert (~never.observed_any).all() and (never.weighted_prevalence == 0).all()
    arms = arm_catalog(["b0"]); s12 = arms["S12_dangerous_1pct_either_arm"]; assert s12.registered is False and arms["primary"].registered is True
    run_study(ds, StudyConfig(n_resamples=20, dangerous_selection="exploratory_1pct_either_arm", arm="S12"), tmp_path / "s12", "0" * 64, None, dangerous, make_figures=False, tables=("T2",))
    led = json.loads((tmp_path / "s12/selection_ledger.json").read_text())["dangerous_selection"]; assert led["registered"] is False and "android.permission.NEVER_SEEN" in led["omitted"]
    with pytest.raises(ValueError):
        StudyConfig(dangerous_selection="whatever")
    with pytest.raises(ValueError):
        StudyConfig(estimator="whatever")


def test_strata_capacity_is_dictionary_conditioned():
    """Defect 4 (T4 metadata): v1 reported all-rows capacity while computing on dictionary-conditioned rows."""
    ds = TrendDataset.from_frame(synthetic_frame()); f = ds.frame; mal = f[ds.detected_mask()]; ben = f[ds.benign_source_mask()]
    cfg = {"variant": "t", "null_band": "(null)", "bands": [{"name": "<=22", "min": 1, "max": 22}, {"name": "23-28", "min": 23, "max": 28}]}
    w_m = Wt.cluster_weights(mal); w_b = Wt.cluster_weights(ben)
    st_all = strata(mal, ben, [2018, 2019, 2020], cfg); st = strata(mal, ben, [2018, 2019, 2020], cfg, w_m=w_m, w_b=w_b)
    assert (st.matched_capacity <= st.matched_capacity_all_rows).all() and (st.matched_capacity_all_rows == st_all.matched_capacity).all()
    assert (st.matched_capacity < st.matched_capacity_all_rows).any()      # the fixture has rows without dictionaries, so the two definitions differ
    assert {"malware_clusters", "benign_clusters"} <= set(st.columns) and (st.malware_clusters <= st.malware_rows).all()


def test_heatmap_keeps_missing_cells_missing(tmp_path):
    """Defect 6: unmeasured cells must stay NaN in the figure CSV, never become zero."""
    from obsidiandroid.research.trends import figures as F
    t = pd.DataFrame({"permission": ["a", "a", "b"], "year": [2018, 2019, 2018], "weighted_prevalence": [0.2, 0.3, 0.5]})
    out = F.fig_heatmap(t, tmp_path, "hm", "permission", "year", "weighted_prevalence", "t"); back = pd.read_csv(tmp_path / out["csv"])
    cell = back[(back.permission == "b") & (back.year == 2019)]["weighted_prevalence"]; assert len(cell) == 1 and cell.isna().all()
    assert back[(back.permission == "b") & (back.year == 2018)]["weighted_prevalence"].iloc[0] == 0.5


def test_stability_labels_are_explicit(tmp_path):
    from obsidiandroid.research.trends import stability as S
    def write(arm, lo0, hi0, lo1, hi1, v="NOT SUPPORTED"):
        d = tmp_path / arm; d.mkdir()
        pd.DataFrame({"permission": ["p", "p"], "year": [2018, 2025], "weighted_prevalence": [0.2, 0.5], "lo95": [lo0, lo1], "hi95": [hi0, hi1]}).to_csv(d / "T2_dangerous_prevalence.csv", index=False)
        pd.DataFrame({"prediction": ["P1"], "verdict": [v]}).to_csv(d / "scorecard.csv", index=False)
    write("primary", 0.1, 0.4, 0.3, 0.6); write("armA", 0.1, 0.3, 0.4, 0.6, v="INCONCLUSIVE")
    df = S.build_stability(tmp_path, ["primary", "armA"])
    assert df[df.item.str.startswith("T2")].verdict.iloc[0] == "SIGN_STABLE_BAND_INCLUDES_ZERO" and df[df.item == "scorecard verdict"].verdict.iloc[0] == "VERDICT_DEGENERATE_IN_FLIPPING_ARMS"
    assert set(df.verdict) & {"REAL", "COMPOSITION-DEPENDENT"} == set() and (df.note == "sign stability across arms is not a significance test").all()


def test_matched_band_bootstrap_supports_both_estimators_and_many_permissions():
    from obsidiandroid.research.trends.matching import matched_malware_band_bootstrap_v1_1 as matched_malware_band_bootstrap
    ds = TrendDataset.from_frame(_frame_with_duplicated_profiles()); mal = ds.frame; w_m = Wt.cluster_weights(mal)
    cfg = {"variant": "t", "null_band": "(null)", "bands": [{"name": "23-28", "min": 23, "max": 28}]}
    ind = M.indicator_matrix(mal["perms"], ["android.permission.READ_SMS", "android.permission.CAMERA"])
    lo_r, hi_r, nb = matched_malware_band_bootstrap(mal, ind, w_m, 2020, cfg, {"23-28": 100.0}, 100, 1, estimator="cluster_unit_recomputed")
    lo_f, hi_f, _ = matched_malware_band_bootstrap(mal, ind, w_m, 2020, cfg, {"23-28": 100.0}, 100, 1, estimator="fixed_design")
    assert lo_r.shape == (2,) and nb == 4 and (lo_r <= hi_r).all() and (lo_f <= hi_f).all() and not (np.allclose(lo_r, lo_f) and np.allclose(hi_r, hi_f))


# ---------------------------------------------------------------- v1.2: registered-unit matched bootstrap and fixed-target P3

def test_registered_matched_bootstrap_uses_year_population_unit_and_reports_both_capacities():
    from obsidiandroid.research.trends.matching import matched_malware_bootstrap_registered
    ds = TrendDataset.from_frame(_frame_with_duplicated_profiles()); mal = ds.frame[ds.frame.year == 2020].copy()
    mal["sdk_catalog_target"] = [22 if i % 2 else 26 for i in range(len(mal))]          # two bands; profiles span both bands
    cfg = {"variant": "t", "null_band": "(null)", "bands": [{"name": "<=22", "min": 1, "max": 22}, {"name": "26-28", "min": 26, "max": 28}]}
    ind = M.indicator_matrix(mal["perms"], ["android.permission.READ_SMS", "android.permission.CAMERA"])
    res = matched_malware_bootstrap_registered(mal, ind, 2020, cfg, {"<=22": 500, "26-28": 500}, 200, 1)
    assert res["unit_mass_check"] == 0.0 and res["n_batches"] == 4 and res["n_profiles"] == mal.perm_profile_hash.nunique()
    # point = capacity-weighted band prevalence with YEAR-level profile weights (every profile unit mass across both bands)
    w = 1.0 / mal.groupby("perm_profile_hash").id_sample_id.transform("size"); band = mal.sdk_catalog_target.map(lambda v: "<=22" if v <= 22 else "26-28")
    num = den = 0.0
    for b in ("<=22", "26-28"):
        sel = (band == b).to_numpy(); cap = min(sel.sum(), 500); num += cap * (ind[sel, 0] * w[sel]).sum() / w[sel].sum(); den += cap
    assert res["point"][0] == pytest.approx(num / den)
    assert (res["lo_fixed"] <= res["hi_fixed"]).all() and (res["lo_recomputed"] <= res["hi_recomputed"]).all()
    assert not (np.allclose(res["lo_fixed"], res["lo_recomputed"]) and np.allclose(res["hi_fixed"], res["hi_recomputed"]))   # the two capacity rules differ


def test_fixed_target_gap_bootstrap_never_reselects_and_decomposes_additively():
    from obsidiandroid.research.trends.matching import fixed_target_gap_bootstrap
    ds = TrendDataset.from_frame(_frame_with_duplicated_profiles()); g = ds.frame[(ds.frame.year == 2020) & ds.frame.has_dict]
    d = fixed_target_gap_bootstrap(g, "android.permission.READ_SMS", 100, 1)
    assert d["permission"] == "android.permission.READ_SMS" and d["decomposition_sum_pp"] == pytest.approx(d["gap_pp"]) and d["gap_lo95_pp"] <= d["gap_hi95_pp"]
    for row in d["leave_one_batch_out_fixed_target"]:
        assert set(row) >= {"batch_removed", "rows_removed", "gap_pp"}                   # same permission throughout; no maximum re-selected
    assert len(d["leave_one_batch_out_fixed_target"]) == g.batch.nunique()


def test_study_writes_p3_detail_and_registered_t4_columns(tmp_path):
    from obsidiandroid.research.trends.study import StudyConfig, run_study
    ds = TrendDataset.from_frame(synthetic_frame(n=240, seed=5)); ds.frame["time_first_submission_year"] = ds.frame["year"] = ds.frame.year.where(ds.frame.year != 2020, 2024).astype("Int64")
    run_study(ds, StudyConfig(n_resamples=30), tmp_path, "0" * 64, None, ["android.permission.READ_SMS"], make_figures=False, tables=("T4", "scorecard"))
    t4 = pd.read_csv(tmp_path / "T4_matched_benign_vs_malware.csv"); assert {"malware_lo95_fixed_capacity", "malware_hi95_fixed_capacity", "matched_band_design"} <= set(t4.columns) and (t4.matched_band_design == "registered_year_profile").all()
    meta = json.loads((tmp_path / "T4_matched_benign_vs_malware.meta.json").read_text()); assert "band_columns" in meta and "unit_checks" in meta
    sc = pd.read_csv(tmp_path / "scorecard.csv"); p3 = sc[sc.prediction == "P3"].iloc[0]; assert "paired batch-resampled gap interval" in p3.evidence or "no batch band" in p3.evidence or p3.verdict == "INCONCLUSIVE"
