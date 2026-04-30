"""Backward-compatible shim for legacy paper-mode resolution imports."""

from __future__ import annotations

from utils.evidence_mode_resolver import (
    ENV_EVIDENCE_MODE as ENV_PAPER_MODE,
    EvidenceModeConfigError as PaperModeConfigError,
    EvidenceModeImmutableError as PaperModeImmutableError,
    EvidenceModeResolution as PaperModeResolution,
    enforce_immutable_lock,
    resolve_evidence_mode,
)


def resolve_paper_mode(**kwargs) -> PaperModeResolution:
    """Legacy wrapper that forwards to the neutral evidence-mode resolver."""
    return resolve_evidence_mode(**kwargs)
