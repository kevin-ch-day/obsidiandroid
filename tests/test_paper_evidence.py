"""Tests for strict paper-evidence helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

from obsidiandroid.governance.paper_constants import (
    build_paper_constants_payload,
    write_paper_constants,
)
from obsidiandroid.pipeline import stage_manifest
from obsidiandroid.pipeline.manifest import paper_compliance_checks
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
from obsidiandroid.pipeline.manifest.paper_evidence import (
    build_feature_set_glossary_payload,
    build_promoted_paper_model_binding,
    validate_paper_contract_bundle,
    validate_perturbation_summary_rows,
)
from obsidiandroid.pipeline.manifest import paper_figure_renderers as pfr
from obsidiandroid.pipeline.manifest.paper_export_registry import build_paper_registry_payload

build_paper_compliance_checks = paper_compliance_checks.build_paper_compliance_checks


def _matched_contract() -> dict:
    return {
        "paper_locked": True,
        "profile_id": "malicious_temporal_stability_locked",
        "contract_id": "malicious_temporal_stability_locked_contract",
        "expected": {
            "sample_count": 3,
            "family_count": 2,
            "type_count": 1,
            "time_window_start_utc": "2020-01-01T00:00:00Z",
            "time_window_end_utc": "2026-01-01T00:00:00Z",
            "time_window_semantics": "start_inclusive_end_exclusive",
        },
        "sample_id_lock": {
            "cohort_hash": "cohort123",
            "taxonomy_hash": "tax123",
        },
        "validation": {"status": "match"},
    }


def test_validate_paper_contract_bundle_detects_count_mismatch(tmp_path: Path) -> None:
    """Mismatched paper constants should fail validation."""
    paper_constants_path = tmp_path / "paper_constants.json"
    manuscript_constants_path = tmp_path / "manuscript_constants.json"
    paper_constants_path.write_text(
        json.dumps(
            {
                "sample_count": 1226,
                "family_count": 39,
                "malware_type_count": 6,
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    manuscript_constants_path.write_text(
        json.dumps(
            {
                "sample_count": 1187,
                "family_count": 39,
                "type_count": 6,
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
                "label_vocabulary": {
                    "training_label_field": "family_id",
                    "display_label_field": "family_canonical",
                },
            }
        ),
        encoding="utf-8",
    )
    payload = validate_paper_contract_bundle(
        profile={
            "profile_id": "malicious_temporal_stability_locked",
            "paper_lock": {
                "expected_sample_count": 1226,
                "expected_family_count": 39,
                "expected_type_count": 6,
                "time_window_start_utc": "2020-01-01T00:00:00Z",
                "time_window_end_utc": "2026-01-01T00:00:00Z",
            },
        },
        manifest={
            "paper_cohort_summary": {
                "sample_count": 1226,
                "family_count": 39,
                "type_count": 6,
            }
        },
        paper_constants_path=paper_constants_path,
        manuscript_constants_path=manuscript_constants_path,
    )
    assert payload["passed"] is False
    failed_fields = {row["field"] for row in payload["checks"] if not row["passed"]}
    assert "sample_count" in failed_fields


def test_validate_perturbation_summary_rows_requires_split_and_cohort_hash() -> None:
    """Perturbation rows must carry split_hash and cohort_hash."""
    with pytest.raises(ValueError, match="split_hash/cohort_hash"):
        validate_perturbation_summary_rows(
            [
                {
                    "run_id": "r1",
                    "profile_id": "malicious_temporal_stability",
                    "split_hash": "",
                    "cohort_hash": "cohort123",
                }
            ]
        )


def test_build_promoted_paper_model_binding_requires_matching_prediction_split_hash(tmp_path: Path) -> None:
    """Promoted prediction CSV split hash must match manifest split hash."""
    run_id = "r1"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "confusion_matrix_primary.png").write_bytes(b"png")
    pd.DataFrame(
        [
            {"sample_id": 1, "split_hash": "bad", "predicted_label_name": "FamA", "true_label_name": "FamA"},
        ]
    ).to_csv(diagnostics_dir / f"headline_test_predictions_{run_id}.csv", index=False)
    (diagnostics_dir / f"headline_test_errors_{run_id}.csv").write_text("", encoding="utf-8")
    (diagnostics_dir / f"evaluation_contract_{run_id}.json").write_text(
        json.dumps({"feature_contract": {"headline_feature_column_hash": "feat123"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="prediction split_hash mismatch"):
        build_promoted_paper_model_binding(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            manifest={
                "run_id": run_id,
                "split": {"split_hash": "good"},
                "model_summary": {"top_model": "xgboost"},
                "cohort_contract": {"sample_id_lock": {"cohort_hash": "cohort123", "taxonomy_hash": "tax123"}},
            },
            evidence_mode=False,
        )


def test_build_promoted_paper_model_binding_records_manifest_split_hash(tmp_path: Path) -> None:
    """Promoted binding should preserve manifest split hash for confusion/prediction evidence."""
    run_id = "r2"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "confusion_matrix_primary.png").write_bytes(b"png")
    pd.DataFrame(
        [
            {"sample_id": 1, "split_hash": "aa" * 32, "predicted_label_name": "FamA", "true_label_name": "FamA"},
        ]
    ).to_csv(diagnostics_dir / f"headline_test_predictions_{run_id}.csv", index=False)
    (diagnostics_dir / f"headline_test_errors_{run_id}.csv").write_text("", encoding="utf-8")
    (diagnostics_dir / f"evaluation_contract_{run_id}.json").write_text(
        json.dumps({"feature_contract": {"headline_feature_column_hash": "feat123"}}),
        encoding="utf-8",
    )
    payload = build_promoted_paper_model_binding(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        manifest={
            "run_id": run_id,
            "split": {"split_hash": "aa" * 32, "split_audit_path": "split.csv"},
            "model_summary": {"top_model": "xgboost"},
            "model_config_hash": "model123",
            "cohort_contract": {"sample_id_lock": {"cohort_hash": "cohort123", "taxonomy_hash": "tax123"}},
        },
        evidence_mode=False,
    )
    assert payload["split_hash"] == "aa" * 32
    assert payload["confusion_matrix_split_hash"] == "aa" * 32
    assert payload["heldout_predictions_split_hash"] == "aa" * 32
    assert payload["label_target"] == "family_id"
    assert payload["display_label_field"] == "family_canonical"
    display_policy = payload["paper_family_display_policy"]
    assert display_policy["policy_id"] == "android_paper_family_display_policy"
    assert display_policy["family_confusion_matrix"]["top_k_major_families"] == 12


def test_feature_set_glossary_uses_paper_label_vocabulary() -> None:
    """Paper-facing glossary should keep family_id/family_canonical vocabulary."""
    payload = build_feature_set_glossary_payload()
    assert payload["label_vocabulary"]["training_label_field"] == "family_id"
    assert payload["label_vocabulary"]["display_label_field"] == "family_canonical"
    names = {row["paper_feature_set"] for row in payload["feature_sets"]}
    assert names == {"permissions_only", "vendor_only", "vendor_permissions_fused"}


def test_write_evaluation_contract_json_preserves_promoted_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Evaluation contract should surface the promoted paper-model binding."""
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    family_tier_csv = diagnostics_dir / "family_tier_model_evaluation_r3.csv"
    family_tier_csv.write_text("model,evaluation_scope,sample_count\nrf,major,10\n", encoding="utf-8")
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "feat123", raising=False)
    monkeypatch.setattr(stage_manifest.app_config, "RUNTIME_HEADLINE_FEATURE_CONTRACT_PATH", "feature_contract.json", raising=False)
    out_path = stage_manifest._write_evaluation_contract_json(  # pylint: disable=protected-access
        diagnostics_dir=diagnostics_dir,
        run_id="r3",
        manifest={
            "split": {"split_hash": "aa" * 32},
            "promoted_paper_model": {
                "model": "xgboost",
                "split_hash": "aa" * 32,
                "confusion_matrix_path": "/tmp/conf.png",
                "heldout_predictions_csv": "/tmp/preds.csv",
            },
            "model_summary": {
                "top_model": "xgboost",
                "top_model_family_tier_rows": [
                    {"model": "xgboost", "evaluation_scope": "major", "sample_count": 10}
                ],
            },
        },
        manifest_context={"label_authority": {"training_label_field": "family_id"}},
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["promoted_paper_model"]["model"] == "xgboost"
    assert payload["promoted_paper_model"]["split_hash"] == "aa" * 32
    assert payload["family_tier_evaluation"]["csv_exists"] is True
    assert payload["family_tier_evaluation"]["top_model_rows"][0]["evaluation_scope"] == "major"


def test_build_paper_constants_requires_split_and_cohort_hash() -> None:
    contract = _matched_contract()
    contract["sample_id_lock"]["cohort_hash"] = ""
    with pytest.raises(ValueError, match="cohort_hash"):
        build_paper_constants_payload(
            run_id="r1",
            profile_id="malicious_temporal_stability_locked",
            cohort_contract=contract,
            split_hash="split123",
            samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["FamA"]}),
        )


