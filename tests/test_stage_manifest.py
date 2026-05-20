"""Tests for run manifest stage helper module."""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.pipeline import stage_manifest
from obsidiandroid.pipeline.manifest import paper_compliance_checks
from obsidiandroid.pipeline.manifest import stage_manifest_evidence_pack as evidence_pack

build_paper_compliance_checks = paper_compliance_checks.build_paper_compliance_checks


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload))


def _seed_confusion_provenance_artifacts(
    run_root: Path,
    run_id: str,
    *,
    samples_tested: int,
) -> tuple[Path, Path, Path]:
    diagnostics_dir = run_root / "diagnostics"
    cm_dir = run_root / "conf_matrices"
    model_dir = run_root / "models" / "random_forest"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    cm_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    (cm_dir / "confusion_matrix_primary.png").write_bytes(b"png")
    _write_json(
        model_dir / "random_forest_classifier_model_metadata.json",
        {"evaluation": {"samples_tested": samples_tested}},
    )
    return diagnostics_dir, cm_dir, model_dir


def _seed_strict_paper2_inputs(
    run_root: Path,
    run_id: str,
    *,
    family_count: int = 12,
    run_scoped_names: bool = False,
    include_type_heatmap: bool = True,
    include_jsd_pairs: bool = True,
    use_single_family_pair: bool = False,
) -> Path:
    diagnostics_dir = run_root / "diagnostics"
    bundle_dir = run_root / "bundles" / "permission_trends"
    (bundle_dir / "figures").mkdir(parents=True, exist_ok=True)
    (bundle_dir / "tables").mkdir(parents=True, exist_ok=True)
    (run_root / "conf_matrices").mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    if include_type_heatmap:
        (bundle_dir / "figures" / "type_permission_heatmap.latest.png").write_bytes(b"a")
    (bundle_dir / "figures" / "family_jsd_heatmap_topN.latest.png").write_bytes(b"b")
    (bundle_dir / "figures" / "type_permission_heatmap_dangerous_only.latest.png").write_bytes(b"c")

    table_suffix = f"_{run_id}" if run_scoped_names else ".latest"
    _write_text(
        bundle_dir / "tables" / f"dangerous_stats_tests{table_suffix}.csv",
        "metric,test,p_value\nsms,kruskal,0.01\n",
    )
    prevalence_rows = (
        "type_slug,permission,prevalence\n"
        "banker,android.permission.READ_SMS,0.8\n"
        "adware,android.permission.READ_SMS,0.2\n"
    )
    _write_text(
        bundle_dir / "tables" / f"type_permission_prevalence{table_suffix}.csv",
        prevalence_rows,
    )
    _write_text(
        bundle_dir / "tables" / f"permission_discriminability_rank{table_suffix}.csv",
        "permission,score\nandroid.permission.READ_SMS,1.0\n",
    )
    dangerous_rows = (
        "type_slug,dangerous_count_strict_mean,dangerous_count_unknown_component_mean,"
        "dangerous_count_inclusive_mean,sample_count\n"
        "banker,2.0,0.3,2.3,10\n"
        "adware,1.0,0.2,1.2,5\n"
    )
    _write_text(
        bundle_dir / "tables" / f"dangerous_distribution_by_type{table_suffix}.csv",
        dangerous_rows,
    )

    if include_jsd_pairs:
        if use_single_family_pair:
            pairs = "family_a,family_b,js_distance\nf0,f1,0.1\n"
        else:
            pairs = "family_a,family_b,js_distance\n" + "\n".join(
                [f"f{i},f{j},0.1" for i in range(family_count) for j in range(i + 1, family_count)]
            ) + "\n"
        _write_text(diagnostics_dir / f"family_jsd_pairs_verification_{run_id}.csv", pairs)

    if family_count > 0:
        _write_text(
            diagnostics_dir / f"selected_families_visual_{run_id}.csv",
            "family_canonical,sample_count,included_in_visual\n"
            + "\n".join([f"f{i},20,1" for i in range(family_count)])
            + "\n",
        )
        _write_text(
            diagnostics_dir / f"trained_family_registry_{run_id}.csv",
            "family_canonical,type_slug,sample_count,included_in_training\n"
            + "\n".join([f"f{i},banker,20,1" for i in range(family_count)])
            + "\n",
        )

    confusion_png = run_root / "conf_matrices" / "confusion_matrix_random_forest.png"
    confusion_png.write_bytes(b"d")
    _write_text(
        diagnostics_dir / f"confusion_matrix_provenance_{run_id}.csv",
        "run_id,model_name,eval_source,test_sample_count,trained_family_count,"
        "confusion_matrix_path,split_hash,feature_column_hash\n"
        f"{run_id},random_forest,test_set,100,{family_count},{confusion_png.as_posix()},,\n",
    )
    _write_text(
        diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        "Model,MacroF1,Acc\nrf,0.88,0.89\nxgb,0.87,0.88\nlog_reg,0.86,0.87\n",
    )
    _write_text(
        diagnostics_dir / ("ablation_summary.csv" if not run_scoped_names else f"ablation_summary_{run_id}.csv"),
        "Feature Set,Model,MacroF1\npermissions_only,rf,0.80\nvendor_only,rf,0.60\nvendor_permissions_fused,rf,0.90\n",
    )
    return diagnostics_dir


def test_extract_parser_list_returns_sorted_unique_names() -> None:
    """Parser extractor should return sorted unique non-null vendor names."""
    vendor_eval_df = pd.DataFrame(
        {
            "Vendor": ["Zeta", "Alpha", "Alpha", None],
            "Score": [1, 2, 3, 4],
        }
    )

    parser_list = stage_manifest._extract_parser_list(vendor_eval_df)  # pylint: disable=protected-access

    assert parser_list == ["Alpha", "Zeta"]


def test_build_paper_compliance_checks_fails_when_taxonomy_mismatch_budget_exceeded(
    tmp_path: Path,
) -> None:
    taxonomy_summary = tmp_path / "taxonomy_consistency_summary.json"
    taxonomy_summary.write_text("{}", encoding="utf-8")

    checks = build_paper_compliance_checks(
        paper_mode=True,
        split_hash="abc",
        split_audit_path=str(tmp_path / "split.csv"),
        duplicate_report_path=str(tmp_path / "dup.csv"),
        duplicate_count=0,
        invalid_sha_count=0,
        vendor_gate_debug_path=str(tmp_path / "vendor.csv"),
        run_paths_manifest_path=str(tmp_path / "run_paths.json"),
        experiment_registry_path=str(tmp_path / "registry.json"),
        taxonomy_summary_path=str(taxonomy_summary),
        taxonomy_type_rows_evaluated=10,
        taxonomy_mismatch_count=5,
        taxonomy_mismatch_max_allowed=0,
    )

    target = next(row for row in checks if row["check_id"] == "taxonomy_mismatch_budget_respected")
    assert target["status"] == "fail"
    assert "budget exceeded" in str(target["reason"])


