"""Legacy ``analysis.pipeline`` package (shim-only).

Canonical implementations live under ``obsidiandroid.pipeline``. This wrapper
keeps the legacy package importable while:

- pre-registering ordinary top-level pipeline leaves that no longer exist on
  disk under ``analysis/pipeline/*.py``
- leaving patch-sensitive leaves (``runner`` and ``main_facade``) on disk
- preserving nested compatibility packages such as
  ``analysis.pipeline.manifest`` and ``analysis.pipeline.governance``
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

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

_PACKAGE_LEAVES = frozenset({"artifacts", "governance", "manifest", "permission_trends"})

_PHYSICAL_LEAVES = frozenset({"main_facade", "runner"})

_TOP_LEVEL_ALIAS_NAMES = frozenset(
    {
        "attach_engine_metadata",
        "av_engine_pipeline",
        "contract_filters",
        "engine_normalization",
        "engine_pipeline_utils",
        "permission_trends_selection",
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
    }
)


def _load_runner_attr(name: str) -> Any:
    runner_mod = importlib.import_module("obsidiandroid.pipeline.runner")
    return getattr(runner_mod, name)


def _load_legacy_leaf(name: str) -> Any:
    if name in _PHYSICAL_LEAVES:
        mod = importlib.import_module(f"{__name__}.{name}")
    else:
        mod = import_legacy_shim(f"obsidiandroid.pipeline.{name}", f"{__name__}.{name}")
        sys.modules[f"{__name__}.{name}"] = mod
    globals()[name] = mod
    return mod


for _name in sorted(_TOP_LEVEL_ALIAS_NAMES):
    _load_legacy_leaf(_name)


def __getattr__(name: str) -> Any:
    if name in _RUNNER_ATTRS:
        return _load_runner_attr(name)
    if name in _TOP_LEVEL_ALIAS_NAMES or name in _PHYSICAL_LEAVES:
        return _load_legacy_leaf(name)
    if name in _PACKAGE_LEAVES:
        pkg = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = pkg
        return pkg
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(__all__) | _PACKAGE_LEAVES | _PHYSICAL_LEAVES)
