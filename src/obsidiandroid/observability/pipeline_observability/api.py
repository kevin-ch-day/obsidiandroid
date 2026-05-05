"""Stable entry points for pipeline observability (avoid ad-hoc JSONL writes in stages).

All helpers resolve :class:`PipelineObservabilitySession` from ``manifest_context["pipeline_observability"]``.
If no session exists, calls are silent no-ops.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from obsidiandroid.observability.pipeline_observability.session import PipelineObservabilitySession
from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory, LogSeverity


def _session(manifest_context: dict[str, Any] | None) -> PipelineObservabilitySession | None:
    if not isinstance(manifest_context, dict):
        return None
    obs = manifest_context.get("pipeline_observability")
    return obs if isinstance(obs, PipelineObservabilitySession) else None


def record_stage_start(
    manifest_context: dict[str, Any] | None,
    stage_name: str,
    **fields: Any,
) -> None:
    """Emit ``STAGE_START`` JSONL for a logical sub-phase (optional finer grain than runner)."""
    s = _session(manifest_context)
    if s:
        s.emit_stage_start(stage_name, **fields)


def record_stage_end(
    manifest_context: dict[str, Any] | None,
    stage_name: str,
    **kwargs: Any,
) -> None:
    """Append ``pipeline_stage_summary`` row + ``STAGE_END`` JSONL (same contract as runner timing)."""
    s = _session(manifest_context)
    if s:
        s.emit_stage_completion(stage_name, **kwargs)


def record_data_population_change(
    manifest_context: dict[str, Any] | None,
    *,
    transition: str,
    previous_count: int | None,
    new_count: int | None,
    reason: str,
    artifact_path: str = "",
) -> None:
    """Structured cohort / row-count transition (``DATA_POPULATION_CHANGE``)."""
    s = _session(manifest_context)
    if s:
        s.log_population_transition(
            transition=transition,
            previous_count=previous_count,
            new_count=new_count,
            reason=reason,
            artifact_path=artifact_path,
        )


def record_feature_schema_change(
    manifest_context: dict[str, Any] | None,
    *,
    stage_hint: str,
    previous_cols: int | None,
    new_cols: int | None,
    reason: str,
    artifact_path: str = "",
) -> None:
    """Feature column deltas (``FEATURE_SCHEMA_CHANGE``)."""
    s = _session(manifest_context)
    if s:
        s.log_schema_change(
            stage_hint=stage_hint,
            previous_cols=previous_cols,
            new_cols=new_cols,
            reason=reason,
            artifact_path=artifact_path,
        )


def record_artifact_write(
    manifest_context: dict[str, Any] | None,
    path: Path | str,
    *,
    detail: str = "",
) -> None:
    """Concrete artifact persisted (``ARTIFACT_WRITE``)."""
    s = _session(manifest_context)
    if s:
        s.emit_artifact_written(path, detail=detail)


def record_artifact_skip(
    manifest_context: dict[str, Any] | None,
    *,
    reason: str,
    path_hint: str = "",
    detail: str = "",
) -> None:
    """Expected export missing or intentionally skipped (``ARTIFACT_SKIP``)."""
    s = _session(manifest_context)
    if s:
        s.emit_artifact_skipped(reason=reason, path_hint=path_hint, detail=detail)


def record_research_warning(
    manifest_context: dict[str, Any] | None,
    message: str,
    *,
    stage_hint: str = "",
) -> None:
    """Warning that may bias interpretation."""
    s = _session(manifest_context)
    if s:
        s.add_warning(
            message,
            severity=LogSeverity.RESEARCH_WARNING,
            category=LogCategory.WARNING_RESEARCH,
            paper_blocker=False,
            stage_hint=stage_hint,
        )


def record_paper_blocker(
    manifest_context: dict[str, Any] | None,
    message: str,
    *,
    stage_hint: str = "",
) -> None:
    """Strict paper/evidence posture violation."""
    s = _session(manifest_context)
    if s:
        s.add_warning(
            message,
            severity=LogSeverity.PAPER_BLOCKER,
            category=LogCategory.PAPER_STATUS,
            paper_blocker=True,
            stage_hint=stage_hint,
        )


def record_partial_failure(
    manifest_context: dict[str, Any] | None,
    *,
    stage: str,
    error: str,
    recoverable: bool = True,
) -> None:
    """Recoverable degraded step (tracked in partial_failures ledger + JSONL error category)."""
    s = _session(manifest_context)
    if s:
        s.record_partial_failure(stage=stage, error=error, recoverable=recoverable)


def record_training_split_allocation(
    manifest_context: dict[str, Any] | None,
    *,
    pool_rows: int | None,
    train_rows: int | None,
    test_rows: int | None,
    reason: str = "",
    artifact_path: str = "",
) -> None:
    """Emit train/test shard sizes after supervised training pool selection."""
    s = _session(manifest_context)
    if s:
        s.log_train_test_split_allocation(
            pool_rows=pool_rows,
            train_rows=train_rows,
            test_rows=test_rows,
            reason=reason,
            artifact_path=artifact_path,
        )


def record_ablation_summary(
    manifest_context: dict[str, Any] | None,
    *,
    frozen_cohort_ids: int,
    training_universe_ids: int,
    experiments_built: int,
    label_target_stats: list[dict[str, Any]],
    summary_csv_path: str,
) -> None:
    """Single JSONL anchor for ablation shapes (no per-row CSV mirroring)."""
    s = _session(manifest_context)
    if s:
        s.emit_jsonl(
            LogCategory.ABLATION_STATUS,
            severity=LogSeverity.INFO,
            message="ablation_shapes",
            frozen_cohort_sample_ids=int(frozen_cohort_ids),
            training_universe_sample_ids=int(training_universe_ids),
            experiments_built=int(experiments_built),
            label_target_stats=list(label_target_stats)[:48],
            ablation_summary_csv=str(summary_csv_path),
        )


__all__ = [
    "record_ablation_summary",
    "record_artifact_skip",
    "record_artifact_write",
    "record_data_population_change",
    "record_feature_schema_change",
    "record_paper_blocker",
    "record_partial_failure",
    "record_research_warning",
    "record_stage_end",
    "record_stage_start",
    "record_training_split_allocation",
]
