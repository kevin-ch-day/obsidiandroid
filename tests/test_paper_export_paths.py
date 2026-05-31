from __future__ import annotations

from pathlib import Path

from obsidiandroid.pipeline.manifest.paper_export_contracts import (
    build_paper_export_contract,
    missing_required_paper_sources,
)
from obsidiandroid.pipeline.manifest.paper_export_paths import (
    build_paper_export_settings,
    build_paper_docs_paths,
    build_paper_export_profile_payload,
    build_paper_exports_manifest_payload,
)
from obsidiandroid.pipeline.manifest.paper_export_registry import build_paper_registry_payload


def test_build_paper_docs_paths_uses_canonical_filenames(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    payload = build_paper_docs_paths(docs_dir=docs_dir)

    assert payload["manuscript_table_constants_json"] == docs_dir / "manuscript_table_constants.json"
    assert payload["feature_set_glossary_json"] == docs_dir / "feature_set_glossary.json"
    assert payload["feature_set_glossary_md"] == docs_dir / "feature_set_glossary.md"
    assert payload["perturbation_summary_csv"] == docs_dir / "perturbation_summary.csv"
    assert payload["perturbation_summary_json"] == docs_dir / "perturbation_summary.json"
    assert payload["perturbation_summary_md"] == docs_dir / "perturbation_summary.md"
    assert payload["paper_contract_validation_json"] == docs_dir / "paper_contract_validation.json"


def test_build_paper_export_profile_payload_reuses_docs_contract(tmp_path: Path) -> None:
    docs_paths = build_paper_docs_paths(docs_dir=tmp_path / "docs")

    payload = build_paper_export_profile_payload(
        strict_profile=True,
        run_id="rid",
        contract_version="v1",
        visual_family_support_threshold=20,
        top_families_visual=12,
        top_permissions=16,
        docs_paths=docs_paths,
    )

    assert payload["single_run_id"] == "rid"
    assert payload["paper_export_contract_version"] == "v1"
    assert payload["manuscript_table_constants_path"] == str(
        docs_paths["manuscript_table_constants_json"].resolve()
    )
    assert payload["perturbation_summary_json"] == str(
        docs_paths["perturbation_summary_json"].resolve()
    )


def test_build_paper_export_settings_normalizes_thresholds() -> None:
    class Config:
        MIN_FAMILY_SUPPORT_FOR_VISUAL = "21"
        MAX_FAMILY_VISUAL_COUNT = "13"
        MAX_PERMISSIONS_HEATMAP = "17"

    payload = build_paper_export_settings(app_config_obj=Config())

    assert payload == {
        "visual_family_support_threshold": 21,
        "top_families_visual": 13,
        "top_permissions": 17,
    }


def test_build_paper_exports_manifest_payload_tracks_contract_validation_presence(tmp_path: Path) -> None:
    docs_paths = build_paper_docs_paths(docs_dir=tmp_path / "docs")
    manifest = build_paper_exports_manifest_payload(
        run_id="rid",
        contract_version="v1",
        strict_profile=False,
        figure_registry_path=tmp_path / "fig.csv",
        table_registry_path=tmp_path / "tab.csv",
        profile_path=docs_paths["paper_export_profile_json"],
        paper_registry_path=docs_paths["paper_registry_json"],
        latex_dir=tmp_path / "latex",
        figure_registry_rows=[{"figure_id": "f1"}],
        table_registry_rows=[{"table_id": "t1"}],
        figure_inputs={"f1": "src.png"},
        table_inputs={"t1": "src.csv"},
        docs_paths=docs_paths,
        validation_summary={"ok": True},
        contract_validation_written=False,
    )

    assert manifest["manuscript_table_constants_json"] == str(
        docs_paths["manuscript_table_constants_json"].resolve()
    )
    assert manifest["paper_contract_validation_json"] == ""
    assert manifest["figure_ids"] == ["f1"]
    assert manifest["table_ids"] == ["t1"]


def test_build_paper_registry_payload_includes_blocked_and_allowed_artifacts(tmp_path: Path) -> None:
    figure_path = tmp_path / "figure.png"
    figure_path.write_bytes(b"png-bytes")
    table_path = tmp_path / "table.csv"
    table_path.write_text("a,b\n1,2\n", encoding="utf-8")

    payload = build_paper_registry_payload(
        run_root=tmp_path,
        run_id="rid",
        contract_version="v1",
        figure_registry_rows=[
            {
                "figure_id": "fig1",
                "destination_path": str(figure_path),
                "destination_filename": "figure.png",
                "source_path": "source.png",
            }
        ],
        table_registry_rows=[
            {
                "table_id": "tab1",
                "destination_path": str(table_path),
                "destination_filename": "table.csv",
                "source_path": "source.csv",
            }
        ],
        latex_paths={"tab1": "table.tex"},
        blocked_non_paper_ids={"blocked1"},
    )

    artifacts = payload["artifacts"]
    assert [item["artifact_id"] for item in artifacts] == ["blocked1", "fig1", "tab1"]
    assert any(item["artifact_type"] == "figure" and item["paper_allowed"] is True for item in artifacts)
    assert any(item["artifact_type"] == "table" and item["latex_path"].endswith("table.tex") for item in artifacts)
    assert any(item["artifact_type"] == "blocked_non_paper" and item["paper_allowed"] is False for item in artifacts)


def test_build_paper_export_contract_resolves_required_sources(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    diagnostics_dir = run_root / "diagnostics"
    bundle_tables = run_root / "bundles" / "permission_trends" / "tables"
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True)
    bundle_tables.mkdir(parents=True)
    conf_dir.mkdir(parents=True)

    (diagnostics_dir / "model_comparison_summary_rid.csv").write_text("model,macro_f1,accuracy\n", encoding="utf-8")
    (diagnostics_dir / "ablation_summary_rid.csv").write_text("feature_set,model,macro_f1\n", encoding="utf-8")
    (diagnostics_dir / "family_jsd_pairs_verification_rid.csv").write_text("family_a,family_b\n", encoding="utf-8")
    (bundle_tables / "dangerous_stats_tests_rid.csv").write_text("metric,p_value\n", encoding="utf-8")
    (bundle_tables / "type_permission_prevalence_rid.csv").write_text("type_slug,permission,prevalence\n", encoding="utf-8")
    (bundle_tables / "permission_discriminability_rank_rid.csv").write_text("permission,score\n", encoding="utf-8")
    (bundle_tables / "dangerous_distribution_by_type_rid.csv").write_text("type_slug,value\n", encoding="utf-8")
    (conf_dir / "confusion_matrix_random_forest.png").write_bytes(b"png")

    payload = build_paper_export_contract(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="rid",
        evidence_mode=True,
    )

    assert "fig1_pipeline_architecture" in payload["required_figure_ids"]
    assert payload["table_sources"]["table4_feature_ablation"].name == "ablation_summary_rid.csv"
    assert payload["figure_filename_map"]["fig5_confusion_matrix_random_forest"] == "confusion_matrix_random_forest.png"
    assert missing_required_paper_sources(payload["required_sources"]) == []