def test_build_paper_compliance_checks_can_pass_when_only_non_paper_facing_taxonomy_noise_exists(
    tmp_path: Path,
) -> None:
    """Manifest compliance should consume the paper-facing mismatch count, not the total diagnostic count."""
    taxonomy_summary = tmp_path / "taxonomy_consistency_summary.json"
    taxonomy_summary.write_text("{}", encoding="utf-8")

    checks = build_paper_compliance_checks(
        paper_mode=True,
        split_hash="abc",
        split_audit_path=str(tmp_path / "split.csv"),
        duplicate_report_path=str(tmp_path / "dup.csv"),
        duplicate_count=0,
        invalid_sha_count=0,
        vendor_gate_debug_path=str(tmp_path / "vendor.csv"),
        run_paths_manifest_path=str(tmp_path / "run_paths.json"),
        experiment_registry_path=str(tmp_path / "registry.json"),
        taxonomy_summary_path=str(taxonomy_summary),
        taxonomy_type_rows_evaluated=10,
        taxonomy_mismatch_count=0,
        taxonomy_mismatch_max_allowed=0,
    )

    target = next(row for row in checks if row["check_id"] == "taxonomy_mismatch_budget_respected")
    assert target["status"] == "pass"


def test_write_evidence_readiness_includes_generic_alias_keys(tmp_path: Path) -> None:
    """Evidence readiness payload should expose generic status aliases."""
    out_path = evidence_pack.write_evidence_readiness(
        run_root=tmp_path / "run1",
        status="ready",
        failed_checks=[],
        manifest={
            "run_id": "run1",
            "evidence_mode": True,
            "cohort_contract": {"cohort_lock_status": "membership_locked"},
            "split": {"split_hash": "abc"},
            "dataset_hash": "def",
            "engine_list_hash": "ghi",
            "engine_ranking_hash": "jkl",
        },
        integrity_reason="",
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["evidence_readiness"] == "ready"
    assert payload["publication_ready_status"] == "ready"
    assert payload["cohort_lock_status"] == "membership_locked"
    assert (tmp_path / "run1" / "paper2_pack" / "evidence_readiness.json").exists()


def test_legacy_evidence_bundle_mirror_prefers_hardlink_when_possible(tmp_path: Path) -> None:
    """Legacy paper2_pack mirroring should avoid duplicate bytes when the FS supports hard links."""
    source_dir = tmp_path / "run1" / "evidence_bundle"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "manifest.json"
    source_path.write_text('{"ok": true}\n', encoding="utf-8")

    legacy_dir = tmp_path / "run1" / "paper2_pack"
    evidence_pack._mirror_legacy_bundle_file(  # pylint: disable=protected-access
        source_path=source_path,
        legacy_dir=legacy_dir,
    )

    legacy_path = legacy_dir / "manifest.json"
    assert legacy_path.exists()
    assert legacy_path.read_text(encoding="utf-8") == source_path.read_text(encoding="utf-8")
    assert os.path.samefile(source_path, legacy_path)


def test_finalize_run_manifest_stage_success(monkeypatch) -> None:
    """Finalize stage should return success when manifest writer succeeds."""
    captured = {}

    def _fake_write_run_manifest(manifest: dict) -> None:
        captured["manifest"] = manifest

    monkeypatch.setattr(stage_manifest.run_manifest, "write_run_manifest", _fake_write_run_manifest)
    monkeypatch.setattr(stage_manifest.run_manifest, "get_git_commit", lambda: "abc123")
    monkeypatch.setattr(
        stage_manifest.run_manifest,
        "compute_taxonomy_version_hash",
        lambda: "taxhash",
    )
    run_root = Path("output") / "runs" / "r1"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", "", raising=False)
    (diagnostics_dir / "taxonomy_consistency_summary_r1.json").write_text(
        json.dumps({"type_rows_evaluated": 1, "taxonomy_mismatch_count": 0}),
        encoding="utf-8",
    )

    pipeline_results = {
        "engine_lifecycle": pd.DataFrame(
            {
                "included_in_model_flag": [True, False],
                "engine_name_canonical": ["a", "b"],
            }
        ),
        "xgboost": {"evaluation": {"macro_f1_score": 0.5}},
    }
    vendor_eval_df = pd.DataFrame({"Vendor": ["VendorA", "VendorB"]})

    result = stage_manifest.finalize_run_manifest_stage(
        manifest_context={"run_id": "r1", "timestamp_utc": "t1", "config_hash": "cfg"},
        profile={"profile_id": "test"},
        samples_df=pd.DataFrame({"sample_id": [1, 2, 3]}),
        pipeline_results=pipeline_results,
        vendor_eval_df=vendor_eval_df,
        artifact_list=[
            str(diagnostics_dir / "a.csv"),
            str(diagnostics_dir / "a.csv"),
            str(diagnostics_dir / "b.csv"),
        ],
    )

    assert result == 0
    assert captured["manifest"]["cohort_size"] == 3
    assert captured["manifest"]["profile_id"] == "test"
    assert captured["manifest"]["run_status"] == "complete"
    assert captured["manifest"]["publication_ready_status"] == "NOT_APPLICABLE"
    assert captured["manifest"]["paper_safe_status"] == "NOT_APPLICABLE"
    assert captured["manifest"]["integrity_status"] == "pass"
    assert captured["manifest"]["trained_models"] == ["xgboost"]
    assert captured["manifest"]["included_engine_count"] == 1
    assert captured["manifest"]["excluded_engine_count"] == 1
    assert captured["manifest"]["excluded_non_run_scoped_count"] >= 0
    artifact_list = captured["manifest"]["artifact_list"]
    assert any(str(item).endswith("a.csv") for item in artifact_list)
    assert any(str(item).endswith("b.csv") for item in artifact_list)
    assert any("experiment_contract_snapshot_r1.json" in item for item in artifact_list)
    assert any("run_artifact_index.md" in item for item in artifact_list)
    run_summary_path = run_root / "run_summary.json"
    assert run_summary_path.exists()
    run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    assert run_summary["run_status"] == "complete"
    assert run_summary["completed_stage"] == "manifest"


def test_finalize_run_manifest_stage_uses_stable_output_root_for_global_latest_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Manifest integrity should accept global latest mirrors when DEFAULT_OUTPUT_DIR points at run_root."""
    captured: dict[str, object] = {}

    def _fake_write_run_manifest(manifest: dict) -> None:
        captured["manifest"] = manifest

    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r_latest"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    global_diag = output_root / "diagnostics"
    global_diag.mkdir(parents=True, exist_ok=True)
    latest_timings = global_diag / "pipeline_stage_timings.latest.csv"
    latest_timings.write_text("stage,duration_sec\nsamples,1.0\n", encoding="utf-8")

    monkeypatch.setattr(stage_manifest.run_manifest, "write_run_manifest", _fake_write_run_manifest)
    monkeypatch.setattr(stage_manifest.run_manifest, "get_git_commit", lambda: "abc123")
    monkeypatch.setattr(stage_manifest.run_manifest, "compute_taxonomy_version_hash", lambda: "taxhash")
    monkeypatch.setattr(stage_manifest.app_config, "DEFAULT_OUTPUT_DIR", str(run_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", "", raising=False)

    result = stage_manifest.finalize_run_manifest_stage(
        manifest_context={"run_id": "r_latest", "timestamp_utc": "t1", "config_hash": "cfg"},
        profile={"profile_id": "test"},
        samples_df=pd.DataFrame({"sample_id": [1, 2, 3]}),
        pipeline_results={},
        vendor_eval_df=pd.DataFrame(),
        artifact_list=[str(latest_timings), str(diagnostics_dir / "local.csv")],
    )

    assert result == 0
    assert captured["manifest"]["run_status"] == "complete"


def test_finalize_run_manifest_stage_skips_strict_paper_exports_for_failed_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Failed paper-mode runs should not trigger a second strict-export failure."""
    captured: dict[str, object] = {}

    def _fake_write_run_manifest(manifest: dict) -> None:
        captured["manifest"] = manifest

    def _strict_exports_should_not_run(**_kwargs):
        raise AssertionError("strict paper exports should be skipped for failed runs")

    run_root = tmp_path / "output" / "runs" / "r_fail"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "diagnostics").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(stage_manifest.run_manifest, "write_run_manifest", _fake_write_run_manifest)
    monkeypatch.setattr(stage_manifest.run_manifest, "get_git_commit", lambda: "abc123")
    monkeypatch.setattr(
        stage_manifest.run_manifest,
        "compute_taxonomy_version_hash",
        lambda: "taxhash",
    )
    monkeypatch.setattr(stage_manifest.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", "", raising=False)
    monkeypatch.setattr(stage_manifest, "_build_strict_paper2_exports", _strict_exports_should_not_run)
    monkeypatch.setattr(stage_manifest, "_build_paper2_pack", lambda **_kwargs: None)

    result = stage_manifest.finalize_run_manifest_stage(
        manifest_context={
            "run_id": "r_fail",
            "timestamp_utc": "t1",
            "config_hash": "cfg",
            "run_status": "failed",
            "failed_stage": "samples",
            "failure_reason": "[COHORT_LOCK] mismatch",
            "paper_mode": {"resolved_value": True, "source": "profile"},
        },
        profile={"profile_id": "paper_locked", "evidence_mode": True},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        pipeline_results={},
        vendor_eval_df=pd.DataFrame(),
        artifact_list=[],
    )

    assert result == 1
    manifest = captured["manifest"]
    assert manifest["run_status"] == "failed"
    assert manifest["paper_export_status"]["enabled"] is False
    assert manifest["paper_export_status"]["reason"] == "run_failed"


def test_finalize_run_manifest_stage_rewrites_terminal_manifest_with_compliance_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Final manifest should carry terminal publication/evidence fields, not only the early pre-compliance payload."""
    captured: dict[str, object] = {}
    run_root = tmp_path / "output" / "runs" / "r_term"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "diagnostics").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(stage_manifest.run_manifest, "get_git_commit", lambda: "abc123")
    monkeypatch.setattr(stage_manifest.run_manifest, "compute_taxonomy_version_hash", lambda: "taxhash")
    monkeypatch.setattr(stage_manifest.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", "", raising=False)
    monkeypatch.setattr(stage_manifest, "_build_strict_paper2_exports", lambda **_kwargs: {})
    monkeypatch.setattr(stage_manifest, "_build_paper2_pack", lambda **_kwargs: None)
    monkeypatch.setattr(
        stage_manifest,
        "_write_manifest_with_pointer",
        lambda **kwargs: captured.__setitem__("manifest", kwargs["manifest"]),
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_summary_json",
        lambda **_kwargs: run_root / "run_summary.json",
    )
    monkeypatch.setattr(stage_manifest, "_finalize_output_hygiene_bundle", lambda **_kwargs: None)
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_summary_onepager",
        lambda **_kwargs: diagnostics_dir / "run_summary_onepager.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_experiment_contract_snapshot",
        lambda **_kwargs: diagnostics_dir / "experiment_contract_snapshot_r_term.json",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_evaluation_contract_json",
        lambda **_kwargs: diagnostics_dir / "evaluation_contract_r_term.json",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_taxonomy_authority_recommendation_md",
        lambda **_kwargs: diagnostics_dir / "taxonomy_authority.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_artifact_index",
        lambda **_kwargs: diagnostics_dir / "run_artifact_index.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_export_trained_family_registry",
        lambda **_kwargs: (diagnostics_dir / "trained_family_registry.csv", 0),
    )
    monkeypatch.setattr(
        stage_manifest,
        "_export_confusion_matrix_provenance",
        lambda **_kwargs: diagnostics_dir / "confusion_matrix_provenance.json",
    )
    monkeypatch.setattr(
        stage_manifest.compliance,
        "build_compliance_report",
        lambda **_kwargs: {"overall_status": "fail"},
    )
    monkeypatch.setattr(stage_manifest.compliance, "write_compliance_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_render_consensus_distribution_png", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_write_evidence_compliance_stub", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_family_temporal_scope_table", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_paper_ablation_table", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_paper_cohort_summary_table", lambda **_kwargs: None)

    result = stage_manifest.finalize_run_manifest_stage(
        manifest_context={
            "run_id": "r_term",
            "timestamp_utc": "t1",
            "config_hash": "cfg",
            "paper_mode": {"resolved_value": True, "source": "profile"},
        },
        profile={"profile_id": "paper_profile", "evidence_mode": False},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        pipeline_results={},
        vendor_eval_df=pd.DataFrame(),
        artifact_list=[],
    )

    assert result == 1
    manifest = captured["manifest"]
    assert manifest["profile_id"] == "paper_profile"
    assert manifest["publication_ready_status"] == "FAIL"
    assert manifest["paper_safe_status"] == "FAIL"
    assert "paper_compliance_not_pass" in manifest["publication_ready_reasons"]


def test_finalize_run_manifest_stage_skips_research_validity_bundle_for_samples_stop(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Samples-only partial runs should not spend manifest time on deep audit bundles."""
    def _research_bundle_should_not_run(**_kwargs):
        raise AssertionError("research validity bundle should be skipped for stop_after=samples")

    run_root = tmp_path / "output" / "runs" / "r_samples"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "diagnostics").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(stage_manifest.run_manifest, "get_git_commit", lambda: "abc123")
    monkeypatch.setattr(stage_manifest.run_manifest, "compute_taxonomy_version_hash", lambda: "taxhash")
    monkeypatch.setattr(stage_manifest.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", "", raising=False)
    monkeypatch.setattr(stage_manifest, "_build_strict_paper2_exports", lambda **_kwargs: {})
    monkeypatch.setattr(stage_manifest, "_build_paper2_pack", lambda **_kwargs: None)
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_summary_json",
        lambda **_kwargs: Path(str(run_root / "run_summary.json")),
    )
    monkeypatch.setattr(
        stage_manifest,
        "_finalize_output_hygiene_bundle",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_summary_onepager",
        lambda **_kwargs: diagnostics_dir / "run_summary_onepager.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_experiment_contract_snapshot",
        lambda **_kwargs: diagnostics_dir / "experiment_contract_snapshot_r_samples.json",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_evaluation_contract_json",
        lambda **_kwargs: diagnostics_dir / "evaluation_contract_r_samples.json",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_taxonomy_authority_recommendation_md",
        lambda **_kwargs: diagnostics_dir / "taxonomy_authority.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_artifact_index",
        lambda **_kwargs: diagnostics_dir / "run_artifact_index.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_export_trained_family_registry",
        lambda **_kwargs: (diagnostics_dir / "trained_family_registry.csv", 0),
    )
    monkeypatch.setattr(
        stage_manifest,
        "_export_confusion_matrix_provenance",
        lambda **_kwargs: diagnostics_dir / "confusion_matrix_provenance.json",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_manifest_with_pointer",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        stage_manifest.compliance,
        "build_compliance_report",
        lambda **_kwargs: {"overall_status": "pass"},
    )
    monkeypatch.setattr(stage_manifest.compliance, "write_compliance_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_render_consensus_distribution_png", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_write_evidence_compliance_stub", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_family_temporal_scope_table", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_paper_ablation_table", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_paper_cohort_summary_table", lambda **_kwargs: None)

    monkeypatch.setattr(
        __import__("obsidiandroid.diagnostics.research_validity", fromlist=["write_research_validity_bundle"]),
        "write_research_validity_bundle",
        _research_bundle_should_not_run,
    )

    manifest_context = {
            "run_id": "r_samples",
            "timestamp_utc": "t1",
            "config_hash": "cfg",
            "run_status": "partial",
            "completed_stage": "samples",
            "stop_after": "samples",
        }

    result = stage_manifest.finalize_run_manifest_stage(
        manifest_context=manifest_context,
        profile={"profile_id": "unit_samples_audit", "evidence_mode": False},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        pipeline_results={},
        vendor_eval_df=pd.DataFrame(),
        artifact_list=[],
    )

    assert result == 0
    assert manifest_context["_research_bundle_skipped_reason"] == "stop_after_samples"
    assert manifest_context["_hostile_bundle_skipped_reason"] == "stop_after_samples"


