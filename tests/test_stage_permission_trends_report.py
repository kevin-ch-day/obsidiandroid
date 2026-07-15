import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from obsidiandroid.pipeline import stage_permission_trends_report as report_stage
from obsidiandroid.pipeline.permission_trends import attack_mapping as perm_attack_mapping
from obsidiandroid.pipeline.permission_trends import bundle_exports as perm_bundle_exports
from obsidiandroid.pipeline.permission_trends import bundle_manifest as perm_bundle_manifest
from obsidiandroid.pipeline.permission_trends import pattern_framework as perm_pattern_framework
from obsidiandroid.pipeline.permission_trends import sample_permission_data as sample_perm_data
from obsidiandroid.pipeline.permission_trends import reporting_support as perm_trends_reporting_support
from obsidiandroid.pipeline.permission_trends import stats_core


def test_compute_consensus_metrics_produces_expected_columns():
    votes_df = pd.DataFrame(
        {
            "sample_id": [1, 1, 1, 2, 2],
            "vendor": ["a", "b", "c", "a", "b"],
            "parsed_family": ["x", "x", "y", "z", "z"],
        }
    )
    result = report_stage._compute_consensus_metrics(votes_df=votes_df, prefix="all")

    assert not result.empty
    assert "consensus_score_all_vendors" in result.columns
    assert "consensus_entropy_all_vendors" in result.columns
    row1 = result[result["sample_id"] == 1].iloc[0]
    assert row1["vendor_count_all"] == 3
    assert row1["top1_vote_share_all"] == 0.666667


def test_build_type_confusion_summary_counts_within_and_cross_type_errors():
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 20, 30, 40],
            "type_slug": ["banker", "banker", "dropper", "rat"],
        }
    )
    model_results = {
        "true_labels": {"1": "10", "2": "20", "3": "30"},
        "prediction_metadata": {
            "1": {"decoded_label": "20", "confidence": 0.9},  # banker->banker
            "2": {"decoded_label": "30", "confidence": 0.8},  # banker->dropper
            "3": {"decoded_label": "30", "confidence": 0.95},  # correct
        },
    }
    summary_df, detail_df = report_stage._build_type_confusion_summary(
        sample_core_df=sample_core_df,
        model_results=model_results,
        run_id="test_run",
    )

    assert not summary_df.empty
    summary = dict(zip(summary_df["error_type"], summary_df["count"]))
    assert summary["within_type_error"] == 1
    assert summary["cross_type_error"] == 1
    assert summary["total_error"] == 2
    assert len(detail_df) == 2


def test_filter_permission_rows_by_view_uses_dictionary_matches():
    df = pd.DataFrame(
        {
            "permission_string": [
                "android.permission.read_sms",
                "android.permission.get_installed_apps",
                "com.vendor.app.permission.foo",
            ],
            "permission_source": ["AOSP", "AOSP", "OEM"],
            "is_aosp_dict_match": [1, 0, 0],
            "is_oem_dict_match": [0, 1, 1],
        }
    )

    aosp_only = report_stage._filter_permission_rows_by_view(df, view_name="aosp_only")
    ecosystem = report_stage._filter_permission_rows_by_view(df, view_name="ecosystem")

    assert aosp_only["permission_string"].tolist() == ["android.permission.read_sms"]
    assert set(ecosystem["permission_string"].tolist()) == {
        "android.permission.read_sms",
        "android.permission.get_installed_apps",
        "com.vendor.app.permission.foo",
    }


def test_fetch_permission_rows_for_samples_prefers_permission_string_norm(monkeypatch) -> None:
    sample_perm_data.permission_contracts.reset_permission_obs_norm_cache()
    monkeypatch.setattr(
        sample_perm_data.permission_contracts.db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string", "permission_string_norm"],
    )
    captured: dict[str, object] = {}

    def _fake_execute_permission_query(query, **kwargs):
        captured["query"] = query
        return pd.DataFrame(
            {
                "sample_id": [1, 1],
                "permission_string_raw": [
                    "android.permission.READ_SMS",
                    "ANDROID.PERMISSION.read_sms",
                ],
                "permission_string": [
                    "android.permission.read_sms",
                    "android.permission.read_sms",
                ],
                "protection_level": ["DANGEROUS", "DANGEROUS"],
                "permission_source": ["AOSP", "AOSP"],
                "is_aosp_dict_match": [1, 1],
                "is_oem_dict_match": [0, 0],
            }
        )

    monkeypatch.setattr(
        sample_perm_data.db_engine,
        "execute_permission_query",
        _fake_execute_permission_query,
    )

    out = sample_perm_data.fetch_permission_rows_for_samples([1])
    assert "permission_string_norm" in str(captured.get("query", ""))
    assert out["permission_string"].tolist() == ["android.permission.read_sms"]

    assert "permission_string_norm" in str(captured.get("query", ""))
    assert out["permission_string"].tolist() == ["android.permission.read_sms"]


def test_fetch_permission_rows_for_samples_falls_back_without_norm(monkeypatch) -> None:
    sample_perm_data.permission_contracts.reset_permission_obs_norm_cache()
    monkeypatch.setattr(
        sample_perm_data.permission_contracts.db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string"],
    )
    captured: dict[str, object] = {}

    def _fake_execute_permission_query(query, **kwargs):
        captured["query"] = query
        return pd.DataFrame(
            {
                "sample_id": [1, 1],
                "permission_string_raw": [
                    "android.permission.READ_SMS",
                    "ANDROID.PERMISSION.read_sms",
                ],
                "permission_string": [
                    "android.permission.read_sms",
                    "android.permission.read_sms",
                ],
                "protection_level": ["DANGEROUS", "DANGEROUS"],
                "permission_source": ["AOSP", "AOSP"],
                "is_aosp_dict_match": [1, 1],
                "is_oem_dict_match": [0, 0],
            }
        )

    monkeypatch.setattr(
        sample_perm_data.db_engine,
        "execute_permission_query",
        _fake_execute_permission_query,
    )

    out = sample_perm_data.fetch_permission_rows_for_samples([1])


def test_js_distance_zero_for_identical() -> None:
    p = np.array([0.2, 0.3, 0.5], dtype=float)
    assert stats_core.js_distance(p, p) == pytest.approx(0.0, abs=1e-9)


def test_build_family_permission_similarity_annotates_pattern_fields() -> None:
    family_prevalence_df = pd.DataFrame(
        [
            {
                "family_canonical": "fam_a",
                "type_slug": "banker",
                "family_support": 12,
                "permission": "android.permission.read_sms",
                "prevalence_pct": 100.0,
            },
            {
                "family_canonical": "fam_a",
                "type_slug": "banker",
                "family_support": 12,
                "permission": "android.permission.receive_sms",
                "prevalence_pct": 100.0,
            },
            {
                "family_canonical": "fam_b",
                "type_slug": "banker",
                "family_support": 14,
                "permission": "android.permission.read_sms",
                "prevalence_pct": 100.0,
            },
            {
                "family_canonical": "fam_b",
                "type_slug": "banker",
                "family_support": 14,
                "permission": "android.permission.receive_sms",
                "prevalence_pct": 100.0,
            },
        ]
    )

    out = report_stage._build_family_permission_similarity(family_prevalence_df)  # pylint: disable=protected-access

    assert len(out) == 1
    row = out.iloc[0]
    assert row["pattern_basis"] == "RAW_PERMISSION+FAMILY_LEVEL+MIXED"
    assert row["pattern_label"] == "Certain Pattern"
    assert row["pattern_confidence"] == "high"
    assert "shared-pattern similarity" in row["pattern_reason"]


def test_spearman_similarity_preserves_constant_input_as_undefined() -> None:
    details = report_stage._spearman_similarity_details(  # pylint: disable=protected-access
        np.array([0.0, 0.0]), np.array([0.0, 1.0])
    )
    assert details["spearman_correlation"] is None
    assert details["correlation_status"] == "constant_input"
    assert details["left_profile_constant"] is True


def test_annotate_similarity_patterns_marks_conflicting_metrics() -> None:
    df = pd.DataFrame(
        [
            {
                "support_a": 12,
                "support_b": 15,
                "cosine_similarity": 0.82,
                "jaccard_similarity": 0.10,
                "spearman_correlation": 0.90,
                "same_type_flag": False,
            }
        ]
    )

    out = perm_pattern_framework.annotate_similarity_patterns(
        df,
        support_a_col="support_a",
        support_b_col="support_b",
        same_type_col="same_type_flag",
        basis="type_permission_similarity",
    )

    row = out.iloc[0]
    assert row["pattern_label"] == "Very Weak Pattern"
    assert row["pattern_basis"] == "RAW_PERMISSION+TYPE_LEVEL+MIXED"
    assert "similarity metrics disagree" in row["pattern_reason"]


def test_annotate_similarity_patterns_marks_neutral_rank_agreement_as_conflicting() -> None:
    df = pd.DataFrame(
        [
            {
                "support_a": 12,
                "support_b": 15,
                "cosine_similarity": 0.82,
                "jaccard_similarity": 0.82,
                "spearman_correlation": 0.0,
                "same_type_flag": True,
            }
        ]
    )

    out = perm_pattern_framework.annotate_similarity_patterns(
        df,
        support_a_col="support_a",
        support_b_col="support_b",
        same_type_col="same_type_flag",
        basis="family_permission_similarity",
    )

    row = out.iloc[0]
    assert row["pattern_label"] == "Very Weak Pattern"
    assert "similarity metrics disagree" in row["pattern_reason"]