def test_write_paper_constants_rejects_count_mismatch(tmp_path: Path) -> None:
    out_root = tmp_path
    contract = _matched_contract()
    paper_dir = out_root / "artifacts" / "paper"
    paper_dir.mkdir(parents=True)
    existing = {
        "sample_count": 99,
        "family_count": 2,
        "malware_type_count": 1,
        "cohort_hash": "cohort123",
    }
    (paper_dir / "paper_constants.json").write_text(json.dumps(existing), encoding="utf-8")
    with pytest.raises(ValueError, match="sample_count"):
        write_paper_constants(
            run_id="r1",
            profile_id="malicious_temporal_stability_locked",
            cohort_contract=contract,
            split_hash="split123",
            samples_df=pd.DataFrame(
                {
                    "sample_id": [1, 2, 3],
                    "family_canonical": ["FamA", "FamA", "FamB"],
                }
            ),
            output_root=out_root,
        )


def test_compliance_checks_skipped_when_paper_mode_off(tmp_path: Path) -> None:
    checks = build_paper_compliance_checks(
        paper_mode=False,
        split_hash="",
        cohort_hash="",
        split_audit_path="",
        duplicate_report_path="",
        duplicate_count=0,
        invalid_sha_count=0,
        vendor_gate_debug_path="",
        run_paths_manifest_path="",
        experiment_registry_path=str(tmp_path / "missing.json"),
        taxonomy_summary_path="",
        taxonomy_type_rows_evaluated=0,
    )
    assert len(checks) == 9
    assert all(c["status"] == "skipped" for c in checks)


