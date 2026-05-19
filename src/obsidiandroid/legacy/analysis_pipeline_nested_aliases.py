# Filename: src/obsidiandroid/legacy/analysis_pipeline_nested_aliases.py
"""Legacy nested-package alias registration for ``analysis.pipeline``.

This helper keeps the final compatibility shell readable by centralizing the
remaining nested package and submodule aliases instead of inlining a large
mapping inside ``analysis.pipeline.__init__``.
"""

from __future__ import annotations

import importlib
import sys

from obsidiandroid.legacy.analysis_pipeline_artifacts_registry import (
    register_analysis_pipeline_artifacts_legacy_aliases,
)
from obsidiandroid.legacy.analysis_pipeline_governance_manifest import (
    ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES,
)
from obsidiandroid.legacy.analysis_pipeline_manifest_registry import (
    register_analysis_pipeline_manifest_legacy_aliases,
)
from obsidiandroid.pipeline.permission_trends.permission_trends_submodule_manifest import (
    PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES,
)

_LEGACY_PACKAGE_TO_CANONICAL = {
    "artifacts": "obsidiandroid.pipeline.artifacts",
    "governance": "obsidiandroid.governance",
    "manifest": "obsidiandroid.pipeline.manifest",
    "permission_trends": "obsidiandroid.pipeline.permission_trends",
}


def register_analysis_pipeline_nested_aliases(package: object | None = None) -> None:
    """Register ``analysis.pipeline.<package>`` and nested submodule aliases."""
    for legacy_leaf, canonical_qual in _LEGACY_PACKAGE_TO_CANONICAL.items():
        legacy_qual = f"analysis.pipeline.{legacy_leaf}"
        canon_pkg = importlib.import_module(canonical_qual)
        sys.modules.setdefault(legacy_qual, canon_pkg)
        if package is not None:
            setattr(package, legacy_leaf, canon_pkg)

    register_analysis_pipeline_artifacts_legacy_aliases(sys.modules["analysis.pipeline.artifacts"])
    register_analysis_pipeline_manifest_legacy_aliases(sys.modules["analysis.pipeline.manifest"])

    for name in sorted(ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES):
        mod = importlib.import_module(f"obsidiandroid.governance.{name}")
        sys.modules.setdefault(f"analysis.pipeline.governance.{name}", mod)
        if package is not None:
            setattr(sys.modules["analysis.pipeline.governance"], name, mod)

    for name in PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES:
        mod = importlib.import_module(f"obsidiandroid.pipeline.permission_trends.{name}")
        sys.modules.setdefault(f"analysis.pipeline.permission_trends.{name}", mod)
        if package is not None:
            setattr(sys.modules["analysis.pipeline.permission_trends"], name, mod)


__all__ = ("register_analysis_pipeline_nested_aliases",)