def test_finalize_run_manifest_stage_keeps_evidence_samples_stop_nonfatal(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Evidence/publication runs stopped at samples should remain partial instead of failing on missing downstream artifacts."""
    captured: dict[str, object] = {}
    run_root = tmp_path / "output" / "runs" / "r_partial"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "diagnostics").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(stage_manifest.run_manifest, "get_git_commit", lambda: "abc123")
    monkeypatch.setattr(stage_manifest.run_manifest, "compute_taxonomy_version_hash", lambda: "taxhash")
    monkeypatch.setattr(stage_manifest.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", "", raising=False)
    monkeypatch.setattr(stage_manifest, "_build_strict_paper2_exports", lambda **_kwargs: {})
    monkeypatch.setattr(stage_manifest, "_build_paper2_pack", lambda **_kwargs: None)
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_summary_json",
        lambda **kwargs: captured.setdefault("result_code", kwargs["result_code"]) or Path(str(run_root / "run_summary.json")),
    )
    monkeypatch.setattr(
        stage_manifest,
        "_finalize_output_hygiene_bundle",
        lambda **kwargs: captured.setdefault("bundle_result_code", kwargs["result_code"]),
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_summary_onepager",
        lambda **_kwargs: diagnostics_dir / "run_summary_onepager.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_experiment_contract_snapshot",
        lambda **_kwargs: diagnostics_dir / "experiment_contract_snapshot_r_partial.json",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_evaluation_contract_json",
        lambda **_kwargs: diagnostics_dir / "evaluation_contract_r_partial.json",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_taxonomy_authority_recommendation_md",
        lambda **_kwargs: diagnostics_dir / "taxonomy_authority.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_run_artifact_index",
        lambda **_kwargs: diagnostics_dir / "run_artifact_index.md",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_export_trained_family_registry",
        lambda **_kwargs: (diagnostics_dir / "trained_family_registry.csv", 0),
    )
    monkeypatch.setattr(
        stage_manifest,
        "_export_confusion_matrix_provenance",
        lambda **_kwargs: diagnostics_dir / "confusion_matrix_provenance.json",
    )
    monkeypatch.setattr(
        stage_manifest,
        "_write_manifest_with_pointer",
        lambda **kwargs: captured.setdefault("manifest", kwargs["manifest"]),
    )
    monkeypatch.setattr(
        stage_manifest.compliance,
        "build_compliance_report",
        lambda **_kwargs: {"overall_status": "fail"},
    )
    monkeypatch.setattr(stage_manifest.compliance, "write_compliance_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_render_consensus_distribution_png", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_write_evidence_compliance_stub", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_family_temporal_scope_table", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_paper_ablation_table", lambda **_kwargs: None)
    monkeypatch.setattr(stage_manifest, "_build_paper_cohort_summary_table", lambda **_kwargs: None)

    manifest_context = {
        "run_id": "r_partial",
        "timestamp_utc": "t1",
        "config_hash": "cfg",
        "run_status": "partial",
        "completed_stage": "samples",
        "stop_after": "samples",
        "paper_mode": {"resolved_value": True, "source": "profile"},
        "paper_cohort_contract": {
            "paper_locked": True,
            "cohort_lock_status": "count_only_incomplete_sample_lock",
            "validation": {"status": "degraded_live_db_drift", "mismatches": []},
        },
    }

    result = stage_manifest.finalize_run_manifest_stage(
        manifest_context=manifest_context,
        profile={"profile_id": "malicious_temporal_stability_locked", "evidence_mode": True},
        samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["fam_a"], "type_slug": ["banker"]}),
        pipeline_results={},
        vendor_eval_df=pd.DataFrame(),
        artifact_list=[],
    )

    assert result == 0
    assert captured["result_code"] == 0
    assert captured["bundle_result_code"] == 0
    assert captured["manifest"]["run_status"] == "partial"


def test_write_run_summary_json_creates_canonical_and_latest(
    tmp_path: Path, monkeypatch
) -> None:
    """Canonical run summary writer should emit run-root and diagnostics copies."""
    run_root = tmp_path / "output" / "runs" / "r1"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        stage_manifest.app_config,
        "RUNTIME_OUTPUT_ROOT_BASE",
        str(tmp_path / "output"),
        raising=False,
    )
    out_path = stage_manifest._write_run_summary_json(  # pylint: disable=protected-access
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        manifest_context={
            "run_id": "r1",
            "timestamp_utc": "2026-03-21T00:00:00Z",
            "run_status": "failed",
            "completed_stage": "training",
            "failed_stage": "training",
            "failure_reason": "training crashed",
            "pipeline_runtime_sec": 12.3,
        },
        manifest={
            "run_id": "r1",
            "timestamp_utc": "2026-03-21T00:00:00Z",
            "profile_params": {"profile_id": "malicious_temporal_stability"},
            "cohort_size": 1226,
            "selected_vendor_count": 8,
            "vendor_constrained_run_flag": False,
            "model_summary": {"top_model": "xgboost", "top_macro_f1": 0.91},
            "paper_mode": {"resolved_value": True},
            "evidence_mode": True,
        },
        result_code=1,
    )

    assert out_path == run_root / "run_summary.json"
    assert out_path.exists()
    assert (diagnostics_dir / "run_summary_r1.json").exists()
    global_latest = tmp_path / "output" / "diagnostics" / "run_summary.latest.json"
    assert global_latest.exists()
    assert not (diagnostics_dir / "run_summary.latest.json").exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["run_status"] == "failed"
    assert payload["failure_reason"] == "training crashed"
    assert payload["publication_ready_status"] == "FAIL"
    assert "paper_compliance_not_pass" in payload["publication_ready_reasons"]


def test_write_manifest_with_pointer_paper_mode(tmp_path: Path, monkeypatch) -> None:
    """Paper mode should write full latest manifest + separate pointer file."""
    run_root = tmp_path / "output" / "runs" / "r1"
    run_root.mkdir(parents=True, exist_ok=True)
    pointer_path = tmp_path / "output" / "diagnostics" / "latest_run_pointer.json"
    latest_manifest_path = tmp_path / "output" / "diagnostics" / "run_manifest.latest.json"
    promoted_txt = tmp_path / "output" / "promoted" / "latest_run.txt"
    promoted_manifest = tmp_path / "output" / "promoted" / "latest_run_manifest.json"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(stage_manifest.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_manifest.run_manifest, "MANIFEST_PATH", latest_manifest_path)

    stage_manifest._write_manifest_with_pointer(  # pylint: disable=protected-access
        manifest={"run_id": "r1", "timestamp_utc": "2026-01-01T00:00:00Z"},
        run_id="r1",
        paper_mode=True,
        run_root=run_root,
    )

    canonical = run_root / "run_manifest.json"
    assert canonical.exists()
    assert pointer_path.exists()
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["run_id"] == "r1"
    assert "run_root" in pointer
    assert latest_manifest_path.exists()
    latest_manifest = json.loads(latest_manifest_path.read_text(encoding="utf-8"))
    assert latest_manifest["run_id"] == "r1"
    assert "manifest_schema_version" in latest_manifest
    assert promoted_txt.exists()
    assert promoted_txt.read_text(encoding="utf-8").strip() == "r1"
    assert promoted_manifest.exists()


def test_write_manifest_with_pointer_non_paper_updates_promoted_pointer(
    tmp_path: Path, monkeypatch
) -> None:
    """Non-paper runs should still update promoted latest run pointers."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r_np"
    run_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "diagnostics" / "run_manifest.latest.json"

    monkeypatch.setattr(stage_manifest.app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(stage_manifest.run_manifest, "MANIFEST_PATH", manifest_path)

    stage_manifest._write_manifest_with_pointer(  # pylint: disable=protected-access
        manifest={"run_id": "r_np", "timestamp_utc": "2026-01-02T00:00:00Z"},
        run_id="r_np",
        paper_mode=False,
        run_root=run_root,
    )

    promoted_txt = output_root / "promoted" / "latest_run.txt"
    promoted_manifest = output_root / "promoted" / "latest_run_manifest.json"
    assert promoted_txt.exists()
    assert promoted_txt.read_text(encoding="utf-8").strip() == "r_np"
    assert promoted_manifest.exists()
    payload = json.loads(promoted_manifest.read_text(encoding="utf-8"))
    assert payload["run_id"] == "r_np"
    assert (run_root / "run_manifest.json").exists()


def test_write_manifest_with_pointer_uses_global_diagnostics_when_default_output_dir_is_run_root(
    tmp_path: Path, monkeypatch
) -> None:
    """Evidence-style run roots should still update global latest manifest and pointer files."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r_ev"
    run_root.mkdir(parents=True, exist_ok=True)
    global_diag = output_root / "diagnostics"
    global_diag.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(stage_manifest.app_config, "DEFAULT_OUTPUT_DIR", str(run_root), raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(stage_manifest.run_manifest, "MANIFEST_PATH", stage_manifest.run_manifest._INITIAL_MANIFEST_PATH)

    stage_manifest._write_manifest_with_pointer(  # pylint: disable=protected-access
        manifest={"run_id": "r_ev", "timestamp_utc": "2026-01-03T00:00:00Z"},
        run_id="r_ev",
        paper_mode=True,
        run_root=run_root,
    )

    assert (run_root / "run_manifest.json").exists()
    assert (global_diag / "run_manifest.latest.json").exists()
    assert (global_diag / "latest_run_pointer.json").exists()
    assert not (run_root / "diagnostics" / "run_manifest.latest.json").exists()
    assert not (run_root / "diagnostics" / "latest_run_pointer.json").exists()


def test_write_run_summary_onepager_creates_run_and_latest(tmp_path: Path) -> None:
    """One-pager writer should emit run-scoped and latest markdown artifacts."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    out_path = stage_manifest._write_run_summary_onepager(  # pylint: disable=protected-access
        run_id="r1",
        diagnostics_dir=diagnostics_dir,
        profile={"profile_id": "all_malicious"},
        manifest_context={
            "paper_mode": {"resolved_value": True, "source": "cli"},
            "model_summary": {
                "top_model": "logistic_regression",
                "top_macro_f1": 0.79,
                "model_rows": [
                    {"model": "logistic_regression", "macro_f1": 0.79, "weighted_f1": 0.93, "accuracy": 0.94}
                ],
            },
            "stage_timings_sec": {"samples": 1.25, "training": 8.7},
        },
        manifest={
            "cohort_size": 2447,
            "selected_vendor_count": 8,
            "vendor_set_hash": "abc123",
            "split": {"split_hash": "split123", "split_audit_path": "split.csv"},
            "duplicate_sha": {"duplicate_sha_groups": 0, "invalid_sha_count": 0},
        },
        compliance_path=diagnostics_dir / "paper_mode_compliance_report_r1.json",
    )

    assert out_path is not None
    assert out_path.exists()
    latest = diagnostics_dir / "run_summary_onepager.latest.md"
    assert latest.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "Run Summary One-Pager (r1)" in text
    assert "top_model: `logistic_regression`" in text


def test_write_run_summary_onepager_run_scoped_uses_global_latest(
    monkeypatch: pytest.MonkeyPatch,
    make_run_diagnostics_layout,
) -> None:
    """Run-scoped one-pager should avoid local latest duplication."""
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("r1")

    out_path = stage_manifest._write_run_summary_onepager(  # pylint: disable=protected-access
        run_id="r1",
        diagnostics_dir=diagnostics_dir,
        profile={"profile_id": "all_malicious"},
        manifest_context={"paper_mode": {"resolved_value": True, "source": "cli"}},
        manifest={"cohort_size": 10},
        compliance_path=None,
    )

    assert out_path is not None and out_path.exists()
    assert not (diagnostics_dir / "run_summary_onepager.latest.md").exists()
    assert (output_root / "diagnostics" / "run_summary_onepager.latest.md").exists()


def test_write_experiment_contract_snapshot_creates_files(tmp_path: Path, monkeypatch) -> None:
    """Experiment contract snapshot writer should emit run-scoped and latest files."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(stage_manifest.app_config, "CV_FOLDS", 5, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "CV_REPEATS", 1, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RANDOM_STATE", 42, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(
        stage_manifest.app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "family_id", raising=False
    )
    monkeypatch.setattr(
        stage_manifest.app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", 19, raising=False
    )
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_COHORT_FAMILY_COUNT", 39, raising=False)

    out_path = stage_manifest._write_experiment_contract_snapshot(  # pylint: disable=protected-access
        run_id="r2",
        diagnostics_dir=diagnostics_dir,
        profile={"profile_id": "malicious_temporal_stability", "cohort_gates": {"min_malicious_detections": 5, "family_cap": 300}},
        manifest_context={
            "paper_mode": {"resolved_value": True, "source": "cli"},
            "model_config_hash": "mhash",
            "paper_cohort_contract": {
                "contract_name": "malicious_temporal_stability_locked",
                "contract_id": "malicious_temporal_stability_locked_contract",
                "paper_locked": True,
                "contract_status": "membership_locked",
                "canonical_historical_run_id": "20260504T044304Z__8c64e6",
                "expected": {"sample_count": 1226, "family_count": 39, "type_count": 6},
                "sample_id_lock": {
                    "path": "/tmp/lock.csv",
                    "lock_sample_count": 1226,
                    "lock_sample_id_hash": "abc123",
                },
            },
        },
        manifest={"split": {"split_hash": "shash", "split_seed": 42, "split_algorithm": "stratified_seeded", "split_algorithm_version": "1.0"}},
    )

    assert out_path is not None
    assert out_path.exists()
    latest = diagnostics_dir / "experiment_contract_snapshot.latest.json"
    assert latest.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "r2"
    assert payload["model_contract"]["model_config_hash"] == "mhash"
    assert payload["model_contract"]["no_model_retuning_across_perturbations"] is True
    assert payload["experiment_series"]["series_id"]
    assert payload["target_task"]["training_label_field"] == "family_id"
    assert payload["label_authority_reporting"]["training_label_field"] == "family_id"
    assert payload["paper_cohort_contract"]["contract_name"] == "malicious_temporal_stability_locked"
    assert payload["paper_cohort_contract"]["paper_locked"] is True
    assert payload["paper_cohort_contract"]["expected"]["sample_count"] == 1226
    assert payload["paper_cohort_contract"]["sample_id_lock"]["lock_sample_count"] == 1226
    assert payload["cohort_contract"]["contract_id"] == "malicious_temporal_stability_locked_contract"


def test_write_experiment_contract_snapshot_run_scoped_uses_global_latest(
    monkeypatch: pytest.MonkeyPatch,
    make_run_diagnostics_layout,
) -> None:
    """Run-scoped experiment contract snapshots should mirror latest globally."""
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("r2")
    monkeypatch.setattr(stage_manifest.app_config, "CV_FOLDS", 5, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "CV_REPEATS", 1, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RANDOM_STATE", 42, raising=False)

    out_path = stage_manifest._write_experiment_contract_snapshot(  # pylint: disable=protected-access
        run_id="r2",
        diagnostics_dir=diagnostics_dir,
        profile={"profile_id": "malicious_temporal_stability", "cohort_gates": {}},
        manifest_context={"paper_mode": {"resolved_value": True, "source": "cli"}, "model_config_hash": "mhash"},
        manifest={"split": {"split_hash": "shash", "split_seed": 42, "split_algorithm": "x", "split_algorithm_version": "1.0"}},
    )

    assert out_path is not None and out_path.exists()
    assert not (diagnostics_dir / "experiment_contract_snapshot.latest.json").exists()
    assert (output_root / "diagnostics" / "experiment_contract_snapshot.latest.json").exists()


def test_contract_snapshot_detects_model_config_drift_within_series(tmp_path: Path, monkeypatch) -> None:
    """No-retuning flag should drop to false when latest run in same series has different config hash."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(stage_manifest.app_config, "CV_FOLDS", 5, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "CV_REPEATS", 1, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RANDOM_STATE", 42, raising=False)

    previous = {
        "run_id": "r_prev",
        "profile_id": "malicious_temporal_stability",
        "experiment_series": {"series_id": stage_manifest._compute_experiment_series_id(  # pylint: disable=protected-access
            profile_id="malicious_temporal_stability",
            split_hash="shash",
        )},
        "model_contract": {"model_config_hash": "oldhash", "no_model_retuning_across_perturbations": True},
        "split_contract": {"split_hash": "shash"},
    }
    (diagnostics_dir / "experiment_contract_snapshot.latest.json").write_text(
        json.dumps(previous),
        encoding="utf-8",
    )

    out_path = stage_manifest._write_experiment_contract_snapshot(  # pylint: disable=protected-access
        run_id="r_new",
        diagnostics_dir=diagnostics_dir,
        profile={"profile_id": "malicious_temporal_stability", "cohort_gates": {}},
        manifest_context={"paper_mode": {"resolved_value": True, "source": "cli"}, "model_config_hash": "newhash"},
        manifest={"split": {"split_hash": "shash", "split_seed": 42, "split_algorithm": "stratified_seeded", "split_algorithm_version": "1.0"}},
    )

    assert out_path is not None
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["experiment_series"]["previous_run_id_in_series"] == "r_prev"
    assert payload["experiment_series"]["model_config_hash_stable_with_series"] is False
    assert payload["model_contract"]["no_model_retuning_across_perturbations"] is False


