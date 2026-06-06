"""Lightweight observability artifact tests."""

from __future__ import annotations

import json
from pathlib import Path

from config import app_config
from obsidiandroid.observability.pipeline_observability.finalize import (
    finalize_pipeline_observability,
    patch_observability_scientific_adequacy_from_dataset_foundation,
)
from obsidiandroid.observability.pipeline_observability.logging_audit import write_logging_audit_artifacts
from obsidiandroid.observability.pipeline_observability.session import PipelineObservabilitySession
from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory


def test_write_logging_audit_artifacts_writes(tmp_path: Path) -> None:
    md, csv_p = write_logging_audit_artifacts(tmp_path, run_id="t1")
    assert md.exists()
    assert csv_p.exists()
    txt = md.read_text(encoding="utf-8")
    assert "severity" in txt.lower()


def test_pipeline_observability_session_writes_stage_start(tmp_path: Path) -> None:
    sess = PipelineObservabilitySession(diagnostics_dir=tmp_path, run_id="r1")
    sess.emit_stage_start("samples")
    jl = tmp_path / "pipeline_events.jsonl"
    txt = jl.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert LogCategory.STAGE_START.value in txt
    assert "samples" in txt


def test_pipeline_observability_session_stage_end_includes_stage_field(tmp_path: Path) -> None:
    """STAGE_END must mirror STAGE_START (``stage`` field) for JSONL consumers."""
    sess = PipelineObservabilitySession(diagnostics_dir=tmp_path, run_id="r1")
    sess.emit_stage_completion("training", status="PASS", duration_sec=1.5)
    jl = tmp_path / "pipeline_events.jsonl"
    blob = json.loads(jl.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert blob.get("category") == LogCategory.STAGE_END.value
    assert blob.get("stage") == "training"
    assert blob.get("message") == "training"


def test_finalize_pipeline_observability_minimal(tmp_path: Path) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {"run_id": "r_z", "_observability_finalized_once": False}
    manifest = {"run_id": "r_z", "cohort_size": 10}
    artifact_list: list[str] = []
    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="p1",
    )
    assert isinstance(out_path, Path)
    summary = diagnostic / "run_observability_summary.json"
    assert summary.exists()
    assert not (diagnostic / "pipeline_observability_status.json").exists()
    txt = summary.read_text(encoding="utf-8")
    assert "pipeline_status" in txt and "schema_version" in txt
    blob = json.loads(txt)
    paths = blob.get("paths") if isinstance(blob.get("paths"), dict) else {}
    assert "run_observability_summary_json" in paths
    assert "pipeline_observability_status_json" not in paths
    assert blob.get("publication_ready_status") == "NOT_APPLICABLE"
    assert blob.get("publication_ready_reasons") == []
    assert blob.get("run_status") == "complete"
    assert blob.get("completed_stage") == "manifest"
    assert ctx["_observability_finalized_once"] is True


def test_finalize_pipeline_observability_records_skip_reasons(tmp_path: Path) -> None:
    """Skipped audit bundles should carry explicit skip reasons into the summary JSON."""
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": "r_skip",
        "_observability_finalized_once": False,
        "_research_bundle_skipped_reason": "stop_after_samples",
        "_hostile_bundle_skipped_reason": "stop_after_samples",
    }
    manifest = {"run_id": "r_skip", "cohort_size": 5}
    artifact_list: list[str] = []

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="p_skip",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("research_validity_status") == "SKIPPED"
    assert blob.get("research_validity_skip_reason") == "stop_after_samples"
    assert blob.get("hostile_audit_status") == "SKIPPED"
    assert blob.get("hostile_audit_skip_reason") == "stop_after_samples"


def test_finalize_pipeline_observability_marks_integrity_stop_as_terminal_failure(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": "r_integrity",
        "_observability_finalized_once": False,
        "run_status": "failed",
        "completed_stage": "unknown",
        "failure_reason": "[INTEGRITY] non-run-scoped artifacts detected: logs/runtime/r1/pipeline_runtime_console_r1.log",
        "integrity_error": "[INTEGRITY] non-run-scoped artifacts detected: logs/runtime/r1/pipeline_runtime_console_r1.log",
    }
    manifest = {"run_id": "r_integrity", "cohort_size": 5}

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "not_applicable"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="android_malware_major_families",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("run_status") == "failed"
    assert blob.get("pipeline_status") == "INTEGRITY_STOP"


def test_finalize_pipeline_observability_preserves_interrupted_status(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": "r_interrupt",
        "_observability_finalized_once": False,
        "run_status": "interrupted",
        "completed_stage": "permission_trends",
        "failed_stage": "permission_trends",
        "failure_reason": "KeyboardInterrupt",
        "error_type": "KeyboardInterrupt",
        "run_mode": "diagnostic",
        "run_slot": "allcurrent_diagnostic",
        "run_instance_id": "r_interrupt",
    }
    manifest = {"run_id": "r_interrupt", "cohort_size": 5}

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=130,
        profile_id="android_malware_all_current",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("run_status") == "interrupted"
    assert blob.get("pipeline_status") == "INTERRUPTED"