def test_build_banker_temporal_pattern_rows_annotates_latest_quarter_patterns() -> None:
    temporal_trends_df = pd.DataFrame(
        [
            {
                "run_id": "r1",
                "period_quarter": "2025-Q1",
                "year": 2025,
                "quarter": 1,
                "sample_count": 12,
                "banker_sample_count": 5,
                "banker_read_sms_prevalence": 0.80,
                "banker_receive_sms_prevalence": 0.60,
                "banker_send_sms_prevalence": 0.20,
                "banker_bind_accessibility_service_prevalence": 0.40,
                "banker_system_alert_window_prevalence": 0.50,
                "banker_request_install_packages_prevalence": 0.10,
            }
        ]
    )

    out = report_stage._build_banker_temporal_pattern_rows(  # pylint: disable=protected-access
        temporal_trends_df=temporal_trends_df,
        run_id="r1",
    )

    assert not out.empty
    read_sms = out[out["permission"] == "android.permission.read_sms"].iloc[0]
    assert read_sms["pattern_basis"] == "RAW_PERMISSION+TYPE_LEVEL+TEMPORAL"
    assert read_sms["pattern_label"] == "Moderate-Strong Pattern"
    assert int(read_sms["positive_count"]) == 4
    assert "prevalence-only evidence is capped" in read_sms["pattern_reason"]


def test_bh_fdr_monotone() -> None:
    p = [0.01, 0.04, 0.10]
    out = stats_core.bh_fdr(p)
    assert len(out) == 3
    assert all(0.0 <= x <= 1.0 for x in out)


def test_spearman_with_bootstrap_strong_correlation() -> None:
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    y = pd.Series([1.1, 2.0, 3.2, 3.9, 5.1])
    rho, _p, _lo, _hi = stats_core.spearman_with_bootstrap_ci(x, y, bootstrap_resamples=30)
    assert rho > 0.99


def test_fetch_permission_aggregates_prefers_permission_string_norm(monkeypatch) -> None:
    sample_perm_data.permission_contracts.reset_permission_obs_norm_cache()
    monkeypatch.setattr(
        sample_perm_data.permission_contracts.db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string", "permission_string_norm"],
    )
    captured: dict[str, object] = {}

    def _fake_execute_permission_query(query, **kwargs):
        captured["query"] = query
        return pd.DataFrame(
            {
                "sample_id": [1],
                "permission_obs_rows": [2],
                "permission_unique_count": [1],
                "permission_common_rows": [0],
            }
        )

    monkeypatch.setattr(
        sample_perm_data.db_engine,
        "execute_permission_query",
        _fake_execute_permission_query,
    )

    out = sample_perm_data.fetch_permission_aggregates()

    assert "permission_string_norm" in str(captured.get("query", ""))
    assert int(out.loc[0, "permission_unique_count"]) == 1


def test_build_permission_anomalies_excludes_stale_zero_count_rule():
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "sha256": ["a" * 64, "b" * 64, "short", "c" * 64],
            "android_package_name": ["pkg.one", "pkg.two", "pkg.three", ""],
            "android_permission_count": [0, 2, 0, 0],
            "permission_obs_rows": [5, 0, 0, 0],
        }
    )

    out = report_stage._build_permission_anomalies(df, run_id="r1")
    reasons = set(out["reason"].tolist())
    assert "run_id" in out.columns

    assert "catalog_permission_count_zero_but_obs_rows_exist" not in reasons
    assert "catalog_permission_count_nonzero_but_missing_obs_rows" in reasons
    assert "missing_or_invalid_sha256" in reasons
    assert "missing_package_name" in reasons


def test_select_banker_summary_rows_prioritizes_forced_permissions():
    df = pd.DataFrame(
        {
            "permission": [
                "android.permission.bind_accessibility_service",
                "android.permission.system_alert_window",
                "android.permission.read_sms",
                "android.permission.get_installed_apps",
            ],
            "odds_ratio": [50.0, 3.0, 1.0, 900.0],
            "p_value_fdr_bh": [1e-8, 1e-4, 0.6, 1e-40],
            "forced_permission_flag": [1, 1, 1, 0],
        }
    )

    out = report_stage._select_banker_summary_rows(df, limit=3)

    assert len(out) == 3
    assert set(out["permission"].tolist()) == {
        "android.permission.bind_accessibility_service",
        "android.permission.system_alert_window",
        "android.permission.read_sms",
    }


def test_zip_bundle_uses_bundle_name(tmp_path: Path):
    bundle_dir = tmp_path / "paper_bundle_test123"
    artifact_dir = bundle_dir / "permission_trends"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "dummy.txt").write_text("ok", encoding="utf-8")

    zip_path = report_stage._zip_bundle(bundle_dir)

    assert Path(zip_path).name == "paper_bundle_test123.zip"
    assert Path(zip_path).exists()


def test_zip_bundle_for_permission_trends_targets_parent_bundle(tmp_path: Path):
    bundle_root = tmp_path / "paper_bundle_abc"
    bundle_dir = bundle_root / "permission_trends"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "dummy.txt").write_text("ok", encoding="utf-8")

    zip_path = report_stage._zip_bundle(bundle_dir)

    assert Path(zip_path).name == "permission_trends.zip"
    assert Path(zip_path).exists()


def test_zip_bundle_for_permission_trends_module_root_uses_bundle_name(tmp_path: Path):
    bundle_dir = tmp_path / "permission_trends"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "dummy.txt").write_text("ok", encoding="utf-8")

    zip_path = report_stage._zip_bundle(bundle_dir)

    assert Path(zip_path).name == "permission_trends.zip"
    assert Path(zip_path).exists()


def test_sample_level_permission_metrics_inclusive_counts_unknown():
    sample_core_df = pd.DataFrame({"sample_id": [1, 2]})
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 1, 2],
            "permission_string": ["a", "b", "c"],
            "protection_level": ["DANGEROUS", "UNKNOWN", "NORMAL"],
        }
    )

    out = report_stage._build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    row1 = out[out["sample_id"] == 1].iloc[0]
    row2 = out[out["sample_id"] == 2].iloc[0]

    assert int(row1["dangerous_count_strict"]) == 1
    assert int(row1["dangerous_count_inclusive"]) == 2
    assert int(row2["dangerous_count_strict"]) == 0
    assert int(row2["dangerous_count_inclusive"]) == 0


def test_banker_family_pattern_clusters_produces_assignments():
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 10, 20, 20],
            "type_slug": ["banker", "banker", "banker", "banker"],
        }
    )
    family_profiles_df = pd.DataFrame(
        {
            "run_id": ["r"] * 4,
            "family_id": [10, 10, 20, 20],
            "family_canonical": ["fam_a", "fam_a", "fam_b", "fam_b"],
            "profile_scope": ["appendix", "appendix", "appendix", "appendix"],
            "permission": ["p1", "p2", "p1", "p2"],
            "prevalence": [0.9, 0.1, 0.2, 0.8],
            "sample_count": [30, 30, 35, 35],
        }
    )

    assignments_df, profiles_df = report_stage._build_banker_family_pattern_clusters(
        sample_core_df=sample_core_df,
        family_profiles_df=family_profiles_df,
        run_id="r",
    )

    assert not assignments_df.empty
    assert set(assignments_df["family_id"].tolist()) == {10, 20}
    assert "cluster_id" in assignments_df.columns
    assert not profiles_df.empty


def test_build_family_permission_profiles_excludes_appendix_duplicates() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5, 6],
            "family_id": [10, 10, 20, 20, 30, 30],
            "family_canonical": ["DoNot", "DoNot", "Gigabud", "Gigabud", "Copybara", "Copybara"],
            "type_slug": ["spyware", "spyware", "banker", "banker", "banker", "banker"],
        }
    )
    permission_matrix_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5, 6],
            "android.permission.internet": [1, 1, 1, 1, 1, 0],
            "android.permission.read_sms": [0, 0, 1, 1, 0, 0],
        }
    )

    original_selector = report_stage._select_visual_families
    report_stage._select_visual_families = lambda **_kwargs: ["DoNot", "Gigabud"]
    try:
        profiles_df, _entropy_df = report_stage._build_family_permission_profiles(
            sample_core_df=sample_core_df,
            permission_matrix_df=permission_matrix_df,
            run_id="r",
        )
    finally:
        report_stage._select_visual_families = original_selector

    scope_map = profiles_df.groupby("family_canonical")["profile_scope"].unique().to_dict()
    assert set(scope_map["DoNot"]) == {"main"}
    assert set(scope_map["Gigabud"]) == {"main"}


def test_build_generic_vs_non_generic_summary_skips_effect_size_without_generic_group() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "type_slug": ["banker", "rat"],
            "family_id": [10, 20],
        }
    )
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 1, 2],
            "permission_string": ["a", "b", "a"],
            "protection_level": ["DANGEROUS", "NORMAL", "DANGEROUS"],
        }
    )
    permission_matrix_df = pd.DataFrame({"sample_id": [1, 2], "a": [1, 1], "b": [1, 0]})
    consensus_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "vendor_count": [10, 10],
            "consensus_score_all_vendors": [0.8, 0.6],
        }
    )

    out = report_stage._build_generic_vs_non_generic_summary(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        permission_matrix_df=permission_matrix_df,
        consensus_df=consensus_df,
        run_id="r",
    )

    assert set(out["group"].tolist()) == {"unresolved"}


