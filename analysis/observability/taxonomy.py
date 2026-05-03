"""Unified log/event categories and severity levels for pipeline observability."""

from __future__ import annotations

from enum import Enum


class LogCategory(str, Enum):
    """Structured event bucket for terminals, JSONL pipeline logs, and audits."""

    STAGE_START = "STAGE_START"
    STAGE_END = "STAGE_END"
    STAGE_SKIP = "STAGE_SKIP"
    DATA_POPULATION_CHANGE = "DATA_POPULATION_CHANGE"
    FEATURE_SCHEMA_CHANGE = "FEATURE_SCHEMA_CHANGE"
    FEATURE_PRUNING = "FEATURE_PRUNING"
    ROW_ALIGNMENT = "ROW_ALIGNMENT"
    LABEL_FILTERING = "LABEL_FILTERING"
    ABLATION_STATUS = "ABLATION_STATUS"
    ARTIFACT_WRITE = "ARTIFACT_WRITE"
    ARTIFACT_SKIP = "ARTIFACT_SKIP"
    CLAIM_AUDIT = "CLAIM_AUDIT"
    FIGURE_AUDIT = "FIGURE_AUDIT"
    PAPER_STATUS = "PAPER_STATUS"
    WARNING_RESEARCH = "WARNING_RESEARCH"
    WARNING_OPERATIONAL = "WARNING_OPERATIONAL"
    ERROR_RECOVERABLE = "ERROR_RECOVERABLE"
    ERROR_FATAL = "ERROR_FATAL"


class LogSeverity(str, Enum):
    """Severity used across terminal hints, Markdown audits, and status JSON."""

    INFO = "INFO"
    WARNING = "WARNING"
    RESEARCH_WARNING = "RESEARCH_WARNING"
    PAPER_BLOCKER = "PAPER_BLOCKER"
    ERROR = "ERROR"
    FATAL = "FATAL"


__all__ = ["LogCategory", "LogSeverity"]