def test_render_consensus_distribution_png_forces_agg_backend(tmp_path: Path) -> None:
    """Consensus chart rendering should force a non-interactive backend."""
    pytest.importorskip("matplotlib")
    out_path = tmp_path / "consensus_distribution.png"
    df = pd.DataFrame(
        {
            "bucket": ["0-0.10", "0.10-0.25"],
            "percent": [0.2, 0.8],
        }
    )

    stage_manifest._render_consensus_distribution_png(  # pylint: disable=protected-access
        consensus_df=df,
        output_path=out_path,
    )

    import matplotlib  # imported after renderer call on purpose

    assert "agg" in str(matplotlib.get_backend()).lower()
    assert out_path.exists()


def test_write_run_artifact_index_creates_markdown(tmp_path: Path) -> None:
    """Run artifact index should be written under diagnostics with key pointers."""
    run_root = tmp_path / "output" / "runs" / "r_idx"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "taxonomy_consistency_summary.latest.json").write_text("{}", encoding="utf-8")

    out_path = stage_manifest._write_run_artifact_index(  # pylint: disable=protected-access
        run_id="r_idx",
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
    )

    assert out_path is not None
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "Authoritative source" in text
    assert "paper_exports" in text
    assert "Lifecycle classes:" in text
    assert "legacy_compatibility" in text