def test_build_generic_vs_non_generic_summary_uses_governed_tier_contract() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, None, None, None],
            "family_canonical": ["DoNot", "", "", ""],
            "type_slug": ["spyware", "rat", "banker", "unknown"],
            "category_primary": ["trojan", "", "", "malware"],
            "category_subtype": ["spyware", "", "trojan", ""],
            "sample_label_kind": [
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
                "unclassified",
            ],
        }
    )
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "permission_string": ["a", "a", "b", "c"],
            "protection_level": ["DANGEROUS", "DANGEROUS", "NORMAL", "UNKNOWN"],
        }
    )
    permission_matrix_df = pd.DataFrame(
        {"sample_id": [1, 2, 3, 4], "a": [1, 1, 0, 0], "b": [0, 0, 1, 0], "c": [0, 0, 0, 1]}
    )
    consensus_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "vendor_count": [10, 10, 10, 10],
            "consensus_score_all_vendors": [0.9, 0.7, 0.5, 0.2],
        }
    )

    out = report_stage._build_generic_vs_non_generic_summary(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        permission_matrix_df=permission_matrix_df,
        consensus_df=consensus_df,
        run_id="r",
    )

    assert set(out["group"].tolist()) == {"non_generic", "generic_or_coarse", "unresolved", "effect_size"}
    counts = dict(zip(out["group"], out["sample_count"]))
    assert counts["non_generic"] == 1
    assert counts["generic_or_coarse"] == 2
    assert counts["unresolved"] == 1


def test_build_generic_definition_audit_uses_governed_tier_contract() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 11, None, None],
            "family_canonical": ["DoNot", "Gigabud", "", ""],
            "type_slug": ["spyware", "banker", "rat", "unknown"],
            "category_primary": ["trojan", "trojan", "", "malware"],
            "category_subtype": ["spyware", "banker", "", ""],
            "sample_label_kind": [
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
                "unclassified",
            ],
        }
    )
    family_support_df = pd.DataFrame({"family_id": [10, 11], "sample_count": [40, 5]})
    consensus_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "consensus_score_all_vendors": [0.95, 0.70, 0.40, 0.10],
            "consensus_entropy_all_vendors": [0.10, 0.20, 0.40, 0.80],
            "vendor_count": [10, 10, 10, 10],
        }
    )

    out = report_stage._build_generic_definition_audit(
        sample_core_df=sample_core_df,
        family_support_df=family_support_df,
        consensus_df=consensus_df,
        run_id="r",
    )
    metrics = dict(zip(out["metric"], out["value"]))

    assert metrics["major_family_count"] == 1
    assert metrics["minor_family_count"] == 1
    assert metrics["generic_or_coarse_count"] == 1
    assert metrics["unresolved_count"] == 1
    assert metrics["generic_low_support_overlap_count"] == 1
    assert metrics["unresolved_low_support_overlap_count"] == 1


def test_export_run_summary_onepager_includes_permission_pattern_sections(tmp_path: Path) -> None:
    coverage_df = pd.DataFrame([{"sample_count": 100, "pct_with_permission_rows": 0.97}])
    dangerous_df = pd.DataFrame([{"unknown_protection_rate": 0.12}, {"unknown_protection_rate": 0.20}])
    consensus_df = pd.DataFrame([{"low_vendor_count_flag": 0}, {"low_vendor_count_flag": 1}])
    discriminability_df = pd.DataFrame(
        [
            {"permission": "android.permission.read_call_log", "cramers_v": 0.66, "global_support": 658},
            {"permission": "android.permission.set_wallpaper", "cramers_v": 0.63, "global_support": 560},
        ]
    )
    type_entropy_df = pd.DataFrame(
        [
            {"type_slug": "banker", "sample_count": 80, "permission_entropy": 3.9, "effective_diversity": 50.2},
            {"type_slug": "rat", "sample_count": 20, "permission_entropy": 3.7, "effective_diversity": 43.3},
        ]
    )
    family_profiles_df = pd.DataFrame(
        [
            {"family_canonical": "Devixor", "sample_count": 40, "profile_scope": "main", "permission": "android.permission.read_sms", "prevalence": 1.0},
            {"family_canonical": "Devixor", "sample_count": 40, "profile_scope": "main", "permission": "android.permission.receive_sms", "prevalence": 0.95},
            {"family_canonical": "Devixor", "sample_count": 40, "profile_scope": "main", "permission": "android.permission.internet", "prevalence": 0.90},
        ]
    )
    type_capability_df = pd.DataFrame(
        [
            {"type_slug": "banker", "sample_count": 80, "capability_bundle": "sms_telephony", "prevalence": 0.88},
            {"type_slug": "banker", "sample_count": 80, "capability_bundle": "account_contact", "prevalence": 0.73},
            {"type_slug": "banker", "sample_count": 80, "capability_bundle": "network_c2", "prevalence": 0.95},
        ]
    )
    family_capability_df = pd.DataFrame(
        [
            {"family_canonical": "Devixor", "sample_count": 40, "capability_bundle": "sms_telephony", "prevalence": 0.97},
            {"family_canonical": "Devixor", "sample_count": 40, "capability_bundle": "network_c2", "prevalence": 0.94},
            {"family_canonical": "Devixor", "sample_count": 40, "capability_bundle": "account_contact", "prevalence": 0.76},
        ]
    )
    attack_hypotheses_df = pd.DataFrame(
        [
            {
                "group_kind": "type",
                "group_value": "banker",
                "sample_count": 80,
                "attack_id": "T1636.004",
                "attack_name": "Protected User Data: SMS Messages",
                "confidence": "strong_inference",
                "evidence_permissions": "android.permission.read_sms, android.permission.receive_sms",
                "matched_permission_count": 2,
                "evidence_prevalence_mean": 0.8,
            }
        ]
    )

    out = perm_bundle_exports.export_run_summary_onepager(
        run_id="r1",
        profile_id="android_malware_all_current",
        bundle_dir=tmp_path,
        coverage_df=coverage_df,
        dangerous_df=dangerous_df,
        consensus_df=consensus_df,
        bundle_metadata={"vendor_constrained_run_flag": False, "dataset_time_contract": {}},
        banker_enrichment_df=pd.DataFrame(),
        select_banker_summary_rows=lambda df, limit=5: df.head(limit),
        discriminability_df=discriminability_df,
        type_entropy_df=type_entropy_df,
        family_profiles_df=family_profiles_df,
        type_capability_df=type_capability_df,
        family_capability_df=family_capability_df,
        attack_hypotheses_df=attack_hypotheses_df,
    )

    text = Path(out).read_text(encoding="utf-8")
    assert "Top permission discriminators:" in text
    assert "Type permission patterns:" in text
    assert "Type capability bundles:" in text
    assert "Example family permission signatures:" in text
    assert "Example family capability bundles:" in text
    assert "Top ATT&CK-Mobile capability hypotheses:" in text
    assert "T1636.004" in text


def test_build_attack_mobile_hypotheses_finds_sms_and_discovery_signals() -> None:
    prevalence_df = pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "sample_count": 50,
                "permission": "android.permission.read_sms",
                "prevalence": 0.82,
                "pattern_score": 82.0,
                "pattern_level": 6,
                "pattern_label": "Moderate Pattern",
                "pattern_basis": "RAW_PERMISSION+TYPE_LEVEL",
                "pattern_confidence": "high",
                "pattern_reason": "prevalence-only evidence is capped",
            },
            {
                "type_slug": "banker",
                "sample_count": 50,
                "permission": "android.permission.receive_sms",
                "prevalence": 0.77,
                "pattern_score": 77.0,
                "pattern_level": 6,
                "pattern_label": "Moderate Pattern",
                "pattern_basis": "RAW_PERMISSION+TYPE_LEVEL",
                "pattern_confidence": "high",
                "pattern_reason": "prevalence-only evidence is capped",
            },
            {
                "type_slug": "banker",
                "sample_count": 50,
                "permission": "android.permission.read_contacts",
                "prevalence": 0.61,
                "pattern_score": 61.0,
                "pattern_level": 6,
                "pattern_label": "Moderate Pattern",
                "pattern_basis": "RAW_PERMISSION+TYPE_LEVEL",
                "pattern_confidence": "high",
                "pattern_reason": "prevalence-only evidence is capped",
            },
            {
                "type_slug": "banker",
                "sample_count": 50,
                "permission": "android.permission.query_all_packages",
                "prevalence": 0.22,
                "pattern_score": 22.0,
                "pattern_level": 4,
                "pattern_label": "Very Weak Pattern",
                "pattern_basis": "RAW_PERMISSION+TYPE_LEVEL",
                "pattern_confidence": "moderate",
                "pattern_reason": "low prevalence",
            },
        ]
    )

    out = perm_attack_mapping.build_attack_mobile_hypotheses(
        prevalence_df=prevalence_df,
        run_id="r",
        group_field="type_slug",
        group_kind="type",
    )

    assert not out.empty
    got = {(row["group_value"], row["attack_id"]) for row in out.to_dict(orient="records")}
    assert ("banker", "T1636.004") in got
    assert ("banker", "T1636.003") in got
    assert ("banker", "T1418") in got
    sms_row = out[out["attack_id"] == "T1636.004"].iloc[0]
    assert sms_row["pattern_basis"] == "BEHAVIOR+TYPE_LEVEL+MIXED"
    assert sms_row["pattern_label"] == "Moderate Pattern"
    assert sms_row["pattern_confidence"] == "moderate"
    assert "permission-derived hypothesis" in sms_row["pattern_reason"]
    assert "mapping_confidence" in sms_row["pattern_reason"]


def test_build_attack_mobile_hypotheses_falls_back_when_pattern_fields_are_missing() -> None:
    prevalence_df = pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "sample_count": 50,
                "permission": "android.permission.read_sms",
                "prevalence": 0.82,
            },
            {
                "type_slug": "banker",
                "sample_count": 50,
                "permission": "android.permission.receive_sms",
                "prevalence": 0.77,
            },
        ]
    )

    out = perm_attack_mapping.build_attack_mobile_hypotheses(
        prevalence_df=prevalence_df,
        run_id="r",
        group_field="type_slug",
        group_kind="type",
    )

    assert not out.empty
    sms_row = out[out["attack_id"] == "T1636.004"].iloc[0]
    assert sms_row["pattern_basis"] == "BEHAVIOR+TYPE_LEVEL+MIXED"
    assert sms_row["pattern_label"] == "Moderate Pattern"
    assert sms_row["pattern_confidence"] == "moderate"


