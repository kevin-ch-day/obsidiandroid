import pandas as pd
import pytest
import json
from pathlib import Path

from obsidiandroid.pipeline import stage_permission_trends_report as report_stage
from obsidiandroid.pipeline.permission_trends import sample_permission_data as sample_perm_data
from obsidiandroid.pipeline.permission_trends import reporting_support as perm_trends_reporting_support


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
    monkeypatch.setattr(sample_perm_data, "_PERMISSION_OBS_NORM_AVAILABLE", None)
    monkeypatch.setattr(
        sample_perm_data.db_engine,
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


def test_fetch_permission_rows_for_samples_falls_back_without_norm(monkeypatch) -> None:
    monkeypatch.setattr(sample_perm_data, "_PERMISSION_OBS_NORM_AVAILABLE", None)
    monkeypatch.setattr(
        sample_perm_data.db_engine,
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

    assert "permission_string_norm" not in str(captured.get("query", ""))
    assert "LOWER(TRIM(ops.permission_string)) AS permission_string" in str(captured.get("query", ""))
    assert out["permission_string"].tolist() == ["android.permission.read_sms"]


def test_fetch_permission_aggregates_prefers_permission_string_norm(monkeypatch) -> None:
    monkeypatch.setattr(sample_perm_data, "_PERMISSION_OBS_NORM_AVAILABLE", None)
    monkeypatch.setattr(
        sample_perm_data.db_engine,
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
    fig_path.write_bytes(b"png")
    tbl_path.write_text("a,b\n1,2\n", encoding="utf-8")

    out = report_stage._export_permission_trends_bundle_manifest(  # pylint: disable=protected-access
        run_id="r1",
        bundle_dir=bundle_dir,
        top_families_visual=12,
        min_visual_family_support=20,
        top_permissions=16,
        artifact_paths=[str(fig_path), str(tbl_path)],
    )

    payload = json.loads(Path(out).read_text(encoding="utf-8"))
    assert payload["bundle_contract_name"] == "permission_trends"
    assert payload["bundle_contract_version"] == "v1"
    assert len(payload["artifacts"]) == 2
    ids = {row["artifact_id"] for row in payload["artifacts"]}
    assert "family_jsd_heatmap_top12" in ids
    assert "dangerous_permission_distribution_by_type" in ids


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