def test_split_hash_required_when_paper_mode_on(tmp_path: Path) -> None:
    checks = build_paper_compliance_checks(
        paper_mode=True,
        split_hash="",
        cohort_hash="cohort123",
        split_audit_path="",
        duplicate_report_path="",
        duplicate_count=0,
        invalid_sha_count=0,
        vendor_gate_debug_path="",
        run_paths_manifest_path="",
        experiment_registry_path=str(tmp_path / "reg.json"),
        taxonomy_summary_path="",
        taxonomy_type_rows_evaluated=0,
    )
    first = checks[0]
    assert first["check_id"] == "split_hash_present"
    assert first["status"] == "fail"


def test_cohort_hash_required_when_paper_mode_on(tmp_path: Path) -> None:
    checks = build_paper_compliance_checks(
        paper_mode=True,
        split_hash="split123",
        cohort_hash="",
        split_audit_path="",
        duplicate_report_path="",
        duplicate_count=0,
        invalid_sha_count=0,
        vendor_gate_debug_path="",
        run_paths_manifest_path="",
        experiment_registry_path=str(tmp_path / "reg.json"),
        taxonomy_summary_path="",
        taxonomy_type_rows_evaluated=0,
    )
    cohort_check = next(row for row in checks if row["check_id"] == "cohort_hash_present")
    assert cohort_check["status"] == "fail"


def test_annotate_confusion_matrix_strips_csv_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "m.csv"
    csv_path.write_text(
        " Model , MacroF1 , Acc , F1-Score \nrf,0.9,0.91,0.88\n",
        encoding="utf-8",
    )
    png_path = tmp_path / "cm.png"
    Image.new("RGB", (80, 80), color=(200, 200, 200)).save(png_path)
    assert pfr.annotate_confusion_matrix_with_metrics(
        confusion_path=png_path,
        model_comparison_csv=csv_path,
    )


def test_annotate_confusion_matrix_without_weighted_f1_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "m.csv"
    csv_path.write_text("Model,MacroF1,Acc\nrf,0.9,0.91\n", encoding="utf-8")
    png_path = tmp_path / "cm.png"
    Image.new("RGB", (80, 80), color=(200, 200, 200)).save(png_path)
    assert pfr.annotate_confusion_matrix_with_metrics(
        confusion_path=png_path,
        model_comparison_csv=csv_path,
    )


def test_first_column_match_is_case_insensitive() -> None:
    cols = pd.Index(["macrof1", "ACC"])
    assert pfr._first_column_match(cols, ("MacroF1",)) == "macrof1"
    assert pfr._first_column_match(cols, ("Accuracy", "Acc")) == "ACC"


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
