"""Tests for runtime stream logging helpers."""

from __future__ import annotations

import io
import sys
from pathlib import Path

from obsidiandroid.observability.logging import runtime as runtime_logging


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

    log_path = tmp_path / "runtime" / "runabc" / "pipeline_runtime_runabc.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "hello-out" in content
    assert "hello-err" in content

    # Restore test process streams.
    monkeypatch.setattr(sys, "stdout", original_stdout)
    monkeypatch.setattr(sys, "stderr", original_stderr)

