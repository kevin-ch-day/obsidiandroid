"""Legacy ``analysis.pipeline.governance`` shim manifest."""

from __future__ import annotations

ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES: frozenset[str] = frozenset(
    {"exceptions", "integrity", "policy", "readiness"}
)

__all__ = ("ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES",)
