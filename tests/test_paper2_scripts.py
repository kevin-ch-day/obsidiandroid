"""Tests for research helper scripts."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.research import check_evidence_bundle as check_paper2_freeze
from scripts.research import generate_claim_artifact_map
from scripts.research import mark_legacy_publication_exports as mark_legacy_partial_paper_exports


def _write_paper_registries(paper_docs: Path) -> None:
    """Write canonical paper figure/table registries for freeze checks."""
    figure_name_map = {
        "fig1_pipeline_architecture": "pipeline_architecture.png",
        "fig2_type_permission_heatmap": "type_permission_heatmap.png",
        "fig3_dangerous_permission_distribution_by_type": "dangerous_permission_distribution_by_type.png",
        "fig4_family_jsd_heatmap_top12": "family_jsd_heatmap_top12.png",
        "fig5_confusion_matrix_random_forest": "confusion_matrix_random_forest.png",
    }
    table_name_map = {
        "table1_cohort_summary": "cohort_summary.csv",
        "table2_malware_family_temporal_scope": "malware_family_temporal_scope.csv",
        "table3_model_comparison_rf_xgb_lr_fused": "model_comparison_rf_xgb_lr_fused.csv",
        "table4_feature_ablation": "feature_ablation.csv",
        "table5_dangerous_permission_stats_tests": "dangerous_permission_stats_tests.csv",
    }
    fig_rows = ["figure_id,destination_filename"]
    fig_rows.extend(
        [f"{fid},{figure_name_map[fid]}" for fid in sorted(check_paper2_freeze.EXPECTED_FIGURE_IDS)]
    )
    table_rows = ["table_id,destination_filename"]
    table_rows.extend(
        [f"{tid},{table_name_map[tid]}" for tid in sorted(check_paper2_freeze.EXPECTED_TABLE_IDS)]
    )
    (paper_docs / "paper_figure_registry.csv").write_text(
        "\n".join(fig_rows) + "\n",
        encoding="utf-8",
    )
    (paper_docs / "paper_table_registry.csv").write_text(
        "\n".join(table_rows) + "\n",
        encoding="utf-8",
    )
    blocked_ids = sorted(check_paper2_freeze.EXPECTED_BLOCKED_NON_PAPER_IDS)
    allowed_ids = sorted(check_paper2_freeze.EXPECTED_FIGURE_IDS | check_paper2_freeze.EXPECTED_TABLE_IDS)
    registry_rows = []
    for artifact_id in allowed_ids:
        registry_rows.append(
            {
                "artifact_id": artifact_id,
                "run_id": "test_run",
                "source_path": "src",
                "destination_path": "dst",
                "sha256": "abc123",
                "paper_allowed": True,
                "contract_version": "paper2.v2",
            }
        )
    for artifact_id in blocked_ids:
        registry_rows.append(
            {
                "artifact_id": artifact_id,
                "run_id": "test_run",
                "source_path": "",
                "destination_path": "",
                "sha256": "",
                "paper_allowed": False,
                "contract_version": "paper2.v2",
            }
        )
    (paper_docs / "paper_registry.json").write_text(
        json.dumps({"run_id": "test_run", "contract_version": "paper2.v2", "artifacts": registry_rows}),
        encoding="utf-8",
    )


def _write_bundle_contract_files(run_root: Path) -> None:
    """Write minimal bundle manifest + inventory expected by freeze checks."""
    contracts = run_root / "bundles" / "permission_trends" / "contracts"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    contracts.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    table_path = tables / "type_permission_prevalence.latest.csv"
    table_path.write_text("run_id,type_slug,permission,prevalence\nr,banker,p,0.1\n", encoding="utf-8")
    manifest = {
        "artifacts": [
            {
                "artifact_id": "type_permission_prevalence",
                "category": "table",
                "role": "primary_structural",
                "relative_path": "tables/type_permission_prevalence.latest.csv",
            }
        ]
    }
    (contracts / "permission_trends_bundle_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (contracts / "permission_trends_table_inventory.csv").write_text(
        "run_id,artifact_id,current_filename,role,is_primary,used_by,keep_in_permission_trends,target_location,needs_latex_export,notes\n"
        "r,type_permission_prevalence,type_permission_prevalence.latest.csv,primary_structural,True,paper,bundles,yes,no,ok\n",
        encoding="utf-8",
    )


def test_generate_claim_artifact_map_build_rows(tmp_path: Path, monkeypatch) -> None:
    """Claim-artifact scaffold should read manifest artifacts and build rows."""
    run_id = "r1"
    run_dir = tmp_path / "output" / "runs" / run_id / "diagnostics"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "roots": {"run_root": str((tmp_path / "output" / "runs" / run_id).resolve())},
        "artifacts": {
            "split_audit_csv": {"relpath": "diagnostics/split.csv", "sha256": "abc"},
            "experiment_registry_json": {"relpath": "diagnostics/registry.json", "sha256": "def"},
        },
    }
    manifest_path = run_dir / f"run_paths_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rows = generate_claim_artifact_map.build_rows([run_id])
    assert len(rows) == 2
    assert rows[0]["run_id"] == run_id
    assert rows[0]["artifact_sha256"] in {"abc", "def"}


def test_check_paper2_freeze_reports_fail_when_missing(tmp_path: Path, monkeypatch) -> None:
    """Freeze checker should fail when required artifacts are absent."""
    run_id = "r2"
    run_root = tmp_path / "output" / "runs" / run_id
    (run_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    # Write minimal run_paths manifest with no required artifact entries.
    run_paths = {
        "artifacts": {},
    }
    (run_root / "diagnostics" / f"run_paths_manifest_{run_id}.json").write_text(
        json.dumps(run_paths),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    report = check_paper2_freeze.check_run(run_id)
    assert report["run_id"] == run_id
    assert report["passed"] is False


def test_check_paper2_freeze_reports_pass_when_complete(tmp_path: Path, monkeypatch) -> None:
    """Freeze checker should pass when all required paper artifacts exist."""
    run_id = "r3"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics = run_root / "diagnostics"
    paper_figures = run_root / "paper_exports" / "figures"
    paper_tables = run_root / "paper_exports" / "tables"
    paper_docs = run_root / "paper_exports" / "docs"
    for path in (diagnostics, paper_figures, paper_tables, paper_docs):
        path.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")

    for template in check_paper2_freeze.REQUIRED_DIAGNOSTICS_FILES:
        filename = template.format(run_id=run_id)
        (diagnostics / filename).write_text("{}", encoding="utf-8")

    run_paths = {
        "artifacts": {
            key: {"relpath": f"diagnostics/{key}.json", "sha256": "abc123"}
            for key in check_paper2_freeze.REQUIRED_ARTIFACT_KEYS
        }
    }
    (diagnostics / f"run_paths_manifest_{run_id}.json").write_text(
        json.dumps(run_paths),
        encoding="utf-8",
    )
    _write_bundle_contract_files(run_root)

    for idx in range(5):
        (paper_figures / f"fig_{idx}.png").write_bytes(b"png")
        if idx < 4:
            (paper_tables / f"table_{idx}.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    _write_paper_registries(paper_docs)
    (paper_tables / "model_comparison_rf_xgb_lr_fused.csv").write_text(
        (
            "Model,Accuracy\n"
            "random_forest,0.9\n"
            "xgboost,0.8\n"
            "logistic_regression,0.7\n"
        ),
        encoding="utf-8",
    )
    (diagnostics / f"family_jsd_pairs_verification_{run_id}.csv").write_text(
        "run_id,family_a,family_b,js_distance\n" + "\n".join([f"{run_id},a{i},b{i},0.1" for i in range(66)]),
        encoding="utf-8",
    )
    (diagnostics / f"selected_families_visual_{run_id}.csv").write_text(
        "rank,family_canonical,type_slug,sample_count,selected_reason\n"
        + "\n".join([f"{i},f{i},banker,20,ok" for i in range(1, 13)]),
        encoding="utf-8",
    )
    (diagnostics / f"trained_family_registry_{run_id}.csv").write_text(
        "run_id,family_canonical,type_slug,sample_count,included_in_training\n"
        "r3,f1,banker,20,1\nr3,f2,adware,21,1\n",
        encoding="utf-8",
    )
    (diagnostics / f"confusion_matrix_provenance_{run_id}.csv").write_text(
        "run_id,model_name,eval_source,test_sample_count,trained_family_count,confusion_matrix_path\n"
        f"{run_id},random_forest,test_set,100,12,x.png\n",
        encoding="utf-8",
    )
    (diagnostics / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps({"type_rows_evaluated": 1}),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    report = check_paper2_freeze.check_run(run_id)
    assert report["run_id"] == run_id
    assert report["passed"] is True


def test_check_paper2_freeze_accepts_lowercase_model_column(tmp_path: Path, monkeypatch) -> None:
    """Freeze checker should accept model_comparison table with lowercase model column."""
    run_id = "r4"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics = run_root / "diagnostics"
    paper_figures = run_root / "paper_exports" / "figures"
    paper_tables = run_root / "paper_exports" / "tables"
    paper_docs = run_root / "paper_exports" / "docs"
    for path in (diagnostics, paper_figures, paper_tables, paper_docs):
        path.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    for template in check_paper2_freeze.REQUIRED_DIAGNOSTICS_FILES:
        (diagnostics / template.format(run_id=run_id)).write_text("{}", encoding="utf-8")
    run_paths = {
        "artifacts": {
            key: {"relpath": f"diagnostics/{key}.json", "sha256": "abc123"}
            for key in check_paper2_freeze.REQUIRED_ARTIFACT_KEYS
        }
    }
    (diagnostics / f"run_paths_manifest_{run_id}.json").write_text(json.dumps(run_paths), encoding="utf-8")
    _write_bundle_contract_files(run_root)
    for idx in range(5):
        (paper_figures / f"fig_{idx}.png").write_bytes(b"png")
        if idx < 4:
            (paper_tables / f"table_{idx}.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    _write_paper_registries(paper_docs)
    (paper_tables / "model_comparison_rf_xgb_lr_fused.csv").write_text(
        "model,accuracy\nrandom_forest,0.9\nxgboost,0.8\nlogistic_regression,0.7\n",
        encoding="utf-8",
    )
    (diagnostics / f"family_jsd_pairs_verification_{run_id}.csv").write_text(
        "run_id,family_a,family_b,js_distance\n" + "\n".join([f"{run_id},a{i},b{i},0.1" for i in range(66)]),
        encoding="utf-8",
    )
    (diagnostics / f"selected_families_visual_{run_id}.csv").write_text(
        "rank,family_canonical,type_slug,sample_count,selected_reason\n"
        + "\n".join([f"{i},f{i},banker,20,ok" for i in range(1, 13)]),
        encoding="utf-8",
    )
    (diagnostics / f"trained_family_registry_{run_id}.csv").write_text(
        "run_id,family_canonical,type_slug,sample_count,included_in_training\n"
        "r4,f1,banker,20,1\nr4,f2,adware,21,1\n",
        encoding="utf-8",
    )
    (diagnostics / f"confusion_matrix_provenance_{run_id}.csv").write_text(
        "run_id,model_name,eval_source,test_sample_count,trained_family_count,confusion_matrix_path\n"
        f"{run_id},random_forest,test_set,100,12,x.png\n",
        encoding="utf-8",
    )
    (diagnostics / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps({"type_rows_evaluated": 1}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    report = check_paper2_freeze.check_run(run_id)
    assert report["passed"] is True


def test_check_paper2_freeze_bundle_only_passes_without_paper_exports(
    tmp_path: Path, monkeypatch
) -> None:
    """Bundle-only mode should validate governance without requiring paper_exports."""
    run_id = "r_bundle_only"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics = run_root / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    for template in check_paper2_freeze.REQUIRED_DIAGNOSTICS_FILES:
        (diagnostics / template.format(run_id=run_id)).write_text("{}", encoding="utf-8")
    run_paths = {
        "artifacts": {
            key: {"relpath": f"diagnostics/{key}.json", "sha256": "abc123"}
            for key in check_paper2_freeze.REQUIRED_ARTIFACT_KEYS
        }
    }
    (diagnostics / f"run_paths_manifest_{run_id}.json").write_text(
        json.dumps(run_paths),
        encoding="utf-8",
    )
    _write_bundle_contract_files(run_root)
    (diagnostics / f"family_jsd_pairs_verification_{run_id}.csv").write_text(
        "run_id,family_a,family_b,js_distance\n" + "\n".join([f"{run_id},a{i},b{i},0.1" for i in range(66)]),
        encoding="utf-8",
    )
    (diagnostics / f"selected_families_visual_{run_id}.csv").write_text(
        "rank,family_canonical,type_slug,sample_count,selected_reason\n"
        + "\n".join([f"{i},f{i},banker,20,ok" for i in range(1, 13)]),
        encoding="utf-8",
    )
    (diagnostics / f"trained_family_registry_{run_id}.csv").write_text(
        "run_id,family_canonical,type_slug,sample_count,included_in_training\n"
        "r_bundle_only,f1,banker,20,1\n",
        encoding="utf-8",
    )
    (diagnostics / f"confusion_matrix_provenance_{run_id}.csv").write_text(
        "run_id,model_name,eval_source,test_sample_count,trained_family_count,confusion_matrix_path\n"
        f"{run_id},random_forest,test_set,100,12,x.png\n",
        encoding="utf-8",
    )
    (diagnostics / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps({"type_rows_evaluated": 1}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    report = check_paper2_freeze.check_run(run_id, bundle_only=True)
    assert report["passed"] is True
    assert not any(
        str(item.get("check", "")).startswith("paper_exports:")
        for item in report.get("checks", [])
    )


def test_check_paper2_freeze_fails_on_duplicate_bundle_table_ids(
    tmp_path: Path, monkeypatch
) -> None:
    """Freeze check should fail when bundle manifest repeats a table artifact_id."""
    run_id = "r_dup_ids"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics = run_root / "diagnostics"
    contracts = run_root / "bundles" / "permission_trends" / "contracts"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    for path in (diagnostics, contracts, tables):
        path.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    for template in check_paper2_freeze.REQUIRED_DIAGNOSTICS_FILES:
        (diagnostics / template.format(run_id=run_id)).write_text("{}", encoding="utf-8")
    run_paths = {
        "artifacts": {
            key: {"relpath": f"diagnostics/{key}.json", "sha256": "abc123"}
            for key in check_paper2_freeze.REQUIRED_ARTIFACT_KEYS
        }
    }
    (diagnostics / f"run_paths_manifest_{run_id}.json").write_text(
        json.dumps(run_paths),
        encoding="utf-8",
    )
    (tables / "a.latest.csv").write_text("run_id,x\nr_dup_ids,1\n", encoding="utf-8")
    (tables / "b.latest.csv").write_text("run_id,x\nr_dup_ids,2\n", encoding="utf-8")
    manifest = {
        "artifacts": [
            {"artifact_id": "dup", "category": "table", "role": "primary_structural", "relative_path": "tables/a.latest.csv"},
            {"artifact_id": "dup", "category": "table", "role": "primary_structural", "relative_path": "tables/b.latest.csv"},
        ]
    }
    (contracts / "permission_trends_bundle_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (contracts / "permission_trends_table_inventory.csv").write_text(
        "run_id,artifact_id,current_filename,role,is_primary,used_by,keep_in_permission_trends,target_location,needs_latex_export,notes\n"
        "r_dup_ids,dup,a.latest.csv,primary_structural,True,paper,yes,bundles/permission_trends/tables,no,ok\n",
        encoding="utf-8",
    )
    (diagnostics / f"family_jsd_pairs_verification_{run_id}.csv").write_text(
        "run_id,family_a,family_b,js_distance\n" + "\n".join([f"{run_id},a{i},b{i},0.1" for i in range(66)]),
        encoding="utf-8",
    )
    (diagnostics / f"selected_families_visual_{run_id}.csv").write_text(
        "rank,family_canonical,type_slug,sample_count,selected_reason\n"
        + "\n".join([f"{i},f{i},banker,20,ok" for i in range(1, 13)]),
        encoding="utf-8",
    )
    (diagnostics / f"trained_family_registry_{run_id}.csv").write_text(
        "run_id,family_canonical,type_slug,sample_count,included_in_training\n"
        "r_dup_ids,f1,banker,20,1\n",
        encoding="utf-8",
    )
    (diagnostics / f"confusion_matrix_provenance_{run_id}.csv").write_text(
        "run_id,model_name,eval_source,test_sample_count,trained_family_count,confusion_matrix_path\n"
        f"{run_id},random_forest,test_set,100,12,x.png\n",
        encoding="utf-8",
    )
    (diagnostics / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps({"type_rows_evaluated": 1}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    report = check_paper2_freeze.check_run(run_id, bundle_only=True)
    assert report["passed"] is False
    duplicate_check = next(
        item for item in report["checks"] if item["check"] == "bundle:table_artifact_ids_unique"
    )
    assert duplicate_check["pass"] is False


def test_mark_legacy_partial_paper_exports_marks_only_invalid_runs(
    tmp_path: Path, monkeypatch
) -> None:
    """Legacy marker should be written only for invalid paper-export runs."""
    output_root = tmp_path / "output"
    valid_dir = output_root / "runs" / "valid_run" / "paper_exports"
    invalid_dir = output_root / "runs" / "invalid_run" / "paper_exports"
    valid_dir.mkdir(parents=True, exist_ok=True)
    invalid_dir.mkdir(parents=True, exist_ok=True)

    def _fake_check_run(run_id: str) -> dict:
        return {"run_id": run_id, "passed": run_id == "valid_run"}

    monkeypatch.setattr(check_paper2_freeze, "check_run", _fake_check_run)
    rows = mark_legacy_partial_paper_exports.mark_legacy_runs(output_root=output_root)
    by_id = {row["run_id"]: row for row in rows}

    assert by_id["valid_run"]["status"] == "valid_publication_exports"
    assert not (valid_dir / mark_legacy_partial_paper_exports.MARKER_FILE).exists()
    assert by_id["invalid_run"]["status"] == "marked_invalid_partial"
    assert (invalid_dir / mark_legacy_partial_paper_exports.MARKER_FILE).exists()
