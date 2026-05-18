"""Legacy ``analysis.orchestration`` shim registry."""

from __future__ import annotations

import importlib
import sys

LEGACY_EXPORT_NAMES: tuple[str, ...] = (
    "metadata_features",
    "methodology_artifacts",
    "permission_features",
    "profile_filters",
    "runtime_reporting",
)


def register_analysis_orchestration_legacy_aliases(package: object | None = None) -> None:
    for name in LEGACY_EXPORT_NAMES:
        mod = importlib.import_module(f"obsidiandroid.orchestration.{name}")
        sys.modules.setdefault(f"analysis.orchestration.{name}", mod)
        if package is not None:
            setattr(package, name, mod)


__all__ = ("LEGACY_EXPORT_NAMES", "register_analysis_orchestration_legacy_aliases")