def test_finalize_pipeline_observability_uses_benchmark_claim_audit_for_benchmark_profile(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": "r_bench_claim",
        "_observability_finalized_once": False,
    }
    manifest = {"run_id": "r_bench_claim", "cohort_size": 5}

    finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="android_malware_major_families",
    )

    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("claim_audit_summary", "").endswith("benchmark_claim_audit.md")
    assert blob.get("claim_surface_label") == "Support-gated benchmark cohort"


def test_finalize_pipeline_observability_uses_publication_claim_audit_for_publication_mode(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": "r_pub_claim",
        "_observability_finalized_once": False,
    }
    manifest = {"run_id": "r_pub_claim", "cohort_size": 5}

    finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "pass"},
        paper_mode=True,
        evidence_mode=True,
        result_code=0,
        profile_id="malicious_temporal_stability_locked",
    )

    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("claim_audit_summary", "").endswith("publication_claim_audit.md")
    assert blob.get("claim_surface_label") == "Locked publication cohort"


def test_finalize_pipeline_observability_uses_research_claim_audit_for_expanded_profile(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    (diagnostic / "benchmark_claim_audit.md").write_text("benchmark\n", encoding="utf-8")
    (diagnostic / "research_claim_audit.md").write_text("research\n", encoding="utf-8")
    ctx = {
        "run_id": "r_expanded_claim",
        "_observability_finalized_once": False,
    }
    manifest = {"run_id": "r_expanded_claim", "cohort_size": 5}

    finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="android_malware_expanded_families",
    )

    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("claim_audit_summary", "").endswith("research_claim_audit.md")
    assert blob.get("claim_surface_label") == "Expanded-family exploratory cohort"
    top_open = list(blob.get("top_artifacts_to_open_first") or [])
    assert any(path.endswith("research_claim_audit.md") for path in top_open)
    research_ix = next(ix for ix, path in enumerate(top_open) if path.endswith("research_claim_audit.md"))
    benchmark_ix = next(ix for ix, path in enumerate(top_open) if path.endswith("benchmark_claim_audit.md"))
    assert research_ix < benchmark_ix


def test_finalize_pipeline_observability_marks_audit_bundles_partial_on_interrupted_run(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": "r_interrupted_partial",
        "_observability_finalized_once": False,
        "run_status": "interrupted",
        "completed_stage": "training",
        "failed_stage": "permission_trends",
        "error_type": "KeyboardInterrupt",
    }
    manifest = {"run_id": "r_interrupted_partial", "cohort_size": 5}

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=130,
        profile_id="android_malware_all_current",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("pipeline_status") == "INTERRUPTED"
    assert blob.get("research_validity_status") == "PASS_PARTIAL"
    assert blob.get("hostile_audit_status") == "PASS_PARTIAL"
    assert blob.get("completed_stage") == "training"


def test_finalize_pipeline_observability_labels_skeptic_audit_in_partial_failures(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    (diagnostic / "hostile_audit_partial_errors.txt").write_text("step failed\n", encoding="utf-8")
    ctx = {"run_id": "r_skeptic", "_observability_finalized_once": False}
    manifest = {"run_id": "r_skeptic", "cohort_size": 5}

    finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="android_malware_major_families",
    )

    text = (diagnostic / "partial_failures.md").read_text(encoding="utf-8")
    assert "## Skeptic audit" in text
    assert "## Hostile audit" not in text


def test_finalize_pipeline_observability_records_compact_artifact_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {"run_id": "r_compact", "_observability_finalized_once": False}
    manifest = {"run_id": "r_compact", "cohort_size": 5}
    artifact_list: list[str] = []

    monkeypatch.setattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_RESEARCH_VALIDITY_BUNDLE", False, raising=False)

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="dev_fast",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("verbose_run_artifacts") is False
    assert blob.get("research_validity_bundle_enabled") is False
    assert blob.get("row_authority") is None
    assert not any("paper_mode_compliance_report" in str(item) for item in (blob.get("top_artifacts_to_open_first") or []))


def test_finalize_pipeline_observability_propagates_row_authority_from_context(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": "r_auth",
        "_observability_finalized_once": False,
        "main_training_row_authority": "governed_cohort",
    }
    manifest = {"run_id": "r_auth", "cohort_size": 5}
    artifact_list: list[str] = []

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="dev_fast",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("main_training_row_authority") == "governed_cohort"
    assert blob.get("row_authority") == "governed_cohort"


