"""Canonical pipeline orchestration namespace.

:mod:`obsidiandroid.pipeline.runner` holds ``run_pipeline`` (**Pass 67**), and
the stage/orchestration modules wired through the runner are implemented under
``obsidiandroid.pipeline.*``. This package is the only supported pipeline
import surface.

Policy leaf modules **contract_filters**, **run_bounds**, and **runtime_policy**
also live here (**Pass 66**). Attributes resolve via :func:`__getattr__` so
runner bindings stay aligned when tests monkeypatch the runner module or its
exported globals (for example ``DIAGNOSTICS_DIR``).
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "DIAGNOSTICS_DIR",
    "PIPELINE_MAIN_LOGGER",
    "PARSER_QUALITY_PATH",
    "run_pipeline",
    "attach_engine_metadata",
    "av_engine_pipeline",
    "contract_filters",
    "engine_normalization",
    "runner",
    "run_bounds",
    "runtime_policy",
    "sample_exports",
    "sample_preparation",
    "score_av_engines",
    "stage_ablation",
    "stage_av_vendor",
    "stage_feature_enrichment",
    "stage_manifest",
    "stage_modeling",
    "stage_permission_trends_report",
    "stage_results_warehouse",
    "stage_samples",
    "vendor_metadata_pipeline",
]

_RUNNER_ATTRS = {
    "DIAGNOSTICS_DIR",
    "PIPELINE_MAIN_LOGGER",
    "PARSER_QUALITY_PATH",
    "run_pipeline",
}

# Pipeline implementation modules exposed by the canonical package facade.
_PIPELINE_PHYSICAL_MODULES = frozenset(
    {
        "contract_filters",
        "run_bounds",
        "runtime_policy",
        "runner",
        "stage_samples",
        "sample_exports",
        "stage_av_vendor",
        "stage_manifest",
        "sample_preparation",
        "stage_feature_enrichment",
        "stage_modeling",
        "stage_ablation",
        "stage_results_warehouse",
        "stage_permission_trends_report",
        "engine_pipeline_utils",
        "attach_engine_metadata",
        "engine_normalization",
        "score_av_engines",
        "av_engine_pipeline",
        "vendor_metadata_pipeline",
        "permission_trends_selection",
    }
)


def __getattr__(name: str) -> Any:
    """Resolve public names from runner globals or canonical pipeline modules."""
    if name in _RUNNER_ATTRS:
        runner_mod = importlib.import_module("obsidiandroid.pipeline.runner")
        return getattr(runner_mod, name)
    if name in _PIPELINE_PHYSICAL_MODULES:
        return importlib.import_module(f"obsidiandroid.pipeline.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