def test_build_type_capability_bundle_prevalence_reports_expected_bundles() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "banker", "rat"],
        }
    )
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 1, 2, 3, 3],
            "permission_string": [
                "android.permission.read_sms",
                "android.permission.internet",
                "android.permission.receive_sms",
                "android.permission.camera",
                "android.permission.record_audio",
            ],
        }
    )

    out = report_stage._build_type_capability_bundle_prevalence(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        run_id="r",
    )

    assert not out.empty
    by_key = {(row["type_slug"], row["capability_bundle"]): row for row in out.to_dict(orient="records")}
    assert ("banker", "sms_telephony") in by_key
    assert by_key[("banker", "sms_telephony")]["prevalence"] == 1.0
    assert ("banker", "network_c2") in by_key
    assert by_key[("banker", "network_c2")]["prevalence"] == 0.5
    assert ("rat", "surveillance_sensor") in by_key
    assert by_key[("rat", "surveillance_sensor")]["prevalence"] == 1.0


def test_build_permission_prevalence_by_type_outputs_expected_columns_and_counts() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "banker", "rat"],
        }
    )
    permission_matrix_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "android.permission.read_sms": [1, 0, 0],
            "android.permission.camera": [0, 0, 1],
        }
    )

    out = report_stage._build_permission_prevalence_by_type(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
    )

    assert {
        "type_slug",
        "permission",
        "n_samples",
        "permission_positive_count",
        "prevalence_pct",
    }.issubset(out.columns)
    banker_sms = out[
        (out["type_slug"] == "banker")
        & (out["permission"] == "android.permission.read_sms")
    ].iloc[0]
    assert int(banker_sms["n_samples"]) == 2
    assert int(banker_sms["permission_positive_count"]) == 1
    assert float(banker_sms["prevalence_pct"]) == 50.0


def test_build_permission_prevalence_by_family_marks_benchmark_eligibility() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 10, 10, 20],
            "family_canonical": ["Alpha", "Alpha", "Alpha", "Beta"],
            "type_slug": ["banker", "banker", "banker", "rat"],
            "category_primary": ["banker", "banker", "banker", "rat"],
            "category_subtype": ["", "", "", ""],
            "sample_label_kind": ["family_or_common_name"] * 4,
            "family_label_raw": ["Alpha", "Alpha", "Alpha", "Beta"],
            "vt_family_token": ["alpha", "alpha", "alpha", "beta"],
        }
    )
    permission_matrix_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "android.permission.read_sms": [1, 1, 0, 1],
        }
    )

    out = report_stage._build_permission_prevalence_by_family(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
        benchmark_min_support=3,
    )

    assert {
        "family_canonical",
        "type_slug",
        "family_support",
        "permission",
        "positive_count",
        "prevalence_pct",
        "benchmark_eligible_n_ge_3",
    }.issubset(out.columns)
    alpha = out[out["family_canonical"] == "Alpha"].iloc[0]
    beta = out[out["family_canonical"] == "Beta"].iloc[0]
    assert bool(alpha["benchmark_eligible_n_ge_3"]) is True
    assert bool(beta["benchmark_eligible_n_ge_3"]) is False


def test_assign_permission_signal_keys_respects_behavior_and_scaffolding_lanes() -> None:
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 1, 2, 3, 4],
            "permission_string": [
                "android.permission.read_sms",
                "android.permission.bind_accessibility_service",
                "com.foo.dynamic_receiver_not_exported_permission",
                "com.anddoes.launcher.permission.update_count",
                "com.google.android.c2dm.permission.receive",
            ],
            "permission_source": ["AOSP", "AOSP", "APP_DEFINED", "APP_DEFINED", "GOOGLE"],
        }
    )
    out = report_stage._assign_permission_signal_keys(permission_rows_df)
    pairs = {(int(row["sample_id"]), str(row["signal_key"])) for _, row in out.iterrows()}
    assert (1, "sms") in pairs
    assert (1, "accessibility") in pairs
    assert (2, "app_defined_scaffolding") in pairs
    assert (3, "launcher_sdk_ecosystem_noise") in pairs
    assert (4, "google_gms_ecosystem") in pairs


def test_assign_permission_signal_keys_uses_governance_lane_mappings() -> None:
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "permission_string": [
                "android.permission.allocate_aggressive",
                "com.example.permission.safe_access",
            ],
            "permission_source": ["UNKNOWN", "UNKNOWN"],
            "candidate_source_family_key": ["needs_source_validation", ""],
            "effective_source_family_key": ["", "oem_vendor_permission"],
            "effective_review_lane": ["source_validation_required", ""],
        }
    )
    out = report_stage._assign_permission_signal_keys(permission_rows_df)
    pairs = {(int(row["sample_id"]), str(row["signal_key"])) for _, row in out.iterrows()}

    assert (1, "aosp_hidden_privileged") in pairs
    assert (2, "oem_vendor_ecosystem") in pairs


def test_build_signal_prevalence_by_type_separates_behavioral_and_model_only() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "banker", "rat"],
        }
    )
    signal_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "signal_key": ["sms", "app_defined_scaffolding", "launcher_sdk_ecosystem_noise"],
        }
    )
    out = report_stage._build_signal_prevalence_by_type(
        sample_core_df=sample_core_df,
        permission_signal_rows_df=signal_rows_df,
    )
    sms = out[(out["type_slug"] == "banker") & (out["signal_key"] == "sms")].iloc[0]
    scaffold = out[
        (out["type_slug"] == "banker")
        & (out["signal_key"] == "app_defined_scaffolding")
    ].iloc[0]
    assert bool(sms["include_in_behavioral_claims"]) is True
    assert bool(scaffold["include_in_model_features"]) is True
    assert bool(scaffold["include_in_behavioral_claims"]) is False
    assert {"pattern_level", "pattern_label", "pattern_basis", "pattern_reason"}.issubset(out.columns)


def test_build_signal_prevalence_by_family_marks_benchmark_eligibility() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 10, 10, 20],
            "family_canonical": ["Alpha", "Alpha", "Alpha", "Beta"],
            "type_slug": ["banker", "banker", "banker", "rat"],
            "category_primary": ["banker", "banker", "banker", "rat"],
            "category_subtype": ["", "", "", ""],
            "sample_label_kind": ["family_or_common_name"] * 4,
            "family_label_raw": ["Alpha", "Alpha", "Alpha", "Beta"],
            "vt_family_token": ["alpha", "alpha", "alpha", "beta"],
        }
    )
    signal_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "signal_key": ["sms", "sms", "app_defined_scaffolding", "sms"],
        }
    )
    out = report_stage._build_signal_prevalence_by_family(
        sample_core_df=sample_core_df,
        permission_signal_rows_df=signal_rows_df,
        benchmark_min_support=3,
    )
    alpha = out[(out["family_canonical"] == "Alpha") & (out["signal_key"] == "sms")].iloc[0]
    beta = out[(out["family_canonical"] == "Beta") & (out["signal_key"] == "sms")].iloc[0]
    assert bool(alpha["benchmark_eligible_n_ge_3"]) is True
    assert bool(beta["benchmark_eligible_n_ge_3"]) is False
    assert beta["pattern_label"] == "Trace Pattern"


def test_filter_behavior_safe_signals_excludes_model_only_rows() -> None:
    df = pd.DataFrame(
        {
            "signal_key": ["sms", "app_defined_scaffolding"],
            "include_in_behavioral_claims": [True, False],
            "prevalence_pct": [50.0, 75.0],
        }
    )
    out = report_stage._filter_behavior_safe_signals(df)

    assert out["signal_key"].tolist() == ["sms"]


def test_build_permission_signal_governance_coverage_counts_lane_presence() -> None:
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 1, 2],
            "permission_string": ["a", "b", "c"],
            "effective_source_family_key": ["oem_vendor_permission", "", ""],
            "candidate_source_family_key": ["", "needs_source_validation", ""],
            "effective_review_lane": ["", "", "source_validation_required"],
            "effective_resolution_semantics": ["x", "", ""],
        }
    )
    signal_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "signal_key": ["oem_vendor_ecosystem", "aosp_hidden_privileged"],
        }
    )

    out = report_stage._build_permission_signal_governance_coverage(
        permission_rows_df,
        signal_rows_df,
        run_id="r1",
    )
    metrics = dict(zip(out["metric"], out["value"]))

    assert metrics["permission_row_count"] == 3
    assert metrics["rows_with_effective_lane"] == 1
    assert metrics["rows_with_candidate_lane"] == 1
    assert metrics["rows_with_review_lane"] == 1
    assert metrics["rows_with_any_governance_lane"] == 3
    assert metrics["signal_assignment_pairs"] == 2


def test_family_support_distribution_uses_family_target_surface_and_marks_benchmark_eligibility() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 10, 10, -1],
            "family_canonical": ["Alpha", "Alpha", "Alpha", ""],
            "type_slug": ["banker", "banker", "banker", ""],
            "category_primary": ["banker", "banker", "banker", ""],
            "category_subtype": ["", "", "", ""],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name", "family_or_common_name", "hash_like"],
            "family_label_raw": ["Alpha", "Alpha", "Alpha", "unknown"],
            "vt_family_token": ["alpha", "alpha", "alpha", ""],
        }
    )

    out = report_stage._build_family_support_distribution(sample_core_df, run_id="r1")

    assert len(out) == 1
    row = out.iloc[0]
    assert row["family_canonical"] == "Alpha"
    assert bool(row["benchmark_eligible_n_ge_3"]) is True


