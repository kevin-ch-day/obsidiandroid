"""Tests for :mod:`obsidiandroid.observability.pipeline_observability.api`."""

from __future__ import annotations

import io
import sys
from pathlib import Path

from obsidiandroid.observability.logging import runtime as runtime_logging
from obsidiandroid.observability.pipeline_observability.api import (
    record_data_population_change,
    record_partial_failure,
    record_training_split_allocation,
)
from obsidiandroid.observability.pipeline_observability.session import PipelineObservabilitySession
from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory


def test_api_helpers_route_to_session(tmp_path: Path) -> None:
    sess = PipelineObservabilitySession(diagnostics_dir=tmp_path, run_id="api_r")
    ctx: dict = {"pipeline_observability": sess}
    record_data_population_change(
        ctx,
        transition="unit_test_transition",
        previous_count=10,
        new_count=9,
        reason="test",
    )
    jl = tmp_path / "pipeline_events.jsonl"
    blob = jl.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert LogCategory.DATA_POPULATION_CHANGE.value in blob
    record_training_split_allocation(
        ctx,
        pool_rows=100,
        train_rows=80,
        test_rows=20,
        reason="split",
        artifact_path="/tmp/nonexistent_audit.csv",
    )
    blob2 = jl.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert LogCategory.LABEL_FILTERING.value in blob2

    record_partial_failure(ctx, stage="x", error="boom", recoverable=True)
    assert sess.partial_failures_snapshot()


def test_api_no_crash_without_session(tmp_path: Path) -> None:
    record_data_population_change(
        None,
        transition="noop",
        previous_count=1,
        new_count=1,
        reason="",
    )


def test_start_runtime_logging_disabled(monkeypatch) -> None:
    """Return None when runtime logging is disabled."""
    monkeypatch.setattr(runtime_logging.app_config, "LOGGING_ENABLED", False)

    context = runtime_logging.start_runtime_logging("run123")

    assert context is None


def test_start_and_stop_runtime_logging(monkeypatch, tmp_path: Path) -> None:
    """Mirror stdout/stderr to runtime log and restore original streams."""
    monkeypatch.setattr(runtime_logging.app_config, "LOGGING_ENABLED", True)
    monkeypatch.setenv("OBSIDIANDROID_LOG_FILES_ROOT", str(tmp_path))

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    capture_out = io.StringIO()
    capture_err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", capture_out)
    monkeypatch.setattr(sys, "stderr", capture_err)

    context = runtime_logging.start_runtime_logging("runabc")
    assert context is not None
    try:
        print("hello-out")
        print("hello-err", file=sys.stderr)
    finally:
        runtime_logging.stop_runtime_logging(context)

    assert sys.stdout is capture_out
    assert sys.stderr is capture_err
    assert "hello-out" in capture_out.getvalue()
    assert "hello-err" in capture_err.getvalue()

    log_path = tmp_path / "runtime" / "runabc" / "pipeline_runtime_console_runabc.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "hello-out" in content
    assert "hello-err" in content

    # Restore test process streams.
    monkeypatch.setattr(sys, "stdout", original_stdout)
    monkeypatch.setattr(sys, "stderr", original_stderr)
