"""Pipeline orchestration namespace (facade over ``analysis.pipeline``).

:mod:`obsidiandroid.pipeline.runner` holds ``run_pipeline`` (**Pass 67**);
:mod:`analysis.pipeline.runner` is an identity shim to the same module object.
**main_facade**, **stage_samples**, **sample_exports**, **stage_av_vendor**, **stage_manifest**,
the remaining **runner**-wired stages (**Pass 70**), the AV/vendor pipeline chain (**Pass 71**), and
**permission_trends/** helpers plus **permission_trends_selection** (**Pass 74**) are canonical.
**manifest/** and **artifacts/** path/registry helpers (**Pass 76**) are canonical; **analysis.pipeline.manifest** and **analysis.pipeline.artifacts** are identity shims.

Policy leaf modules **contract_filters**, **run_bounds**, and **runtime_policy**
are also implemented under this package (**Pass 66**). Attributes resolve via
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

# Pass 66–71: implementation under ``obsidiandroid.pipeline``; legacy paths are thin shims.
_PIPELINE_PHYSICAL_MODULES = frozenset(
    {
        "contract_filters",
        "run_bounds",
        "runtime_policy",
        "runner",
        "main_facade",
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
    """Resolve public names from runner globals or canonical ``obsidiandroid.pipeline.*`` modules."""
    if name in _RUNNER_ATTRS:
        runner_mod = importlib.import_module("obsidiandroid.pipeline.runner")
        return getattr(runner_mod, name)
    if name in _PIPELINE_PHYSICAL_MODULES:
        return importlib.import_module(f"obsidiandroid.pipeline.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
