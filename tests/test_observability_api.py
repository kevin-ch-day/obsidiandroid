"""Tests for :mod:`obsidiandroid.observability.pipeline_observability.api`."""

from __future__ import annotations

from pathlib import Path

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
