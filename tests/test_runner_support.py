"""Tests for operator-facing pipeline failure summaries."""

from __future__ import annotations

import json

from obsidiandroid.pipeline.runner_support import (
    PipelineStageFailure,
    emit_pipeline_failure_summary,
    write_pipeline_failure_summary,
)


def test_emit_pipeline_failure_summary_for_stage_failure(capsys) -> None:
    err = PipelineStageFailure("[PIPELINE] Engine scoring error (NameError): ml_console is not defined")

    emit_pipeline_failure_summary(
        stage_name="av_pipeline",
        error=err,
        diagnostics_dir="/tmp/run/diagnostics",
        run_root="/tmp/run",
        preflight_path="/tmp/run/diagnostics/preflight_report.json",
    )

    out = capsys.readouterr().out
    assert "Pipeline Failure" in out
    assert "Stage" in out and "av_pipeline" in out
    assert "Error type" in out and "PipelineStageFailure" in out
    assert "Reason" in out
    assert "Engine scoring error" in out
    assert "Preflight report" in out
    assert "[NEXT]" in out


def test_emit_pipeline_failure_summary_for_integrity_stop(capsys) -> None:
    err = ValueError("[INTEGRITY] included_engines == 0")

    emit_pipeline_failure_summary(
        stage_name="av_pipeline",
        error=err,
        diagnostics_dir="/tmp/run/diagnostics",
        run_root="/tmp/run",
        preflight_path="",
    )

    out = capsys.readouterr().out
    assert "Integrity Stop" in out
    assert "included_engines == 0" in out
    assert "Review the integrity-related diagnostics" in out


def test_write_pipeline_failure_summary_artifacts(tmp_path) -> None:
    paths = write_pipeline_failure_summary(
        diagnostics_dir=str(tmp_path / "diagnostics"),
        run_root=str(tmp_path / "run"),
        run_id="rid123",
        stage_name="av_pipeline",
        error=PipelineStageFailure("[PIPELINE] Engine scoring error (NameError): ml_console is not defined"),
        preflight_path=str(tmp_path / "diagnostics" / "preflight_report.json"),
    )
    assert len(paths) == 2
    json_path = tmp_path / "diagnostics" / "failure_summary.json"
    md_path = tmp_path / "diagnostics" / "failure_summary.md"
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "rid123"
    assert payload["stage"] == "av_pipeline"
    assert payload["recoverable_stage_failure"] is True
    assert "Engine scoring error" in payload["reason"]
    assert "engine lifecycle" in payload["recommended_next_action"].lower()