def test_family_permission_profiles_include_type_and_benchmark_context(monkeypatch) -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_id": [10, 10, 10],
            "family_canonical": ["Alpha", "Alpha", "Alpha"],
            "type_slug": ["banker", "banker", "banker"],
            "category_primary": ["banker", "banker", "banker"],
            "category_subtype": ["", "", ""],
            "sample_label_kind": ["family_or_common_name"] * 3,
            "family_label_raw": ["Alpha", "Alpha", "Alpha"],
            "vt_family_token": ["alpha", "alpha", "alpha"],
        }
    )
    permission_matrix_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "android.permission.read_sms": [1, 1, 0],
        }
    )
    monkeypatch.setattr(report_stage, "_select_visual_families", lambda sample_core_df: ["Alpha"])

    profiles_df, entropy_df = report_stage._build_family_permission_profiles(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
        run_id="r1",
    )

    assert {"type_slug", "benchmark_eligible_n_ge_3"}.issubset(profiles_df.columns)
    assert {"type_slug", "benchmark_eligible_n_ge_3"}.issubset(entropy_df.columns)
    assert profiles_df["type_slug"].eq("banker").all()
    assert profiles_df["benchmark_eligible_n_ge_3"].astype(bool).all()
    assert {
        "pattern_score",
        "pattern_level",
        "pattern_label",
        "pattern_basis",
        "pattern_confidence",
        "pattern_reason",
    }.issubset(profiles_df.columns)
    assert set(profiles_df["pattern_basis"]) == {"RAW_PERMISSION+FAMILY_LEVEL"}


def test_build_permission_enrichment_outputs_expected_fields() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 10, 20, 20],
            "family_canonical": ["Alpha", "Alpha", "Beta", "Beta"],
            "type_slug": ["banker", "banker", "rat", "rat"],
            "category_primary": ["banker", "banker", "rat", "rat"],
            "category_subtype": ["", "", "", ""],
            "sample_label_kind": ["family_or_common_name"] * 4,
            "family_label_raw": ["Alpha", "Alpha", "Beta", "Beta"],
            "vt_family_token": ["alpha", "alpha", "beta", "beta"],
        }
    )
    permission_matrix_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "android.permission.read_sms": [1, 1, 0, 0],
            "android.permission.camera": [0, 0, 1, 1],
        }
    )

    type_out = report_stage._build_permission_type_enrichment(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
    )
    family_out = report_stage._build_permission_family_enrichment(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
        benchmark_min_support=3,
    )

    assert {"q_value_fdr", "interpretation_bucket", "odds_ratio"}.issubset(type_out.columns)
    assert {
        "q_value_fdr",
        "interpretation_bucket",
        "odds_ratio",
        "benchmark_eligible_n_ge_3",
    }.issubset(family_out.columns)
    assert {
        "pattern_score",
        "pattern_level",
        "pattern_label",
        "pattern_basis",
        "pattern_confidence",
        "pattern_reason",
    }.issubset(type_out.columns)
    assert {
        "pattern_score",
        "pattern_level",
        "pattern_label",
        "pattern_basis",
        "pattern_confidence",
        "pattern_reason",
    }.issubset(family_out.columns)


def test_permission_pattern_framework_emits_no_pattern_and_conflicting_evidence() -> None:
    no_pattern = perm_pattern_framework.classify_enrichment_pattern(
        subject_prevalence_pct=0.0,
        background_prevalence_pct=0.0,
        odds_ratio=1.0,
        q_value=1.0,
        support=12,
        basis="type_enrichment_vs_rest",
    )
    conflicting = perm_pattern_framework.classify_enrichment_pattern(
        subject_prevalence_pct=48.0,
        background_prevalence_pct=44.0,
        odds_ratio=1.08,
        q_value=0.41,
        support=12,
        basis="type_enrichment_vs_rest",
    )

    assert no_pattern["pattern_level"] == 0
    assert no_pattern["pattern_label"] == "Null / Absent Pattern"
    assert conflicting["pattern_level"] == 2
    assert conflicting["pattern_label"] == "Very Weak Pattern"


def test_permission_pattern_framework_caps_prevalence_only_strength_and_separates_confidence() -> None:
    out = perm_pattern_framework.classify_prevalence_pattern(
        prevalence_pct=100.0,
        positive_count=12,
        group_support=12,
        basis="permission_prevalence_by_type",
    )

    assert out["pattern_level"] == 6
    assert out["pattern_label"] == "Moderate-Strong Pattern"
    assert out["pattern_score"] == 100.0
    assert out["pattern_basis"] == "RAW_PERMISSION+TYPE_LEVEL"
    assert out["pattern_confidence"] == "high"
    assert "capped" in out["pattern_reason"]


def test_permission_pattern_framework_keeps_small_support_prevalence_confidence_below_high() -> None:
    out = perm_pattern_framework.classify_prevalence_pattern(
        prevalence_pct=100.0,
        positive_count=3,
        group_support=3,
        basis="signal_prevalence_by_family",
    )

    assert out["pattern_level"] == 6
    assert out["pattern_basis"] == "PERMISSION_GROUP+FAMILY_LEVEL"
    assert out["pattern_confidence"] in {"moderate", "low", "very_low"}


def test_type_capability_bundle_prevalence_carries_pattern_contract() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "banker", "rat"],
        }
    )
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "permission_string": [
                "android.permission.read_sms",
                "android.permission.receive_sms",
                "android.permission.internet",
            ],
        }
    )

    out = report_stage._build_type_capability_bundle_prevalence(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        run_id="r1",
    )

    assert {
        "pattern_score",
        "pattern_level",
        "pattern_label",
        "pattern_basis",
        "pattern_confidence",
        "pattern_reason",
    }.issubset(out.columns)
    assert set(out["pattern_basis"]) == {"CAPABILITY+TYPE_LEVEL"}


def test_family_capability_bundle_profiles_carry_pattern_contract(monkeypatch) -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_id": [10, 10, 10],
            "family_canonical": ["Alpha", "Alpha", "Alpha"],
            "type_slug": ["banker", "banker", "banker"],
            "category_primary": ["banker", "banker", "banker"],
            "category_subtype": ["", "", ""],
            "sample_label_kind": ["family_or_common_name"] * 3,
            "family_label_raw": ["Alpha", "Alpha", "Alpha"],
            "vt_family_token": ["alpha", "alpha", "alpha"],
        }
    )
    permission_rows_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "permission_string": [
                "android.permission.read_sms",
                "android.permission.receive_sms",
            ],
        }
    )
    monkeypatch.setattr(report_stage, "_select_visual_families", lambda sample_core_df: ["Alpha"])
    out = report_stage._build_family_capability_bundle_profiles(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        run_id="r1",
    )

    assert {
        "pattern_score",
        "pattern_level",
        "pattern_label",
        "pattern_basis",
        "pattern_confidence",
        "pattern_reason",
    }.issubset(out.columns)
    assert set(out["pattern_basis"]) == {"CAPABILITY+FAMILY_LEVEL"}


