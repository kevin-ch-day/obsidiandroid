"""Legacy ``analysis.pipeline.governance`` package (shim-only).

Canonical implementations live under ``obsidiandroid.governance``; leaf modules
``exceptions``, ``integrity``, ``policy``, and ``readiness`` are thin ``sys.modules``
identity shims to the same ``ModuleType`` objects as ``obsidiandroid.governance.*``.

Submodule names are defined in
:mod:`obsidiandroid.governance.analysis_pipeline_governance_shim`.
"""

from __future__ import annotations

from typing import Any

from obsidiandroid.governance.analysis_pipeline_governance_shim import (
    ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES,
)
from obsidiandroid.legacy_shim_lazy import lazy_legacy_submodule


def __getattr__(name: str) -> Any:
    return lazy_legacy_submodule(name, __name__, ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES)


def __dir__() -> list[str]:
    return sorted(ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES)


__all__ = tuple(sorted(ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES))
