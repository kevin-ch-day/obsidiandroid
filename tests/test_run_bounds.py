"""Tests for ``analysis.pipeline.run_bounds``."""

from __future__ import annotations

from pathlib import Path

from analysis.pipeline.run_bounds import (
    PipelineRunBounds,
    clear_pipeline_run_bounds,
    get_pipeline_run_bounds,
    set_pipeline_run_bounds,
)


def test_run_bounds_lifecycle() -> None:
    assert get_pipeline_run_bounds() is None
    b = PipelineRunBounds(
        run_id="rid",
        profile_ref="p",
        stop_after="full",
        diagnostics_dir=Path("/tmp/diag"),
        output_root_base=Path("/tmp/out"),
        runtime_run_root=Path("/tmp/out/runs/rid"),
    )
    set_pipeline_run_bounds(b)
    assert get_pipeline_run_bounds() is b
    clear_pipeline_run_bounds()
    assert get_pipeline_run_bounds() is None