def test_export_permission_pattern_summary_mentions_required_sections(tmp_path: Path) -> None:
    prevalence_by_type_df = pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "permission": "android.permission.read_sms",
                "n_samples": 5,
                "permission_positive_count": 4,
                "prevalence_pct": 80.0,
            }
        ]
    )
    prevalence_by_family_df = pd.DataFrame(
        [
            {
                "family_canonical": "Alpha",
                "type_slug": "banker",
                "family_support": 5,
                "permission": "android.permission.read_sms",
                "positive_count": 4,
                "prevalence_pct": 80.0,
                "benchmark_eligible_n_ge_3": True,
            },
            {
                "family_canonical": "Tiny",
                "type_slug": "banker",
                "family_support": 2,
                "permission": "android.permission.read_sms",
                "positive_count": 1,
                "prevalence_pct": 50.0,
                "benchmark_eligible_n_ge_3": False,
            },
        ]
    )
    signal_prevalence_by_type_df = pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "signal_key": "sms",
                "signal_label": "SMS",
                "authority_lane": "behavior_safe_capability",
                "include_in_model_features": True,
                "include_in_behavioral_claims": True,
                "type_sample_count": 5,
                "positive_count": 4,
                "prevalence_pct": 80.0,
            },
            {
                "type_slug": "banker",
                "signal_key": "app_defined_scaffolding",
                "signal_label": "App-Defined Scaffolding",
                "authority_lane": "app_scaffolding",
                "include_in_model_features": True,
                "include_in_behavioral_claims": False,
                "type_sample_count": 5,
                "positive_count": 2,
                "prevalence_pct": 40.0,
            },
        ]
    )
    signal_prevalence_by_family_df = pd.DataFrame(
        [
            {
                "family_canonical": "Alpha",
                "type_slug": "banker",
                "family_support": 5,
                "benchmark_eligible_n_ge_3": True,
                "signal_key": "sms",
                "signal_label": "SMS",
                "authority_lane": "behavior_safe_capability",
                "include_in_model_features": True,
                "include_in_behavioral_claims": True,
                "positive_count": 4,
                "prevalence_pct": 80.0,
            }
        ]
    )
    type_enrichment_df = pd.DataFrame(
        [
            {
                "permission": "android.permission.read_sms",
                "type_slug": "banker",
                "type_prevalence_pct": 80.0,
                "non_type_prevalence_pct": 10.0,
                "odds_ratio": 5.0,
                "p_value": 0.001,
                "q_value_fdr": 0.005,
                "interpretation_bucket": "strong_enriched",
            }
        ]
    )
    family_enrichment_df = pd.DataFrame(
        [
            {
                "permission": "android.permission.read_sms",
                "family_canonical": "Alpha",
                "type_slug": "banker",
                "family_support": 5,
                "family_prevalence_pct": 80.0,
                "non_family_prevalence_pct": 10.0,
                "odds_ratio": 5.0,
                "p_value": 0.001,
                "q_value_fdr": 0.005,
                "benchmark_eligible_n_ge_3": True,
                "interpretation_bucket": "strong_enriched",
            }
        ]
    )
    family_similarity_df = pd.DataFrame(
        [
            {
                "family_a": "Alpha",
                "family_b": "Beta",
                "type_a": "banker",
                "type_b": "banker",
                "support_a": 5,
                "support_b": 4,
                "jaccard_similarity": 0.8,
                "cosine_similarity": 0.9,
                "spearman_correlation": 0.7,
                "same_type_flag": True,
            }
        ]
    )
    family_signal_similarity_df = pd.DataFrame(
        [
            {
                "family_a": "Alpha",
                "family_b": "Beta",
                "type_a": "banker",
                "type_b": "banker",
                "support_a": 5,
                "support_b": 4,
                "jaccard_similarity": 1.0,
                "cosine_similarity": 1.0,
                "spearman_correlation": 1.0,
                "same_type_flag": True,
            }
        ]
    )
    signal_governance_coverage_df = pd.DataFrame(
        [
            {"metric": "permission_row_count", "value": 25},
            {"metric": "rows_with_any_governance_lane", "value": 24},
            {"metric": "rows_with_effective_lane", "value": 22},
            {"metric": "rows_with_candidate_lane", "value": 3},
            {"metric": "signal_assignment_pairs", "value": 10},
        ]
    )
    attack_hypotheses_df = pd.DataFrame(
        [
            {
                "group_kind": "type",
                "group_value": "banker",
                "attack_id": "T1636.004",
                "attack_name": "Protected User Data: SMS Messages",
                "confidence": "direct",
                "matched_permission_count": 2,
            }
        ]
    )
    generic_summary_df = pd.DataFrame(
        [
            {
                "group": "generic_or_coarse",
                "sample_count": 10,
                "permission_entropy_mean": 1.2,
                "dangerous_count_strict_mean": 2.5,
            }
        ]
    )
    temporal_pattern_df = pd.DataFrame(
        [
            {
                "period_quarter": "2025-Q2",
                "permission": "android.permission.read_sms",
                "prevalence_pct": 80.0,
                "banker_sample_count": 5,
                "pattern_label": "Moderate Pattern",
                "pattern_confidence": "moderate",
            }
        ]
    )

    out = perm_bundle_exports.export_permission_pattern_summary(
        run_id="r1",
        bundle_dir=tmp_path,
        prevalence_by_type_df=prevalence_by_type_df,
        prevalence_by_family_df=prevalence_by_family_df,
        signal_prevalence_by_type_df=signal_prevalence_by_type_df,
        signal_prevalence_by_type_behavior_safe_df=signal_prevalence_by_type_df[
            signal_prevalence_by_type_df["include_in_behavioral_claims"].astype(bool)
        ].copy(),
        signal_prevalence_by_family_df=signal_prevalence_by_family_df,
        signal_prevalence_by_family_behavior_safe_df=signal_prevalence_by_family_df[
            signal_prevalence_by_family_df["include_in_behavioral_claims"].astype(bool)
        ].copy(),
        family_signal_similarity_df=family_signal_similarity_df,
        family_signal_similarity_behavior_safe_df=family_signal_similarity_df.copy(),
        signal_governance_coverage_df=signal_governance_coverage_df,
        type_enrichment_df=type_enrichment_df,
        family_enrichment_df=family_enrichment_df,
        family_similarity_df=family_similarity_df,
        attack_hypotheses_df=attack_hypotheses_df,
        generic_summary_df=generic_summary_df,
        temporal_pattern_df=temporal_pattern_df,
    )

    text = Path(out).read_text(encoding="utf-8")
    assert "Broad corpus signal" in text
    assert "Type-level signal" in text
    assert "Signal-group interpretation" in text
    assert "Governance coverage" in text
    assert "These counts describe how much of the permission surface carried live governance lane metadata" in text
    assert "Benchmark-eligible family signal" in text
    assert "Secondary mixed-signal family groups" in text
    assert "Top benchmark-eligible behavior-safe family signal groups" in text
    assert "Temporal banker permission signals" in text
    assert "Latest-quarter banker permission patterns" in text
    assert "Family-within-type clusters" in text
    assert "Secondary mixed-signal family signal-group pairs" in text
    assert "Closest same-type behavior-safe family signal-group pairs" in text
    assert "Exclusions and caution lanes" in text
    assert "Treat behavior-safe signal tables as the primary interpretation surface" in text
    assert "Taxonomy anomalies" in text
    assert "Candidate MITRE ATT&CK capability hypothesis mappings" in text
    assert "permission-derived capability hypotheses only" in text.lower()
    assert "static declared-capability signals" in text


@pytest.mark.heavy
def test_export_banker_trends_line_plot_latest_only_when_run_scoped_disabled(
    monkeypatch,
    tmp_path: Path,
):
    pytest.importorskip("matplotlib")
    trends_df = pd.DataFrame(
        {
            "period_quarter": ["2025Q1", "2025Q2"],
            "banker_sample_count": [10, 12],
            "banker_bind_accessibility_service_prevalence": [0.10, 0.12],
            "banker_system_alert_window_prevalence": [0.15, 0.18],
            "banker_request_install_packages_prevalence": [0.08, 0.11],
            "banker_read_sms_prevalence": [0.25, 0.27],
            "banker_receive_sms_prevalence": [0.22, 0.21],
            "banker_send_sms_prevalence": [0.30, 0.33],
        }
    )
    monkeypatch.setattr(perm_trends_reporting_support, "write_run_scoped_permission_artifacts", lambda: False)

    out = report_stage._export_banker_trends_line_plot(
        trends_df=trends_df,
        run_id="r123",
        bundle_dir=tmp_path,
    )

    assert out is not None
    assert Path(out).name == "banker_permission_trends_over_time.latest.png"
    assert (tmp_path / "figures" / "banker_permission_trends_over_time.latest.png").exists()
    assert not (tmp_path / "figures" / "banker_permission_trends_over_time_r123.png").exists()


@pytest.mark.heavy
def test_export_banker_trends_line_plot_writes_run_scoped_when_enabled(
    monkeypatch,
    tmp_path: Path,
):
    pytest.importorskip("matplotlib")
    trends_df = pd.DataFrame(
        {
            "period_quarter": ["2025Q1", "2025Q2"],
            "banker_sample_count": [10, 12],
            "banker_bind_accessibility_service_prevalence": [0.10, 0.12],
            "banker_system_alert_window_prevalence": [0.15, 0.18],
            "banker_request_install_packages_prevalence": [0.08, 0.11],
            "banker_read_sms_prevalence": [0.25, 0.27],
            "banker_receive_sms_prevalence": [0.22, 0.21],
            "banker_send_sms_prevalence": [0.30, 0.33],
        }
    )
    monkeypatch.setattr(perm_trends_reporting_support, "write_run_scoped_permission_artifacts", lambda: True)

    out = report_stage._export_banker_trends_line_plot(
        trends_df=trends_df,
        run_id="r123",
        bundle_dir=tmp_path,
    )

    assert out is not None
    assert Path(out).name == "banker_permission_trends_over_time_r123.png"
    assert (tmp_path / "figures" / "banker_permission_trends_over_time.latest.png").exists()
    assert (tmp_path / "figures" / "banker_permission_trends_over_time_r123.png").exists()


def test_prune_run_stamped_pngs_in_latest_bundle_removes_legacy_files(tmp_path: Path):
    bundle_dir = tmp_path / "paper_bundle_latest" / "permission_trends"
    bundle_dir.mkdir(parents=True)
    stale = bundle_dir / "type_permission_heatmap_20260303T153540Z__90e82c.png"
    keep = bundle_dir / "type_permission_heatmap.latest.png"
    stale.write_bytes(b"stale")
    keep.write_bytes(b"latest")

    removed = report_stage._prune_run_stamped_pngs_in_latest_bundle(bundle_dir)  # pylint: disable=protected-access

    assert str(stale) in removed
    assert not stale.exists()
    assert keep.exists()


def test_prune_run_stamped_pngs_skips_run_scoped_bundle(tmp_path: Path):
    bundle_dir = tmp_path / "paper_bundle_20260303T153540Z__90e82c" / "permission_trends"
    bundle_dir.mkdir(parents=True)
    stale = bundle_dir / "figures" / "type_permission_heatmap_20260303T153540Z__90e82c.png"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"stale")

    removed = report_stage._prune_run_stamped_pngs_in_latest_bundle(bundle_dir)  # pylint: disable=protected-access

    assert str(stale) in removed
    assert not stale.exists()


def test_publish_canonical_type_heatmap_writes_run_and_latest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(report_stage.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(
        report_stage.app_config,
        "ENABLE_LEGACY_CANONICAL_HEATMAP_EXPORT",
        True,
        raising=False,
    )
    src = tmp_path / "paper_bundle_latest" / "permission_trends" / "type_permission_heatmap.latest.png"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"png")

    out = report_stage._publish_canonical_type_heatmap(  # pylint: disable=protected-access
        source_path=str(src),
        run_id="20260303T153540Z__90e82c",
        cohort_hash="cohort123",
        permission_feature_hash="feature123",
        type_heatmap_identity="identity123",
    )

    run_path = tmp_path / "runs" / "20260303T153540Z__90e82c" / "paper" / "type_permission_heatmap.png"
    latest_path = tmp_path / "latest" / "type_permission_heatmap.png"
    identity_path = tmp_path / "latest" / "type_permission_heatmap.identity.json"
    assert str(run_path) in out
    assert str(latest_path) in out
    assert str(identity_path) in out
    assert run_path.exists()
    assert latest_path.exists()
    assert identity_path.exists()


