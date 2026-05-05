"""Immutable snapshot of the active pipeline run's filesystem scope.

Callers historically relied on ``app_config.RUNTIME_*`` and ``DIAGNOSTICS_DIR`` scattered
across modules. This module provides a single typed snapshot **after** profile load and
evidence/paper path remapping (see ``runner.run_pipeline``), then clears it in ``finally``.

New diagnostics tooling should prefer :func:`get_pipeline_run_bounds` over re-parsing globals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PipelineRunBounds:
    """Resolved paths for one ``run_pipeline`` invocation."""

    run_id: str
    profile_ref: str
    stop_after: str
    diagnostics_dir: Path
    output_root_base: Path
    runtime_run_root: Path


_bounds: PipelineRunBounds | None = None


def set_pipeline_run_bounds(bounds: PipelineRunBounds) -> None:
    """Register bounds for the current process (replaced on each pipeline run)."""
    global _bounds
    _bounds = bounds


def get_pipeline_run_bounds() -> PipelineRunBounds | None:
    """Return active bounds, or ``None`` before ``run_pipeline`` or after teardown."""
    return _bounds


def clear_pipeline_run_bounds() -> None:
    """Clear bounds (called from runner ``finally`` so tests do not leak state)."""
    global _bounds
    _bounds = None