def test_finalize_pipeline_observability_falls_back_to_feature_matrix_row_authority(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": "r_auth_fallback",
        "_observability_finalized_once": False,
        "feature_matrix_row_authority": "governed_cohort",
    }
    manifest = {"run_id": "r_auth_fallback", "cohort_size": 5}
    artifact_list: list[str] = []

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="dev_fast",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("main_training_row_authority") == "governed_cohort"
    assert blob.get("row_authority") == "governed_cohort"


def test_finalize_pipeline_observability_includes_label_strategy_when_present(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    (diagnostic / "taxonomy_target_surfaces_r_labels.json").write_text(
        json.dumps(
            {
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                    "avoid_for_primary_claims": ["category_primary"],
                    "alignment_interpretation": "Raw subtype aligns materially better than raw primary.",
                }
            }
        ),
        encoding="utf-8",
    )
    ctx = {
        "run_id": "r_labels",
        "_observability_finalized_once": False,
        "feature_matrix_row_authority": "governed_cohort",
    }
    manifest = {"run_id": "r_labels", "cohort_size": 5}
    artifact_list: list[str] = []

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="dev_fast",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("label_strategy", {}).get("preferred_family_target") == "family_id"
    assert blob.get("label_strategy", {}).get("preferred_type_target") == "type_slug"
    assert blob.get("label_strategy", {}).get("avoid_for_primary_claims") == ["category_primary"]


