"""Pipeline orchestration namespace (facade over ``analysis.pipeline``).

Re-exports stable, public symbols from :mod:`analysis.pipeline.runner`; policy
leaf modules **contract_filters**, **run_bounds**, and **runtime_policy** are
implemented under this package (**Pass 66**). Attributes resolve via
:func:`__getattr__` so runner bindings stay aligned when tests monkeypatch
:mod:`analysis.pipeline.runner` (e.g. ``DIAGNOSTICS_DIR``).

Prefer ``from obsidiandroid.pipeline import ...`` in new code.
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
    "main_facade",
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

# Pass 66: implementation under ``obsidiandroid.pipeline``; legacy paths are thin shims.
_PIPELINE_PHYSICAL_MODULES = frozenset({"contract_filters", "run_bounds", "runtime_policy"})


def __getattr__(name: str) -> Any:
    """Forward public names to :mod:`analysis.pipeline` modules."""
    if name in _RUNNER_ATTRS:
        runner_mod = importlib.import_module("analysis.pipeline.runner")
        return getattr(runner_mod, name)
    if name in _PIPELINE_PHYSICAL_MODULES:
        return importlib.import_module(f"obsidiandroid.pipeline.{name}")
    if name in __all__:
        return importlib.import_module(f"analysis.pipeline.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
