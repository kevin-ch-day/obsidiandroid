"""Tests for the malware-type permission-pattern report composer."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.reporting.type_permission_pattern_report import (
    COMPOSER_VERSION,
    build_complete_type_inventory,
    build_family_balanced_type_prevalence,
    build_overall_permission_prevalence,
    classify_permission_role,
    classify_type_inclusion,
    compose_type_permission_pattern_report,
    detect_source_run_status,
    sha256_file,
)


def _write_fixture_run(tmp_path: Path, *, run_id: str = "fixture_run", with_running: bool = False) -> Path:
    run_root = tmp_path / "run"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    tables.mkdir(parents=True)
    (run_root / "diagnostics").mkdir(parents=True)
    if with_running:
        (run_root / ".RUNNING").write_text(
            json.dumps({"state": "running", "current_stage": "research_validity_bundle"}),
            encoding="utf-8",
        )
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_status": "complete", "status": "complete", "completed_stage": "manifest"}),
        encoding="utf-8",
    )

    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "profile_id": "android_malware_all_current",
                "sample_count": 110,
                "samples_with_permission_rows": 110,
                "samples_zero_permission_rows": 0,
                "samples_missing_sha256": 0,
                "samples_missing_package_name": 0,
                "pct_with_permission_rows": 1.0,
                "pct_missing_permission_rows": 0.0,
                "pct_zero_permissions": 0.0,
                "pct_missing_sha256": 0.0,
                "pct_missing_package_name": 0.0,
                "pct_samples_only_common_perms": 0.0,
                "pct_samples_le2_permissions": 0.0,
                "mean_unique_permissions": 10.0,
                "std_unique_permissions": 1.0,
                "median_unique_permissions": 10.0,
            }
        ]
    ).to_csv(tables / f"permission_coverage_report_{run_id}.csv", index=False)

    # Snapshot: 100 banker + 10 dropper = 110; includes blank-family unknown rows separately
    snap_rows = []
    for i in range(90):
        snap_rows.append({"sample_id": i, "type_slug": "banker", "family_canonical": "Huge"})
    for i in range(90, 100):
        snap_rows.append({"sample_id": i, "type_slug": "banker", "family_canonical": "Small"})
    for i in range(100, 107):
        snap_rows.append({"sample_id": i, "type_slug": "dropper", "family_canonical": "Necro"})
    for i in range(107, 110):
        snap_rows.append({"sample_id": i, "type_slug": "dropper", "family_canonical": "Clast82"})
    # Extra unknown blank-family rows would break prepared=110; keep fixture at 110.
    pd.DataFrame(snap_rows).to_csv(
        run_root / "diagnostics" / f"analysis_snapshot_{run_id}.csv",
        index=False,
    )

    pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "permission": "android.permission.internet",
                "n_samples": 100,
                "permission_positive_count": 95,
                "prevalence_pct": 95.0,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "type_slug": "dropper",
                "permission": "android.permission.internet",
                "n_samples": 10,
                "permission_positive_count": 9,
                "prevalence_pct": 90.0,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "type_slug": "banker",
                "permission": "android.permission.read_sms",
                "n_samples": 100,
                "permission_positive_count": 40,
                "prevalence_pct": 40.0,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "type_slug": "dropper",
                "permission": "android.permission.read_sms",
                "n_samples": 10,
                "permission_positive_count": 1,
                "prevalence_pct": 10.0,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "type_slug": "banker",
                "permission": "android.permission.read_media_images",
                "n_samples": 100,
                "permission_positive_count": 4,
                "prevalence_pct": 4.0,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "type_slug": "dropper",
                "permission": "android.permission.read_media_images",
                "n_samples": 10,
                "permission_positive_count": 7,
                "prevalence_pct": 70.0,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
        ]
    ).to_csv(tables / f"permission_prevalence_by_type_{run_id}.csv", index=False)

    pd.DataFrame(
        [
            {
                "permission": "android.permission.read_sms",
                "type_slug": "banker",
                "type_sample_count": 100,
                "background_sample_count": 10,
                "type_prevalence_pct": 40.0,
                "non_type_prevalence_pct": 10.0,
                "odds_ratio": 6.0,
                "p_value": 0.0,
                "q_value_fdr": 0.0,
                "interpretation_bucket": "enriched",
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "permission": "android.permission.internet",
                "type_slug": "banker",
                "type_sample_count": 100,
                "background_sample_count": 10,
                "type_prevalence_pct": 95.0,
                "non_type_prevalence_pct": 90.0,
                "odds_ratio": 1.5,
                "p_value": 0.5,
                "q_value_fdr": 0.5,
                "interpretation_bucket": "no_signal",
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "permission": "android.permission.request_install_packages",
                "type_slug": "dropper",
                "type_sample_count": 10,
                "background_sample_count": 100,
                "type_prevalence_pct": 80.0,
                "non_type_prevalence_pct": 5.0,
                "odds_ratio": 70.0,
                "p_value": 0.0,
                "q_value_fdr": 0.0,
                "interpretation_bucket": "strong_enriched",
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
        ]
    ).to_csv(tables / f"permission_type_enrichment_{run_id}.csv", index=False)

    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "type_slug": "banker",
                "capability_bundle": "sms_telephony",
                "prevalence": 0.4,
                "prevalence_pct": 40.0,
                "positive_count": 40,
                "sample_count": 100,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "run_id": run_id,
                "type_slug": "dropper",
                "capability_bundle": "install_packages",
                "prevalence": 0.8,
                "prevalence_pct": 80.0,
                "positive_count": 8,
                "sample_count": 10,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
        ]
    ).to_csv(tables / f"type_capability_bundle_prevalence_{run_id}.csv", index=False)

    pd.DataFrame(
        [
            {
                "type_a": "banker",
                "type_b": "dropper",
                "support_a": 100,
                "support_b": 10,
                "jaccard_similarity": 0.2,
                "cosine_similarity": 0.5,
                "spearman_correlation": 0.1,
                "correlation_status": "defined",
                "left_profile_constant": False,
                "right_profile_constant": False,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
        ]
    ).to_csv(tables / f"type_permission_similarity_{run_id}.csv", index=False)

    pd.DataFrame(
        [
            {
                "family_id": 1,
                "family_canonical": "Huge",
                "sample_count": 90,
                "type_slug": "banker",
                "benchmark_eligible_n_ge_3": True,
                "support_ge_30_flag": 1,
                "support_ge_50_flag": 1,
                "run_id": run_id,
            },
            {
                "family_id": 2,
                "family_canonical": "Small",
                "sample_count": 10,
                "type_slug": "banker",
                "benchmark_eligible_n_ge_3": True,
                "support_ge_30_flag": 0,
                "support_ge_50_flag": 0,
                "run_id": run_id,
            },
            {
                "family_id": 3,
                "family_canonical": "Necro",
                "sample_count": 7,
                "type_slug": "dropper",
                "benchmark_eligible_n_ge_3": True,
                "support_ge_30_flag": 0,
                "support_ge_50_flag": 0,
                "run_id": run_id,
            },
            {
                "family_id": 4,
                "family_canonical": "Clast82",
                "sample_count": 3,
                "type_slug": "dropper",
                "benchmark_eligible_n_ge_3": True,
                "support_ge_30_flag": 0,
                "support_ge_50_flag": 0,
                "run_id": run_id,
            },
        ]
    ).to_csv(tables / f"family_support_distribution_{run_id}.csv", index=False)

    pd.DataFrame(
        [
            {
                "family_canonical": "Huge",
                "type_slug": "banker",
                "family_support": 90,
                "permission": "android.permission.read_sms",
                "positive_count": 90,
                "prevalence_pct": 100.0,
                "benchmark_eligible_n_ge_3": True,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "family_canonical": "Small",
                "type_slug": "banker",
                "family_support": 10,
                "permission": "android.permission.read_sms",
                "positive_count": 0,
                "prevalence_pct": 0.0,
                "benchmark_eligible_n_ge_3": True,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "family_canonical": "Necro",
                "type_slug": "dropper",
                "family_support": 7,
                "permission": "android.permission.read_media_images",
                "positive_count": 7,
                "prevalence_pct": 100.0,
                "benchmark_eligible_n_ge_3": True,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
            {
                "family_canonical": "Clast82",
                "type_slug": "dropper",
                "family_support": 3,
                "permission": "android.permission.read_media_images",
                "positive_count": 0,
                "prevalence_pct": 0.0,
                "benchmark_eligible_n_ge_3": True,
                "pattern_score": 1,
                "pattern_level": 1,
                "pattern_label": "x",
                "pattern_basis": "x",
                "pattern_confidence": "x",
                "pattern_reason": "x",
            },
        ]
    ).to_csv(tables / f"permission_prevalence_by_family_{run_id}.csv", index=False)

    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "type_slug": "banker",
                "sample_count": 100,
                "dangerous_count_strict_mean": 6.0,
                "dangerous_count_strict_median": 5.0,
                "dangerous_count_inclusive_mean": 10.0,
                "dangerous_count_inclusive_median": 9.0,
                "dangerous_count_unknown_component_mean": 1.0,
                "unknown_protection_rate": 0.1,
                "total_perm_count_mean": 20.0,
                "total_perm_count_median": 20.0,
                "permission_source_aosp_rate": 0.9,
                "permission_source_oem_rate": 0.05,
                "permission_source_app_defined_rate": 0.03,
                "permission_source_unknown_rate": 0.02,
            },
            {
                "run_id": run_id,
                "type_slug": "dropper",
                "sample_count": 10,
                "dangerous_count_strict_mean": 4.0,
                "dangerous_count_strict_median": 4.0,
                "dangerous_count_inclusive_mean": 7.0,
                "dangerous_count_inclusive_median": 7.0,
                "dangerous_count_unknown_component_mean": 1.0,
                "unknown_protection_rate": 0.1,
                "total_perm_count_mean": 15.0,
                "total_perm_count_median": 15.0,
                "permission_source_aosp_rate": 0.9,
                "permission_source_oem_rate": 0.05,
                "permission_source_app_defined_rate": 0.03,
                "permission_source_unknown_rate": 0.02,
            },
        ]
    ).to_csv(tables / f"dangerous_distribution_by_type_{run_id}.csv", index=False)

    pd.DataFrame(
        [
            {
                "dangerous_bucket": "normal",
                "feature_column": "perm__android_permission_internet",
                "permission_string": "android.permission.internet",
                "pi_bucket_source": "AOSP",
                "global_support": 100,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "dangerous",
                "feature_column": "perm__android_permission_read_sms",
                "permission_string": "android.permission.read_sms",
                "pi_bucket_source": "AOSP",
                "global_support": 40,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "dangerous",
                "feature_column": "perm__android_permission_read_media_images",
                "permission_string": "android.permission.read_media_images",
                "pi_bucket_source": "AOSP",
                "global_support": 20,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "dangerous",
                "feature_column": "perm__android_permission_request_install_packages",
                "permission_string": "android.permission.request_install_packages",
                "pi_bucket_source": "AOSP",
                "global_support": 15,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "unknown",
                "feature_column": "perm__android_permission_install_packages",
                "permission_string": "android.permission.install_packages",
                "pi_bucket_source": "AOSP",
                "global_support": 5,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "google",
                "feature_column": "perm__com_google_android_providers_gsf_permission_read_gservices",
                "permission_string": "com.google.android.providers.gsf.permission.read_gservices",
                "pi_bucket_source": "GOOGLE",
                "global_support": 8,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "oem_vendor",
                "feature_column": "perm__com_samsung_android_providers_context_permission_write_use_app_feature_survey",
                "permission_string": "com.samsung.android.providers.context.permission.write_use_app_feature_survey",
                "pi_bucket_source": "OEM",
                "global_support": 3,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "app_defined",
                "feature_column": "perm__com_example_app_perm",
                "permission_string": "com.example.app.perm",
                "pi_bucket_source": "APP_DEFINED",
                "global_support": 1,
                "retained_after_pruning": "no",
            },
            {
                "dangerous_bucket": "unknown",
                "feature_column": "perm__weird",
                "permission_string": "weird.token",
                "pi_bucket_source": "UNKNOWN",
                "global_support": 1,
                "retained_after_pruning": "no",
            },
        ]
    ).to_csv(run_root / "diagnostics" / "permission_feature_audit.csv", index=False)
    return run_root


def test_build_overall_and_family_balance() -> None:
    prevalence = pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "permission": "p1",
                "n_samples": 100,
                "permission_positive_count": 50,
                "prevalence_pct": 50.0,
            },
            {
                "type_slug": "dropper",
                "permission": "p1",
                "n_samples": 10,
                "permission_positive_count": 10,
                "prevalence_pct": 100.0,
            },
        ]
    )
    overall = build_overall_permission_prevalence(prevalence)
    assert abs(float(overall.iloc[0]["prevalence_pct"]) - (6000.0 / 110.0)) < 1e-6

    frame = pd.DataFrame(
        [
            {
                "family_canonical": "Huge",
                "type_slug": "banker",
                "family_support": 90,
                "permission": "android.permission.read_sms",
                "positive_count": 90,
                "prevalence_pct": 100.0,
            },
            {
                "family_canonical": "Small",
                "type_slug": "banker",
                "family_support": 10,
                "permission": "android.permission.read_sms",
                "positive_count": 0,
                "prevalence_pct": 0.0,
            },
        ]
    )
    out = build_family_balanced_type_prevalence(frame, min_family_support=3)
    assert abs(float(out.iloc[0]["family_balanced_prevalence_pct"]) - 50.0) < 1e-9
    assert abs(float(out.iloc[0]["sample_weighted_prevalence_pct"]) - 90.0) < 1e-9


def test_type_inventory_reconciles_and_flags_unknown() -> None:
    snap = pd.DataFrame(
        [
            {"sample_id": 1, "type_slug": "banker", "family_canonical": "A"},
            {"sample_id": 2, "type_slug": "banker", "family_canonical": "B"},
            {"sample_id": 3, "type_slug": "unknown", "family_canonical": ""},
            {"sample_id": 4, "type_slug": "dropper", "family_canonical": "Necro"},
        ]
    )
    family_support = pd.DataFrame(
        [
            {"family_canonical": "A", "type_slug": "banker", "sample_count": 1},
            {"family_canonical": "B", "type_slug": "banker", "sample_count": 1},
            {"family_canonical": "Necro", "type_slug": "dropper", "sample_count": 1},
        ]
    )
    prevalence = pd.DataFrame(
        [
            {"type_slug": "banker", "permission": "p", "n_samples": 2, "permission_positive_count": 1},
            {"type_slug": "unknown", "permission": "p", "n_samples": 1, "permission_positive_count": 0},
            {"type_slug": "dropper", "permission": "p", "n_samples": 1, "permission_positive_count": 1},
        ]
    )
    inv = build_complete_type_inventory(
        analysis_snapshot=snap,
        family_support=family_support,
        prevalence_by_type=prevalence,
        prepared_sample_count=4,
        min_main_samples=2,
        min_main_families=2,
        max_dominance_for_main=0.9,
    )
    assert int(inv["sample_count"].sum()) == 4
    assert inv.attrs["reconciliation"]["reconciles"] is True
    unknown = inv.loc[inv["type_slug"] == "unknown"].iloc[0]
    assert not bool(unknown["included_in_main_comparison"])
    assert unknown["suppression_or_inclusion_reason"] == "unknown_or_unresolved_type"


def test_permission_role_and_run_status(tmp_path: Path) -> None:
    assert (
        classify_permission_role(
            overall_prevalence_pct=95.0,
            type_prevalence_pct=96.0,
            non_type_prevalence_pct=94.0,
            odds_ratio=1.2,
        )
        == "high_prevalence_low_discrimination"
    )
    assert classify_type_inclusion(
        type_slug="backdoor",
        sample_count=200,
        active_families=2,
        largest_family_share=0.99,
        mapped_family_samples=200,
    ) == (False, "insufficient_family_support")

    run_root = tmp_path / "r"
    run_root.mkdir()
    (run_root / ".RUNNING").write_text("{}", encoding="utf-8")
    status = detect_source_run_status(run_root)
    assert status["report_status"] == "PROVISIONAL"
    assert status["source_run_status"] == "RUNNING"
    (run_root / ".RUNNING").unlink()
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_status": "complete"}),
        encoding="utf-8",
    )
    status2 = detect_source_run_status(run_root)
    assert status2["report_status"] == "FINAL_FROM_COMPLETED_RUN"


def test_compose_provisional_and_deterministic(tmp_path: Path) -> None:
    run_id = "fixture_run"
    run_root = _write_fixture_run(tmp_path, run_id=run_id, with_running=True)
    manifest1 = compose_type_permission_pattern_report(run_root=run_root, run_id=run_id)
    assert manifest1["report_status"] == "PROVISIONAL"
    assert manifest1["source_run_status"] == "RUNNING"
    assert manifest1["composer_version"] == COMPOSER_VERSION
    assert manifest1["type_accounting_reconciliation"]["reconciles"] is True
    assert "input_sha256" in manifest1 and "coverage" in manifest1["input_sha256"]
    assert "output_sha256" in manifest1

    out = Path(manifest1["output_dir"])
    report = (out / f"type_permission_pattern_report_{run_id}.md").read_text(encoding="utf-8")
    assert "Report status: **PROVISIONAL**" in report
    assert "Complete type inventory" in report
    inv = pd.read_csv(out / f"type_inventory_{run_id}.csv")
    assert int(inv["sample_count"].sum()) == 110

    # Deterministic CSV hashes when regenerated without timestamp-sensitive CSV content.
    hash_before = sha256_file(out / f"type_inventory_{run_id}.csv")
    manifest2 = compose_type_permission_pattern_report(run_root=run_root, run_id=run_id)
    hash_after = sha256_file(Path(manifest2["output_dir"]) / f"type_inventory_{run_id}.csv")
    assert hash_before == hash_after

    # Final status when .RUNNING cleared.
    (run_root / ".RUNNING").unlink()
    manifest3 = compose_type_permission_pattern_report(run_root=run_root, run_id=run_id)
    assert manifest3["report_status"] == "FINAL_FROM_COMPLETED_RUN"
    text = Path(manifest3["report_markdown"]).read_text(encoding="utf-8")
    assert "FINAL_FROM_COMPLETED_RUN" in text