def test_finalize_pipeline_observability_includes_label_resolution_and_type_guard_counts(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    run_id = "r_guard"
    (diagnostic / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps({"type_guard_family_suppressed_count": 3}),
        encoding="utf-8",
    )
    ctx = {
        "run_id": run_id,
        "_observability_finalized_once": False,
        "label_resolution_enabled": True,
    }
    manifest = {"run_id": run_id, "cohort_size": 5}
    artifact_list: list[str] = []

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="dev_fast",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("label_resolution_enabled") is True
    assert blob.get("type_guard_family_suppressed_count") == 3


def test_finalize_pipeline_observability_includes_stage_loss_summaries(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    run_id = "r_stage_losses"
    ctx = {
        "run_id": run_id,
        "_observability_finalized_once": False,
        "alignment_attrition_stats": {
            "alignment_non_authoritative_family_drop_count": 4,
            "alignment_live_authority_rescue_count": 179,
        },
        "alignment_attrition_details": {
            "alignment_live_authority_rescue_families": {"Applite": 159, "Wroba": 15, "Piom": 5},
            "alignment_non_authoritative_family_drop_families": {"unknown_family": 4},
        },
        "low_support_family_drop_detail": [
            {"family": "BrowBot", "aligned_support": 1},
            {"family": "GINP", "aligned_support": 1},
            {"family": "BRATA", "aligned_support": 2},
        ],
        "split": {
            "temporal_split_summary": {
                "test_rows_dropped_unseen_train_classes": 7,
                "test_rows_dropped_unseen_train_class_families": {"Zanubis": 4, "Alien": 3},
            }
        },
    }
    manifest = {"run_id": run_id, "cohort_size": 5}

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "pass"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="dev_fast",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("alignment_non_authoritative_family_drop_count") == 4
    assert blob.get("alignment_live_authority_rescue_count") == 179
    assert blob.get("alignment_live_authority_rescue_families_top") == "Applite=159, Wroba=15, Piom=5"
    assert blob.get("alignment_non_authoritative_family_drops_top") == "unknown_family=4"
    assert blob.get("low_support_family_drop_count") == 3
    assert blob.get("low_support_row_drop_count") == 4
    assert blob.get("low_support_family_drops_top") == "BrowBot=1, GINP=1, BRATA=2"
    assert blob.get("temporal_future_only_family_drops_top") == "Zanubis=4, Alien=3"


def test_finalize_pipeline_observability_marks_sample_only_science_as_not_assessed(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    run_id = "r_samples_only"
    (diagnostic / f"taxonomy_target_surfaces_{run_id}.json").write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "surface_name": "family_id",
                        "unique_classes": 115,
                        "trainable_classes_at_min_support": 80,
                    },
                    {
                        "surface_name": "type_slug",
                        "unique_classes": 6,
                        "trainable_classes_at_min_support": 6,
                    },
                ],
                "benchmark_support_policy": {
                    "benchmark_min_support": 3,
                    "excluded_below_support_family_count": 2,
                    "excluded_below_support_families": [
                        {"family_canonical": "ginp", "sample_count": 1},
                        {"family_canonical": "marcher", "sample_count": 1},
                    ],
                },
                "tier_counts": {
                    "excluded_below_benchmark_support_samples": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    ctx = {
        "run_id": run_id,
        "_observability_finalized_once": False,
        "run_status": "partial",
        "completed_stage": "samples",
    }
    manifest = {"run_id": run_id, "cohort_size": 1231}

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=[],
        compliance_report={"overall_status": "not_applicable"},
        paper_mode=False,
        evidence_mode=False,
        result_code=0,
        profile_id="android_malware_major_families",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert blob.get("scientific_adequacy", {}).get("posture") == "Not assessed"
    assert blob.get("scientific_adequacy", {}).get("blockers") == []
    assert blob.get("benchmark_support_floor") == 3
    assert blob.get("benchmark_support_excluded_sample_count") == 2
    assert blob.get("benchmark_support_excluded_family_count") == 2
    assert blob.get("benchmark_support_excluded_families_top") == "ginp=1, marcher=1"
    assert blob.get("visible_family_count") == 115
    assert blob.get("benchmark_trainable_family_count") == 80
    assert blob.get("visible_type_count") == 6


def test_finalize_pipeline_observability_adds_temporal_split_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {"run_id": "r_temp", "_observability_finalized_once": False}
    manifest = {"run_id": "r_temp", "cohort_size": 5}
    artifact_list: list[str] = []

    monkeypatch.setattr(
        app_config,
        "RUNTIME_LAST_SPLIT_ALGORITHM",
        "stratified_seeded",
        raising=False,
    )

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=True,
        evidence_mode=True,
        result_code=0,
        profile_id="malicious_temporal_stability_locked",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    warnings = blob.get("research_warnings_top") or []
    assert any("non-temporal split algorithm stratified_seeded" in str(item) for item in warnings)


def test_finalize_pipeline_observability_adds_temporal_future_only_drop_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    ctx = {"run_id": "r_temp_ok", "_observability_finalized_once": False}
    manifest = {"run_id": "r_temp_ok", "cohort_size": 5}
    artifact_list: list[str] = []

    monkeypatch.setattr(
        app_config,
        "RUNTIME_LAST_SPLIT_ALGORITHM",
        "temporal_year_holdout_v1",
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TEMPORAL_SPLIT_SUMMARY",
        {
            "test_year_floor": 2024,
            "test_rows_dropped_unseen_train_classes": 219,
        },
        raising=False,
    )

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=True,
        evidence_mode=True,
        result_code=0,
        profile_id="malicious_temporal_stability_locked",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    warnings = blob.get("research_warnings_top") or []
    assert any("dropped 219 newer-row sample(s)" in str(item) for item in warnings)


def test_finalize_pipeline_observability_carries_degraded_cohort_contract_warning(
    tmp_path: Path,
) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    warning = (
        "[COHORT_LOCK] Locked cohort taxonomy drift for profile demo: "
        "sample-id membership still matches, but family/type counts changed."
    )
    ctx = {
        "run_id": "r_cohort_drift",
        "_observability_finalized_once": False,
        "paper_cohort_contract": {
            "validation": {
                "status": "degraded_taxonomy_label_drift",
                "warning": warning,
            }
        },
    }
    manifest = {"run_id": "r_cohort_drift", "cohort_size": 5}
    artifact_list: list[str] = []

    out_path = finalize_pipeline_observability(
        diagnostics_dir=diagnostic,
        run_root=None,
        manifest_context=ctx,
        manifest=manifest,
        artifact_list=artifact_list,
        compliance_report={"overall_status": "pass"},
        paper_mode=True,
        evidence_mode=True,
        result_code=0,
        profile_id="malicious_temporal_stability_locked",
    )

    assert isinstance(out_path, Path)
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    warnings = blob.get("research_warnings_top") or []
    assert warning in warnings


def test_patch_observability_scientific_adequacy_from_dataset_foundation(tmp_path: Path) -> None:
    diagnostic = tmp_path / "diag"
    diagnostic.mkdir(parents=True, exist_ok=True)
    (diagnostic / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "model": {"top_macro_f1": 0.684, "top_model_primary_metric_value": 0.684},
                "scientific_adequacy": {
                    "posture": "Mixed",
                    "blockers": ["dataset foundation does not mark supervised family claims as suitable"],
                    "supervised_family_claims_suitable": False,
                    "temporal_future_only_rows_dropped": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    (diagnostic / "dataset_foundation_summary.json").write_text(
        json.dumps({"supervised_family_claims_suitable": True}),
        encoding="utf-8",
    )

    assert patch_observability_scientific_adequacy_from_dataset_foundation(diagnostics_dir=diagnostic) is True
    blob = json.loads((diagnostic / "run_observability_summary.json").read_text(encoding="utf-8"))
    sci = blob.get("scientific_adequacy") or {}
    assert sci.get("supervised_family_claims_suitable") is True
    assert sci.get("posture") == "Strong"
    assert sci.get("blockers") == []
