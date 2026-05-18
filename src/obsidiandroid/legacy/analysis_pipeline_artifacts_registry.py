"""Legacy ``analysis.pipeline.artifacts`` shim registry."""

from __future__ import annotations

import importlib
import sys

LEGACY_EXPORT_NAMES: tuple[str, ...] = ("paths", "registry")


def register_analysis_pipeline_artifacts_legacy_aliases(package: object | None = None) -> None:
    for name in LEGACY_EXPORT_NAMES:
        mod = importlib.import_module(f"obsidiandroid.pipeline.artifacts.{name}")
        sys.modules.setdefault(f"analysis.pipeline.artifacts.{name}", mod)
        if package is not None:
            setattr(package, name, mod)


__all__ = ("LEGACY_EXPORT_NAMES", "register_analysis_pipeline_artifacts_legacy_aliases")