def test_export_parser_quality_final_writes_final_gate_snapshot(tmp_path: Path) -> None:
    """Final parser quality export should be derived from engine weights frame."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    weights_df = pd.DataFrame(
        {
            "Vendor": ["Lionic", "Tencent"],
            "parser_gate_status": ["included_relaxed_mapped", "excluded_low_mapped"],
            "included_in_model": [1, 0],
        }
    )

    out_path = stage_manifest._export_parser_quality_final(  # pylint: disable=protected-access
        diagnostics_dir=diagnostics_dir,
        run_id="rfinal",
        weights_df=weights_df,
    )

    assert out_path is not None
    assert out_path.exists()
    latest = diagnostics_dir / "parser_quality_final.latest.csv"
    assert latest.exists()
    exported = pd.read_csv(out_path)
    assert list(exported["vendor_id"]) == ["lionic", "tencent"]
    assert list(exported["included_in_model"]) == [1, 0]
    assert "included_in_engine_weights" in exported.columns
    assert "selected_for_feature_matrix" in exported.columns
    assert "selection_status" in exported.columns
    assert "selection_stage" in exported.columns
    assert set(exported["diagnostic_stage"].unique()) == {"engine_weights_final"}


def test_export_parser_quality_final_run_scoped_uses_global_latest(
    monkeypatch: pytest.MonkeyPatch,
    make_run_diagnostics_layout,
) -> None:
    """Run-scoped parser quality final export should not emit local latest duplicates."""
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rfinal")
    weights_df = pd.DataFrame(
        {
            "Vendor": ["Lionic"],
            "parser_gate_status": ["included_relaxed_mapped"],
            "included_in_model": [1],
        }
    )

    out_path = stage_manifest._export_parser_quality_final(  # pylint: disable=protected-access
        diagnostics_dir=diagnostics_dir,
        run_id="rfinal",
        weights_df=weights_df,
    )

    assert out_path is not None and out_path.exists()
    assert not (diagnostics_dir / "parser_quality_final.latest.csv").exists()
    assert (output_root / "diagnostics" / "parser_quality_final.latest.csv").exists()


def test_build_paper_compliance_checks_includes_taxonomy_type_guard(tmp_path: Path) -> None:
    split_audit = tmp_path / "split.csv"
    split_audit.write_text("x\n", encoding="utf-8")
    dup = tmp_path / "dup.csv"
    dup.write_text("x\n", encoding="utf-8")
    vendor = tmp_path / "vendor.csv"
    vendor.write_text("x\n", encoding="utf-8")
    run_paths = tmp_path / "run_paths.json"
    run_paths.write_text("{}", encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    tax = tmp_path / "taxonomy.json"
    tax.write_text("{}", encoding="utf-8")

    checks = build_paper_compliance_checks(
        paper_mode=True,
        split_hash="abc",
        split_audit_path=str(split_audit),
        duplicate_report_path=str(dup),
        duplicate_count=0,
        invalid_sha_count=0,
        vendor_gate_debug_path=str(vendor),
        run_paths_manifest_path=str(run_paths),
        experiment_registry_path=str(registry),
        taxonomy_summary_path=str(tax),
        taxonomy_type_rows_evaluated=0,
    )

    by_id = {row["check_id"]: row for row in checks}
    assert "taxonomy_type_audit_not_blind" in by_id
    assert by_id["taxonomy_type_audit_not_blind"]["status"] == "fail"


def test_export_trained_family_registry_writes_expected_columns(tmp_path: Path, monkeypatch) -> None:
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 3, raising=False)
    samples_df = pd.DataFrame(
        {
            "family_canonical": ["a", "a", "a", "b", "b"],
            "type_slug": ["banker", "banker", "banker", "adware", "adware"],
        }
    )

    out_path, included_count = stage_manifest._export_trained_family_registry(  # pylint: disable=protected-access
        samples_df=samples_df,
        run_id="r1",
        diagnostics_dir=diagnostics_dir,
    )

    assert out_path is not None
    assert out_path.exists()
    exported = pd.read_csv(out_path)
    assert list(exported.columns) == [
        "run_id",
        "family_canonical",
        "type_slug",
        "sample_count",
        "included_in_training",
    ]
    assert included_count == 1


def test_export_trained_family_registry_run_scoped_uses_global_latest(
    monkeypatch: pytest.MonkeyPatch,
    make_run_diagnostics_layout,
) -> None:
    """Run-scoped trained family registry should mirror latest globally."""
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("r1")
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 3, raising=False)
    samples_df = pd.DataFrame({"family_canonical": ["a", "a", "a"], "type_slug": ["banker", "banker", "banker"]})

    out_path, _ = stage_manifest._export_trained_family_registry(  # pylint: disable=protected-access
        samples_df=samples_df,
        run_id="r1",
        diagnostics_dir=diagnostics_dir,
    )

    assert out_path is not None and out_path.exists()
    assert not (diagnostics_dir / "trained_family_registry.latest.csv").exists()
    assert (output_root / "diagnostics" / "trained_family_registry.latest.csv").exists()


def test_export_confusion_matrix_provenance_uses_test_set_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = tmp_path / "output" / "runs" / "r1"
    diagnostics_dir, cm_dir, _model_dir = _seed_confusion_provenance_artifacts(
        run_root,
        "r1",
        samples_tested=123,
    )
    monkeypatch.setattr(
        stage_manifest.app_config,
        "RUNTIME_HEADLINE_SPLIT_METADATA",
        {"split_hash": "aa" * 32},
        raising=False,
    )
    monkeypatch.setattr(
        stage_manifest.app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "feat_h", raising=False
    )

    out_path = stage_manifest._export_confusion_matrix_provenance(  # pylint: disable=protected-access
        run_root=run_root,
        run_id="r1",
        diagnostics_dir=diagnostics_dir,
        manifest_context={},
        trained_family_count=19,
        evidence_mode=False,
    )

    assert out_path is not None
    exported = pd.read_csv(out_path)
    row = exported.iloc[0].to_dict()
    assert row["model_name"] == "random_forest"
    assert row["eval_source"] == "test_set"
    assert int(row["test_sample_count"]) == 123
    assert int(row["trained_family_count"]) == 19
    assert str(row["split_hash"]) == "aa" * 32
    assert str(row["feature_column_hash"]) == "feat_h"
    assert row["confusion_matrix_path"].endswith("confusion_matrix_primary.png")


def test_export_confusion_matrix_provenance_run_scoped_uses_global_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run-scoped confusion provenance should mirror latest globally."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    diagnostics_dir, cm_dir, _model_dir = _seed_confusion_provenance_artifacts(
        run_root,
        "r1",
        samples_tested=7,
    )
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    out_path = stage_manifest._export_confusion_matrix_provenance(  # pylint: disable=protected-access
        run_root=run_root,
        run_id="r1",
        diagnostics_dir=diagnostics_dir,
        manifest_context={},
        trained_family_count=3,
        evidence_mode=False,
    )

    assert out_path is not None and out_path.exists()
    assert not (diagnostics_dir / "confusion_matrix_provenance.latest.csv").exists()
    assert (output_root / "diagnostics" / "confusion_matrix_provenance.latest.csv").exists()


def test_build_cohort_limitation_summary_computes_key_shares(monkeypatch) -> None:
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 2, raising=False)
    samples_df = pd.DataFrame(
        {
            "family_canonical": ["f1", "f1", "f2", "f3"],
            "type_slug": ["banker", "banker", "adware", "rat"],
        }
    )
    summary = stage_manifest._build_cohort_limitation_summary(samples_df)  # pylint: disable=protected-access
    assert summary["total_samples"] == 4
    assert summary["total_cohort_families"] == 3
    assert summary["training_families"] == 1
    assert summary["represented_types"] == 3
    assert summary["top_family_share"] == 0.5
    assert summary["banker_share"] == 0.5


def test_build_strict_paper2_exports_creates_registries(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    run_id = "r1"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = _seed_strict_paper2_inputs(run_root, run_id, family_count=12)
    _write_text(
        diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        "Model,MacroF1,Acc\nxgb,0.90,0.91\nbal_rf,0.99,0.99\nrf,0.88,0.89\nlog_reg,0.87,0.88\n",
    )
    _write_text(
        diagnostics_dir / "ablation_summary.csv",
        "Feature Set,Model,MacroF1\npermissions_only,rf,0.80\nvendor_only,rf,0.60\nvendor_permissions_fused,rf,0.90\nvendor_no_parsed_family,rf,0.55\npermissions_only,bal_rf,0.70\n",
    )
    stale = run_root / "paper_exports" / "figures" / "stale.png"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"old")
    monkeypatch.setattr(stage_manifest.app_config, "PAPER2_STRICT_EXPORT_PROFILE", True, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "MAX_FAMILY_VISUAL_COUNT", 12, raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "MAX_PERMISSIONS_HEATMAP", 16, raising=False)

    out = stage_manifest._build_strict_paper2_exports(  # pylint: disable=protected-access
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        samples_df=pd.DataFrame(
            {
                "family_canonical": ["f1", "f1", "f2"],
                "type_slug": ["banker", "banker", "adware"],
                "effective_first_seen_at_utc": ["2020-01-01", "2021-01-01", "2022-01-01"],
            }
        ),
        manifest_context={},
        evidence_mode=False,
        paper_mode=True,
    )

    assert out["profile"]["single_run_id"] == run_id
    docs_dir = run_root / "paper_exports" / "docs"
    assert (docs_dir / "paper_figure_registry.csv").exists()
    assert (docs_dir / "paper_table_registry.csv").exists()
    assert not stale.exists()
    model_table = pd.read_csv(run_root / "paper_exports" / "tables" / "model_comparison_rf_xgb_lr_fused.csv")
    assert set(model_table["model"].tolist()) == {
        "random_forest",
        "xgboost",
        "logistic_regression",
    }
    ablation_table = pd.read_csv(run_root / "paper_exports" / "tables" / "feature_ablation.csv")
    assert set(ablation_table["feature_set"].tolist()) == {
        "permissions_only",
        "vendor_only",
        "vendor_permissions_fused",
    }


def test_build_strict_paper2_exports_accepts_run_scoped_bundle_sources(tmp_path: Path, monkeypatch) -> None:
    """Strict paper export should resolve run-scoped permission-trends and ablation inputs."""
    run_id = "rscoped"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = _seed_strict_paper2_inputs(
        run_root,
        run_id,
        family_count=12,
        run_scoped_names=True,
    )
    monkeypatch.setattr(stage_manifest.app_config, "PAPER2_STRICT_EXPORT_PROFILE", True, raising=False)

    out = stage_manifest._build_strict_paper2_exports(  # pylint: disable=protected-access
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        samples_df=pd.DataFrame(
            {
                "family_canonical": ["f1", "f1", "f2"],
                "type_slug": ["banker", "banker", "adware"],
                "effective_first_seen_at_utc": ["2020-01-01", "2021-01-01", "2022-01-01"],
            }
        ),
        manifest_context={},
        evidence_mode=True,
        paper_mode=True,
    )

    assert out["profile"]["single_run_id"] == run_id
    assert (run_root / "paper_exports" / "tables" / "feature_ablation.csv").exists()
    assert (run_root / "paper_exports" / "tables" / "dangerous_permission_stats_tests.csv").exists()


def test_build_paper_ablation_table_supports_experiment_schema(tmp_path: Path) -> None:
    source = tmp_path / "ablation_summary.csv"
    source.write_text(
        (
            "experiment,model,accuracy,macro_f1_score,leakage_sensitivity_delta\n"
            "permissions_only,random_forest,0.90,0.80,0.20\n"
            "vendor_only,random_forest,0.85,0.60,0.00\n"
            "vendor_permissions_fused,random_forest,0.93,0.88,0.28\n"
            "vendor_no_parsed_family,random_forest,0.70,0.50,-0.10\n"
        ),
        encoding="utf-8",
    )
    output = tmp_path / "feature_ablation.csv"

    stage_manifest._build_paper_ablation_table(  # pylint: disable=protected-access
        source_path=source,
        output_path=output,
    )

    out_df = pd.read_csv(output)
    assert set(out_df["feature_set"].tolist()) == {
        "permissions_only",
        "vendor_only",
        "vendor_permissions_fused",
    }
    assert "vendor_no_parsed_family" not in set(out_df["feature_set"].tolist())


def test_build_paper_ablation_table_normalizes_current_runtime_feature_sets(tmp_path: Path) -> None:
    source = tmp_path / "ablation_summary_current.csv"
    source.write_text(
        (
            "experiment,label_target,model,accuracy,macro_f1_score,delta_vs_full_fused\n"
            "permissions_grouped,family_id,random_forest,0.95,0.93,-0.03\n"
            "permissions_raw,family_within_type,random_forest,0.96,0.94,-0.02\n"
            "vendor_full,family_id,xgboost,0.96,0.92,-0.05\n"
            "permissions_grouped_plus_vendor_no_family,family_id,xgboost,0.98,0.97,-0.01\n"
            "full_fused,family_id,xgboost,0.99,0.98,0.00\n"
        ),
        encoding="utf-8",
    )
    output = tmp_path / "feature_ablation.csv"

    stage_manifest._build_paper_ablation_table(  # pylint: disable=protected-access
        source_path=source,
        output_path=output,
    )

    out_df = pd.read_csv(output)
    assert set(out_df["feature_set"].tolist()) == {
        "permissions_only",
        "vendor_only",
        "vendor_permissions_fused",
    }
    assert "full_fused" not in set(out_df["feature_set"].tolist())


def test_build_strict_paper2_exports_skips_when_paper_mode_disabled(tmp_path: Path) -> None:
    """Non-paper runs must not leave paper_exports artifacts."""
    run_root = tmp_path / "output" / "runs" / "rnp"
    diagnostics_dir = run_root / "diagnostics"
    stale = run_root / "paper_exports" / "figures" / "stale.png"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"old")
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    out = stage_manifest._build_strict_paper2_exports(  # pylint: disable=protected-access
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="rnp",
        samples_df=pd.DataFrame(),
        manifest_context={},
        evidence_mode=True,
        paper_mode=False,
    )

    assert out["artifact_paths"] == []
    assert out["profile"]["enabled"] is False
    assert not (run_root / "paper_exports").exists()


def test_build_strict_paper2_exports_writes_machine_manifest(tmp_path: Path, monkeypatch) -> None:
    """Paper exports should include machine-readable manifest."""
    output_root = tmp_path / "output"
    run_id = "rmf"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = _seed_strict_paper2_inputs(run_root, run_id, family_count=12)
    monkeypatch.setattr(stage_manifest.app_config, "PAPER2_STRICT_EXPORT_PROFILE", True, raising=False)

    out = stage_manifest._build_strict_paper2_exports(  # pylint: disable=protected-access
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        samples_df=pd.DataFrame(
            {
                "family_canonical": ["f1", "f1", "f2"],
                "type_slug": ["banker", "banker", "adware"],
                "effective_first_seen_at_utc": ["2020-01-01", "2021-01-01", "2022-01-01"],
            }
        ),
        manifest_context={},
        evidence_mode=False,
        paper_mode=True,
    )

    manifest_path = run_root / "paper_exports" / "docs" / "paper_exports_manifest.json"
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == run_id
    assert len(payload["figure_ids"]) == 5
    assert len(payload["table_ids"]) == 5
    assert (run_root / "paper_exports" / "docs" / "paper_registry.json").exists()
    latex_dir = run_root / "paper_exports" / "tables_latex"
    assert latex_dir.exists()
    assert len(list(latex_dir.glob("*.tex"))) == 5
    assert any(str(path).endswith("paper_exports_manifest.json") for path in out["artifact_paths"])


def test_build_strict_paper2_exports_fails_closed_when_required_artifact_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Missing required paper artifact should fail without creating paper_exports."""
    output_root = tmp_path / "output"
    run_id = "rmiss"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = _seed_strict_paper2_inputs(
        run_root,
        run_id,
        family_count=0,
        include_type_heatmap=False,
        include_jsd_pairs=False,
    )
    monkeypatch.setattr(stage_manifest.app_config, "PAPER2_STRICT_EXPORT_PROFILE", True, raising=False)

    with pytest.raises(ValueError):
        stage_manifest._build_strict_paper2_exports(  # pylint: disable=protected-access
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            samples_df=pd.DataFrame(),
            manifest_context={},
            evidence_mode=False,
            paper_mode=True,
        )

    assert not (run_root / "paper_exports").exists()


def test_build_strict_paper2_exports_cleans_temp_on_late_validation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Late strict-validation failures should leave no partial paper_exports."""
    output_root = tmp_path / "output"
    run_id = "rlate"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = _seed_strict_paper2_inputs(
        run_root,
        run_id,
        family_count=1,
        use_single_family_pair=True,
    )
    monkeypatch.setattr(stage_manifest.app_config, "PAPER2_STRICT_EXPORT_PROFILE", True, raising=False)

    with pytest.raises(ValueError):
        stage_manifest._build_strict_paper2_exports(  # pylint: disable=protected-access
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            samples_df=pd.DataFrame(
                {
                    "family_canonical": ["f1", "f1", "f2"],
                    "type_slug": ["banker", "banker", "adware"],
                    "effective_first_seen_at_utc": ["2020-01-01", "2021-01-01", "2022-01-01"],
                }
            ),
            manifest_context={},
            evidence_mode=False,
            paper_mode=True,
        )

    assert not (run_root / "paper_exports").exists()
    temp_dirs = list(run_root.glob("paper_exports.__tmp__*"))
    assert not temp_dirs
