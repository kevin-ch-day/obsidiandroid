"""Lightweight observability artifact tests."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.observability.pipeline_observability.finalize import finalize_pipeline_observability
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
    assert blob.get("publication_ready_status") == blob.get("paper_safe_status")
    assert blob.get("publication_ready_reasons") == blob.get("paper_safe_reasons")
    assert ctx["_observability_finalized_once"] is True
