# Filename: src/obsidiandroid/governance/analysis_pipeline_governance_shim.py
"""Allowed submodule names for the legacy ``analysis.pipeline.governance`` lazy façade (Pass 75)."""

from __future__ import annotations

ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES: frozenset[str] = frozenset(
    {"exceptions", "integrity", "policy", "readiness"}
)

__all__ = ("ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES",)
