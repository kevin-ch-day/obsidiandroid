"""Runtime stream logging helpers.

This module mirrors stdout/stderr output into a per-run log file so pipeline
events emitted via both ``print`` and display helpers are persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from config import app_config


@dataclass
class RuntimeLogContext:
    """Captured state for restoring streams after tee logging."""

    log_path: Path
    stream_handle: TextIO
    original_stdout: TextIO
    original_stderr: TextIO


class _TeeStream:
    """Mirror text writes to two output streams."""

    def __init__(self, primary: TextIO, mirror: TextIO) -> None:
        self._primary = primary
        self._mirror = mirror

    def write(self, text: str) -> int:
        written = self._primary.write(text)
        self._mirror.write(text)
        if "\n" in text:
            self.flush()
        return written

    def flush(self) -> None:
        self._primary.flush()
        self._mirror.flush()

    def isatty(self) -> bool:
        return bool(getattr(self._primary, "isatty", lambda: False)())


def start_runtime_logging(run_id: str) -> RuntimeLogContext | None:
    """Enable stdout/stderr tee logging for a run."""
    if not bool(getattr(app_config, "LOGGING_ENABLED", False)):
        return None
    policy = str(getattr(app_config, "LOG_RETENTION_POLICY", "per_run_only")).strip().lower()
    if policy == "rolling_only":
        return None

    import sys

    runtime_diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    runtime_run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
    if runtime_diag and runtime_run_id == str(run_id):
        log_dir = Path(runtime_diag) / "runtime_logs"
    else:
        log_dir = Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics" / "runtime_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"pipeline_runtime_{run_id}.log"
    stream_handle = open(log_path, "w", encoding="utf-8", buffering=1)

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = _TeeStream(original_stdout, stream_handle)
    sys.stderr = _TeeStream(original_stderr, stream_handle)

    return RuntimeLogContext(
        log_path=log_path,
        stream_handle=stream_handle,
        original_stdout=original_stdout,
        original_stderr=original_stderr,
    )


def stop_runtime_logging(context: RuntimeLogContext | None) -> None:
    """Restore original streams and close runtime log handle."""
    if context is None:
        return

    import sys

    try:
        sys.stdout = context.original_stdout
        sys.stderr = context.original_stderr
    finally:
        context.stream_handle.flush()
        context.stream_handle.close()
