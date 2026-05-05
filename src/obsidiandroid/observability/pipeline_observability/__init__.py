"""Pipeline run observability: session, JSONL timeline, stage summary, finalize, run health.

This package is the canonical home for pipeline run observability (formerly under a
legacy ``analysis/observability`` package; that shim path has been removed — import
from here only).
"""

from __future__ import annotations

from obsidiandroid.observability.pipeline_observability import api
from obsidiandroid.observability.pipeline_observability.finalize import finalize_pipeline_observability
from obsidiandroid.observability.pipeline_observability.logging_audit import write_logging_audit_artifacts
from obsidiandroid.observability.pipeline_observability.session import PipelineObservabilitySession
from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory, LogSeverity

__all__ = [
    "api",
    "LogCategory",
    "LogSeverity",
    "PipelineObservabilitySession",
    "finalize_pipeline_observability",
    "write_logging_audit_artifacts",
]