def test_publish_canonical_type_heatmap_disabled_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(report_stage.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(
        report_stage.app_config,
        "ENABLE_LEGACY_CANONICAL_HEATMAP_EXPORT",
        False,
        raising=False,
    )
    src = tmp_path / "permission_trends" / "type_permission_heatmap.latest.png"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"png")

    out = report_stage._publish_canonical_type_heatmap(  # pylint: disable=protected-access
        source_path=str(src),
        run_id="r1",
        cohort_hash="c",
        permission_feature_hash="p",
        type_heatmap_identity="i",
    )
    assert out == []


def test_export_helpers_write_to_grouped_subfolders(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(perm_trends_reporting_support, "write_run_scoped_permission_artifacts", lambda: False)
    df = pd.DataFrame({"a": [1]})
    csv_out = report_stage._export_df_with_latest(  # pylint: disable=protected-access
        df=df,
        run_id="r1",
        file_stem="sample_table",
        bundle_dir=tmp_path,
    )
    json_out = report_stage._export_json_with_latest(  # pylint: disable=protected-access
        payload={"x": 1},
        run_id="r1",
        file_stem="sample_contract",
        bundle_dir=tmp_path,
    )
    txt_out = report_stage._export_text_with_latest(  # pylint: disable=protected-access
        text="ok",
        run_id="r1",
        file_stem="sample_doc",
        bundle_dir=tmp_path,
    )

    assert Path(csv_out).parent.name == "tables"
    assert Path(json_out).parent.name == "contracts"
    assert Path(txt_out).parent.name == "docs"


def test_resolve_permission_bundle_dir_defaults_to_module_root(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(report_stage.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(report_stage.app_config, "RUNTIME_RUN_ROOT", "", raising=False)

    out = report_stage._resolve_permission_bundle_dir("run123")  # pylint: disable=protected-access

    assert out == tmp_path / "runs" / "run123" / "bundles" / "permission_trends"
    assert "paper_bundle_latest" not in str(out)


def test_resolve_permission_bundle_dir_prefers_runtime_run_root(monkeypatch, tmp_path: Path):
    run_root = tmp_path / "runs" / "run123"
    monkeypatch.setattr(report_stage.app_config, "DEFAULT_OUTPUT_DIR", str(run_root), raising=False)
    monkeypatch.setattr(report_stage.app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)

    out = report_stage._resolve_permission_bundle_dir("run123")  # pylint: disable=protected-access

    assert out == run_root / "bundles" / "permission_trends"


def test_copy_permission_bundle_to_latest_creates_latest_copy(monkeypatch, tmp_path: Path):
    source = tmp_path / "runs" / "run123" / "bundles" / "permission_trends"
    source.mkdir(parents=True, exist_ok=True)
    (source / "tables").mkdir(parents=True, exist_ok=True)
    (source / "tables" / "x.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.setattr(report_stage.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(report_stage.app_config, "ENABLE_PERMISSION_TRENDS_LATEST_MIRROR", True, raising=False)

    latest = report_stage._copy_permission_bundle_to_latest(source)  # pylint: disable=protected-access

    assert latest is not None
    assert latest == tmp_path / "bundles" / "latest" / "permission_trends"
    assert (latest / "tables" / "x.csv").exists()


def test_select_discriminative_permissions_orders_by_rank():
    df = pd.DataFrame(
        {
            "permission": ["p1", "p2", "p3"],
            "cramers_v": [0.10, 0.30, 0.20],
            "mutual_information": [0.2, 0.1, 0.4],
        }
    )

    out = report_stage._select_discriminative_permissions(df, top_k=2)  # pylint: disable=protected-access

    assert out == ["p2", "p3"]


def test_select_dangerous_permissions_for_heatmap_uses_prevalence_order():
    permission_rows = pd.DataFrame(
        {
            "permission_string": ["p1", "p2", "p3"],
            "protection_level": ["dangerous", "DANGEROUS", "normal"],
        }
    )
    prevalence = pd.DataFrame(
        {
            "permission": ["p1", "p2", "p1", "p2"],
            "prevalence": [0.2, 0.9, 0.3, 0.8],
        }
    )

    out = report_stage._select_dangerous_permissions_for_heatmap(  # pylint: disable=protected-access
        permission_rows_df=permission_rows,
        type_prevalence_df=prevalence,
        top_k=2,
    )

    assert out == ["p2", "p1"]


def test_build_permission_trends_layout_check_warns_on_timestamped_png(tmp_path: Path):
    bundle_dir = tmp_path / "permission_trends"
    (bundle_dir / "figures").mkdir(parents=True)
    (bundle_dir / "tables").mkdir(parents=True)
    (bundle_dir / "contracts").mkdir(parents=True)
    (bundle_dir / "docs").mkdir(parents=True)
    (bundle_dir / "figures" / "type_permission_heatmap.latest.png").write_bytes(b"ok")
    (bundle_dir / "figures" / "type_permission_heatmap_20260303T153540Z__90e82c.png").write_bytes(b"old")

    out = report_stage._build_permission_trends_layout_check(bundle_dir=bundle_dir)  # pylint: disable=protected-access

    assert out["status"] == "WARN"
    assert out["timestamped_png_in_latest_count"] == 1


def test_export_permission_trends_bundle_manifest_writes_contract_payload(tmp_path: Path):
    bundle_dir = tmp_path / "permission_trends"
    figures = bundle_dir / "figures"
    tables = bundle_dir / "tables"
    contracts = bundle_dir / "contracts"
    for path in (figures, tables, contracts):
        path.mkdir(parents=True, exist_ok=True)
    fig_path = figures / "family_jsd_heatmap_top12.latest.png"
    tbl_path = tables / "dangerous_distribution_by_type.latest.csv"
    capability_path = tables / "type_capability_bundle_prevalence.latest.csv"
    fig_path.write_bytes(b"png")
    tbl_path.write_text("a,b\n1,2\n", encoding="utf-8")
    capability_path.write_text("a,b\n1,2\n", encoding="utf-8")
    signal_path = tables / "permission_signal_prevalence_by_type.latest.csv"
    signal_behavior_safe_path = tables / "permission_signal_prevalence_by_type_behavior_safe.latest.csv"
    signal_path.write_text("a,b\n1,2\n", encoding="utf-8")
    signal_behavior_safe_path.write_text("a,b\n1,2\n", encoding="utf-8")

    out = report_stage._export_permission_trends_bundle_manifest(  # pylint: disable=protected-access
        run_id="r1",
        bundle_dir=bundle_dir,
        top_families_visual=12,
        min_visual_family_support=20,
        top_permissions=16,
        artifact_paths=[
            str(fig_path),
            str(tbl_path),
            str(capability_path),
            str(signal_path),
            str(signal_behavior_safe_path),
        ],
    )

    payload = json.loads(Path(out).read_text(encoding="utf-8"))
    assert payload["bundle_contract_name"] == "permission_trends"
    assert payload["bundle_contract_version"] == "v1"
    assert len(payload["artifacts"]) == 5
    ids = {row["artifact_id"] for row in payload["artifacts"]}
    assert "family_jsd_heatmap_top12" in ids
    assert "dangerous_permission_distribution_by_type" in ids
    assert "type_capability_bundle_prevalence" in ids
    mixed = next(row for row in payload["artifacts"] if row["artifact_id"] == "permission_signal_prevalence_by_type")
    safe = next(
        row for row in payload["artifacts"] if row["artifact_id"] == "permission_signal_prevalence_by_type_behavior_safe"
    )
    assert mixed["interpretation_surface"] == "mixed_signal_secondary"
    assert mixed["preferred_behavior_claim_artifact_id"] == "permission_signal_prevalence_by_type_behavior_safe"
    assert safe["interpretation_surface"] == "behavior_safe_primary"
    assert safe["preferred_behavior_claim_artifact_id"] == "permission_signal_prevalence_by_type_behavior_safe"


def test_build_bundle_metadata_includes_attack_mapping_and_capability_bundle_contract() -> None:
    sample_core_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "vt_first_seen_itw_date": ["2025-01-01T00:00:00Z", "2025-03-01T00:00:00Z"],
            "vt_first_submission_at_utc": ["2025-01-01T00:00:00Z", "2025-03-01T00:00:00Z"],
        }
    )
    coverage_df = pd.DataFrame([{"sample_count": 2, "pct_with_permission_rows": 1.0}])
    consensus_df = pd.DataFrame([{"low_vendor_count_flag": 0}, {"low_vendor_count_flag": 1}])
    family_support_df = pd.DataFrame(
        {
            "support_ge_50_flag": [0, 1],
            "support_ge_30_flag": [1, 1],
        }
    )

    out = report_stage._build_bundle_metadata(
        run_id="r1",
        profile_id="android_malware_all_current",
        sample_core_df=sample_core_df,
        coverage_df=coverage_df,
        consensus_df=consensus_df,
        family_support_df=family_support_df,
        selected_vendors=["vendor_a"],
        engine_included_count=5,
        engine_excluded_count=2,
        permission_support_floor=50,
        kept_permission_count=12,
        kept_permissions_by_view={"inclusive": ["a", "b"], "aosp_only": ["a"], "ecosystem": ["a", "b", "c"]},
        analysis_scope="all",
        figure_mode="paper",
        cohort_hash="cohort_hash",
        permission_feature_hash="perm_hash",
        type_heatmap_identity="heatmap_hash",
        dataset_time_contract={},
    )

    policy = out["permission_pattern_policy"]
    assert "capability_bundle_names" in policy
    assert "sms_telephony" in policy["capability_bundle_names"]
    assert int(policy["capability_bundle_rule_count"]) > 0
    assert str(policy["attack_mobile_mapping_version"]).strip()
    assert str(policy["attack_mobile_mapping_hash"]).strip()


def test_export_permission_trends_table_inventory_from_manifest(tmp_path: Path):
    bundle_dir = tmp_path / "permission_trends"
    contracts = bundle_dir / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    manifest_path = contracts / "permission_trends_bundle_manifest.json"
    payload = {
        "artifacts": [
            {
                "artifact_id": "dangerous_permission_distribution_by_type",
                "category": "table",
                "filename": "dangerous_distribution_by_type.latest.csv",
                "role": "primary_structural",
                "is_primary": True,
                "used_by": "paper,bundle_only,backfill",
                "keep_in_permission_trends": "yes",
                "target_location": "bundles/permission_trends/tables/csv/primary",
                "needs_latex_export": "yes",
                "interpretation_surface": "not_applicable",
                "preferred_behavior_claim_artifact_id": "",
                "notes": "Primary structural table.",
            }
        ]
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    out = report_stage._export_permission_trends_table_inventory_from_manifest(  # pylint: disable=protected-access
        bundle_dir=bundle_dir,
        run_id="r1",
        manifest_path=str(manifest_path),
    )

    out_df = pd.read_csv(Path(out))
    assert out_df.iloc[0]["artifact_id"] == "dangerous_permission_distribution_by_type"
    assert out_df.iloc[0]["needs_latex_export"] == "yes"
    assert out_df.iloc[0]["interpretation_surface"] == "not_applicable"
    assert str(out_df.iloc[0]["preferred_behavior_claim_artifact_id"]) in {"", "nan"}


def test_export_permission_trends_bundle_readme_writes_scope_notes(tmp_path: Path):
    bundle_dir = tmp_path / "permission_trends"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    out = report_stage._export_permission_trends_bundle_readme(  # pylint: disable=protected-access
        run_id="r2",
        bundle_dir=bundle_dir,
    )

    readme = Path(out)
    assert readme.exists()
    text = readme.read_text(encoding="utf-8")
    assert "Permission Trends Bundle" in text
    assert "paper_exports/: strict paper subset" in text


def test_export_jsd_pair_verification_writes_bundle_pair_table(tmp_path: Path):
    jsd_df = pd.DataFrame(
        {
            "run_id": ["r1", "r1", "r1", "r1"],
            "family_canonical": ["a", "b", "a", "b"],
            "other": ["a", "a", "b", "b"],
            "js_distance": [0.0, 0.2, 0.2, 0.0],
        }
    )
    bundle_dir = tmp_path / "permission_trends"
    (bundle_dir / "tables").mkdir(parents=True, exist_ok=True)

    out = report_stage._export_jsd_pair_verification(  # pylint: disable=protected-access
        jsd_df=jsd_df,
        run_id="r1",
        bundle_dir=bundle_dir,
        file_stem="family_jsd_pairs_top12",
    )

    assert out is not None
    pair_path = bundle_dir / "tables" / "family_jsd_pairs_top12.latest.csv"
    assert pair_path.exists()


def test_normalize_analysis_scope_defaults_to_all(monkeypatch):
    monkeypatch.setattr(report_stage.app_config, "ANALYSIS_SCOPE", "bad_value", raising=False)
    out = report_stage._normalize_analysis_scope()  # pylint: disable=protected-access
    assert out == "all"


def test_filter_type_prevalence_for_visuals_excludes_unknown(monkeypatch):
    monkeypatch.setattr(report_stage.app_config, "EXCLUDE_UNKNOWN_TYPE_IN_VISUALS", True, raising=False)
    df = pd.DataFrame(
        {
            "type_slug": ["banker", "unknown"],
            "permission": ["p1", "p1"],
            "prevalence": [0.9, 0.4],
        }
    )
    out = report_stage._filter_type_prevalence_for_visuals(df)  # pylint: disable=protected-access
    assert out["type_slug"].tolist() == ["banker"]


def test_select_visual_families_applies_support_threshold(monkeypatch):
    monkeypatch.setattr(report_stage.app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 3, raising=False)
    monkeypatch.setattr(report_stage.app_config, "MAX_FAMILY_VISUAL_COUNT", 2, raising=False)
    sample_core_df = pd.DataFrame(
        {
            "family_canonical": ["a", "a", "a", "b", "b", "c"],
        }
    )
    out = report_stage._select_visual_families(sample_core_df)  # pylint: disable=protected-access
    assert out == ["a"]


def test_select_visual_families_breaks_ties_deterministically(monkeypatch):
    monkeypatch.setattr(report_stage.app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 2, raising=False)
    monkeypatch.setattr(report_stage.app_config, "MAX_FAMILY_VISUAL_COUNT", 2, raising=False)
    sample_core_df = pd.DataFrame(
        {
            "family_canonical": ["b", "b", "a", "a", "c"],
        }
    )
    out = report_stage._select_visual_families(sample_core_df)  # pylint: disable=protected-access
    assert out == ["a", "b"]


def test_bundle_manifest_canonical_artifact_id_strips_run_stamp_for_signal_tables() -> None:
    path = Path("permission_signal_prevalence_by_type_20260601T164351Z__fe432f.csv")

    artifact_id = perm_bundle_manifest.canonical_bundle_artifact_id_from_path(
        path,
        category="table",
    )
    role, is_primary = perm_bundle_manifest.bundle_artifact_role(artifact_id, "table")
    policy = perm_bundle_manifest.bundle_table_policy(artifact_id)

    assert artifact_id == "permission_signal_prevalence_by_type"
    assert role == "auxiliary_table"
    assert is_primary is False
    assert "should not be the default surface for behavior claims" in policy["notes"]


def test_bundle_manifest_behavior_safe_signal_table_is_primary_structural() -> None:
    path = Path("permission_signal_prevalence_by_type_behavior_safe_20260601T164351Z__fe432f.csv")

    artifact_id = perm_bundle_manifest.canonical_bundle_artifact_id_from_path(
        path,
        category="table",
    )
    role, is_primary = perm_bundle_manifest.bundle_artifact_role(artifact_id, "table")
    policy = perm_bundle_manifest.bundle_table_policy(artifact_id)

    assert artifact_id == "permission_signal_prevalence_by_type_behavior_safe"
    assert role == "primary_structural"
    assert is_primary is True
    assert policy["notes"] == "Primary structural table."


def test_bundle_manifest_temporal_pattern_table_is_primary_structural() -> None:
    path = Path("banker_permission_trend_patterns_20260601T164351Z__fe432f.csv")

    artifact_id = perm_bundle_manifest.canonical_bundle_artifact_id_from_path(
        path,
        category="table",
    )
    role, is_primary = perm_bundle_manifest.bundle_artifact_role(artifact_id, "table")
    policy = perm_bundle_manifest.bundle_table_policy(artifact_id)

    assert artifact_id == "banker_permission_trend_patterns"
    assert role == "primary_structural"
    assert is_primary is True
    assert policy["notes"] == "Primary structural table."


def test_bundle_manifest_signal_tables_publish_behavior_claim_preference_metadata() -> None:
    mixed_id = "family_signal_similarity"
    safe_id = "family_signal_similarity_behavior_safe"

    assert perm_bundle_manifest.interpretation_surface(mixed_id) == "mixed_signal_secondary"
    assert perm_bundle_manifest.preferred_behavior_claim_artifact_id(mixed_id) == safe_id
    assert perm_bundle_manifest.interpretation_surface(safe_id) == "behavior_safe_primary"
    assert perm_bundle_manifest.preferred_behavior_claim_artifact_id(safe_id) == safe_id


def test_bundle_artifact_entry_prefers_behavior_safe_replacement() -> None:
    manifest = {
        "artifacts": [
            {
                "artifact_id": "permission_signal_prevalence_by_type",
                "relative_path": "tables/permission_signal_prevalence_by_type.latest.csv",
                "preferred_behavior_claim_artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
            },
            {
                "artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
                "relative_path": "tables/permission_signal_prevalence_by_type_behavior_safe.latest.csv",
                "preferred_behavior_claim_artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
            },
        ]
    }

    direct = perm_bundle_manifest.bundle_artifact_entry(
        manifest,
        "permission_signal_prevalence_by_type",
        prefer_behavior_claim_surface=False,
    )
    preferred = perm_bundle_manifest.bundle_artifact_entry(
        manifest,
        "permission_signal_prevalence_by_type",
        prefer_behavior_claim_surface=True,
    )

    assert direct is not None
    assert preferred is not None
    assert direct["artifact_id"] == "permission_signal_prevalence_by_type"
    assert preferred["artifact_id"] == "permission_signal_prevalence_by_type_behavior_safe"


def test_resolve_bundle_artifact_path_prefers_behavior_safe_replacement(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "permission_trends"
    tables = bundle_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    mixed_path = tables / "permission_signal_prevalence_by_type.latest.csv"
    safe_path = tables / "permission_signal_prevalence_by_type_behavior_safe.latest.csv"
    mixed_path.write_text("x\n", encoding="utf-8")
    safe_path.write_text("x\n", encoding="utf-8")
    manifest = {
        "artifacts": [
            {
                "artifact_id": "permission_signal_prevalence_by_type",
                "relative_path": "tables/permission_signal_prevalence_by_type.latest.csv",
                "preferred_behavior_claim_artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
            },
            {
                "artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
                "relative_path": "tables/permission_signal_prevalence_by_type_behavior_safe.latest.csv",
                "preferred_behavior_claim_artifact_id": "permission_signal_prevalence_by_type_behavior_safe",
            },
        ]
    }

    direct = perm_bundle_manifest.resolve_bundle_artifact_path(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="permission_signal_prevalence_by_type",
        prefer_behavior_claim_surface=False,
    )
    preferred = perm_bundle_manifest.resolve_bundle_artifact_path(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="permission_signal_prevalence_by_type",
        prefer_behavior_claim_surface=True,
    )

    assert direct == mixed_path.resolve()
    assert preferred == safe_path.resolve()
