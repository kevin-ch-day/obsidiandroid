"""Synthetic tests for temporal observation contract and offline trends."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.reporting.temporal_observation_contract import (
    SOURCE_FIRST_ANALYZED_SUBMISSION,
    SOURCE_FIRST_DISCOVERED,
    SOURCE_FIRST_SEEN_IN_THE_WILD,
    SOURCE_MISSING,
    attach_temporal_observations,
    extract_observation_year,
    parse_observation_timestamp,
    select_temporal_observation,
)
from obsidiandroid.reporting.temporal_permission_trends import (
    build_missing_date_rates,
    build_yearly_capability_prevalence,
    build_yearly_counts,
    compose_temporal_permission_trends,
)


def test_temporal_precedence_and_source_preservation() -> None:
    row = {
        "vt_first_seen_itw_date": "2020-06-11",
        "vt_first_submission_date": "2019-08-31 10:16:14",
        "effective_first_seen_at_utc": "2020-06-11 00:00:00",
    }
    selected = select_temporal_observation(row)
    assert selected["selected_date_source"] == SOURCE_FIRST_SEEN_IN_THE_WILD
    assert selected["source_confidence"] == "high"
    assert selected["original__vt_first_submission_date"] == row["vt_first_submission_date"]
    assert selected["apk_creation_dating"] is False
    assert selected["temporal_eligibility_status"] == "eligible"
    assert int(selected["observation_year"]) == 2020


def test_discovered_over_submission_and_missing_handling() -> None:
    row = {
        "first_discovered": "2018-01-02",
        "vt_first_submission_date": "2019-01-02",
    }
    selected = select_temporal_observation(row)
    assert selected["selected_date_source"] == SOURCE_FIRST_DISCOVERED
    assert selected["missing_first_seen_in_the_wild"] is True

    empty = select_temporal_observation({})
    assert empty["selected_date_source"] == SOURCE_MISSING
    assert empty["temporal_eligibility_status"] == "ineligible_missing_date"
    assert empty["missing_selected_temporal_date"] is True

    submission_only = select_temporal_observation({"vt_first_submission_date": "2017-03-04"})
    assert submission_only["selected_date_source"] == SOURCE_FIRST_ANALYZED_SUBMISSION


def test_pd_na_and_unparseable_itw_count_as_missing() -> None:
    selected = select_temporal_observation(
        {
            "vt_first_seen_itw_date": pd.NA,
            "vt_first_submission_date": "2019-01-02",
        }
    )
    assert selected["missing_first_seen_in_the_wild"] is True
    assert selected["selected_date_source"] == SOURCE_FIRST_ANALYZED_SUBMISSION

    bad_itw = select_temporal_observation(
        {
            "vt_first_seen_itw_date": "not-a-date",
            "vt_first_submission_date": "2018-03-04",
        }
    )
    assert bad_itw["missing_first_seen_in_the_wild"] is True
    assert bad_itw["selected_date_source"] == SOURCE_FIRST_ANALYZED_SUBMISSION


def test_missing_date_rates_use_clear_eligibility_metrics() -> None:
    labels = pd.DataFrame(
        [
            {
                "missing_first_seen_in_the_wild": True,
                "missing_first_discovered": True,
                "missing_first_analyzed_or_submission": False,
                "missing_collection_timestamp": True,
                "missing_selected_temporal_date": False,
                "temporal_eligibility_status": "eligible",
            },
            {
                "missing_first_seen_in_the_wild": True,
                "missing_first_discovered": True,
                "missing_first_analyzed_or_submission": True,
                "missing_collection_timestamp": True,
                "missing_selected_temporal_date": True,
                "temporal_eligibility_status": "ineligible_missing_date",
            },
        ]
    )
    rates = build_missing_date_rates(labels)
    metrics = set(rates["metric"])
    assert "ineligible_missing_selected_date" in metrics
    assert "eligible_observation_date_samples" in metrics
    assert "temporal_eligible_samples" not in metrics
    ineligible = rates[rates.metric == "ineligible_missing_selected_date"].iloc[0]
    eligible = rates[rates.metric == "eligible_observation_date_samples"].iloc[0]
    assert int(ineligible["count"]) == 1
    assert int(eligible["count"]) == 1


def test_year_extraction_and_attach() -> None:
    assert extract_observation_year("2021-05-01") == 2021
    assert extract_observation_year("") is None
    assert pd.isna(parse_observation_timestamp(None))
    labels = pd.DataFrame(
        [
            {"sample_id": 1, "type_slug": "rat", "family_canonical": "A", "vt_first_submission_date": "2019-01-01"},
            {"sample_id": 2, "type_slug": "rat", "family_canonical": "B", "vt_first_seen_itw_date": "2020-02-02", "vt_first_submission_date": "2018-01-01"},
        ]
    )
    out = attach_temporal_observations(labels)
    assert list(out["selected_date_source"]) == [
        SOURCE_FIRST_ANALYZED_SUBMISSION,
        SOURCE_FIRST_SEEN_IN_THE_WILD,
    ]
    assert list(out["observation_year"]) == [2019, 2020]


def test_support_suppression_and_yearly_prevalence() -> None:
    labels = pd.DataFrame(
        [
            {
                "sample_id": i,
                "type_slug": "rat",
                "family_canonical": "F",
                "observation_year": 2019 if i < 5 else 2020,
                "temporal_eligibility_status": "eligible",
            }
            for i in range(40)
        ]
    )
    yearly = build_yearly_counts(labels, group_col="type_slug", min_support=30)
    y2019 = yearly[yearly.observation_year == 2019].iloc[0]
    y2020 = yearly[yearly.observation_year == 2020].iloc[0]
    assert y2019.support_suppressed
    assert not y2020.support_suppressed

    matrix = labels.copy()
    matrix["sms_mms"] = [1 if i % 2 == 0 else 0 for i in range(40)]
    matrix["is_missing_package"] = False
    matrix["package_key"] = [f"com.p{i}" for i in range(40)]
    for cat in (
        "phone_call_log",
        "contacts_accounts",
        "notifications",
        "accessibility",
        "overlay_screen",
        "location",
        "camera",
        "microphone_audio",
        "bluetooth_nearby",
        "wifi_network",
        "storage_media",
        "package_install_remove",
        "boot_persistence",
        "battery_background",
        "device_admin_security",
        "calendar",
        "sensors",
        "oem_platform",
        "app_defined_unknown",
    ):
        matrix[cat] = 0
    prev = build_yearly_capability_prevalence(matrix, min_support=30, weighting="sample_weighted")
    assert prev[prev.observation_year == 2019]["support_suppressed"].all()
    assert not prev[prev.observation_year == 2020]["support_suppressed"].all()


def test_temporal_composer_deterministic_no_mutation(tmp_path: Path) -> None:
    run_id = "20260721T231415Z__e0c43b"
    run_root = tmp_path / "run"
    diag = run_root / "diagnostics"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    diag.mkdir(parents=True)
    tables.mkdir(parents=True)
    (run_root / ".COMPLETE").write_text("ok\n", encoding="utf-8")
    labels = pd.DataFrame(
        [
            {
                "sample_id": i,
                "family_canonical": f"F{i % 4}",
                "type_slug": "rat" if i % 2 == 0 else "banker",
                "package_name": f"com.p{i % 6}",
                "family_id": i % 4,
                "sha256": f"h{i}",
                "vt_first_submission_date": f"201{9 if i < 20 else 8}-0{(i % 9) + 1}-15",
                "vt_first_seen_itw_date": "" if i % 5 else f"2020-0{(i % 9) + 1}-01",
            }
            for i in range(40)
        ]
    )
    labels.to_csv(diag / f"aligned_labels_{run_id}.csv", index=False)
    labels.to_csv(diag / f"analysis_snapshot_{run_id}.csv", index=False)
    perms = []
    for i in range(40):
        perms.append({"sample_id": i, "permission_name": "android.permission.internet", "permission_present": 1})
        if i % 2 == 0:
            perms.append({"sample_id": i, "permission_name": "android.permission.send_sms", "permission_present": 1})
    pd.DataFrame(perms).to_csv(diag / f"ml_sample_permission_feature_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {
                "permission_string": "android.permission.internet",
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "normal",
                "feature_column": "x",
                "feature_group": "g",
                "global_support": 10,
                "max_family_support": 2,
                "max_type_support": 2,
                "pruned_as_leakage": False,
                "retained_after_pruning": True,
            }
        ]
    ).to_csv(diag / "permission_feature_audit.csv", index=False)
    pd.DataFrame([{"samples_with_permission_rows": 9457}]).to_csv(
        tables / f"permission_coverage_report_{run_id}.csv", index=False
    )
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": "android_malware_all_current",
                "git_commit": "deadbeef",
                "dataset_hash": "abc",
                "cohort_prepared_row_count": 9716,
                "run_status": "complete",
            }
        ),
        encoding="utf-8",
    )
    before = (diag / f"aligned_labels_{run_id}.csv").read_bytes()
    out1 = tmp_path / "t1"
    out2 = tmp_path / "t2"
    m1 = compose_temporal_permission_trends(run_root=run_root, run_id=run_id, output_dir=out1, min_support=5)
    m2 = compose_temporal_permission_trends(run_root=run_root, run_id=run_id, output_dir=out2, min_support=5)
    assert m1["eligible_sample_count"] == m2["eligible_sample_count"]
    assert (out1 / "yearly_sample_counts_by_type.csv").read_bytes() == (out2 / "yearly_sample_counts_by_type.csv").read_bytes()
    assert (out1 / "sample_temporal_observations.csv").read_bytes() == (out2 / "sample_temporal_observations.csv").read_bytes()
    pb_fig = "figures/yearly_capability_prevalence_package_balanced.png"
    assert (out1 / pb_fig).is_file()
    assert (out1 / pb_fig).read_bytes() == (out2 / pb_fig).read_bytes()
    assert (diag / f"aligned_labels_{run_id}.csv").read_bytes() == before
    rates = build_missing_date_rates(pd.read_csv(out1 / "sample_temporal_observations.csv"))
    assert not rates.empty
    assert m1["causal_android_update_claims"] is False
    assert m1["apk_creation_dating"] is False
