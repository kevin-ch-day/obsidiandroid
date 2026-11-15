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
