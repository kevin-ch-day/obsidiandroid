"""Legacy ``analysis.pipeline.manifest`` shim registry."""

from __future__ import annotations

import importlib
import sys

LEGACY_EXPORT_NAMES: tuple[str, ...] = (
    "builder",
    "confusion_matrix_paths",
    "hashing",
    "paper2_strict_exports",
    "paper_compliance_checks",
    "paper_figure_renderers",
    "runtime_support",
    "schema",
    "stage_manifest_artifacts",
    "stage_manifest_evidence_pack",
    "stage_manifest_writers",
    "writer",
)


def register_analysis_pipeline_manifest_legacy_aliases(package: object | None = None) -> None:
    for name in LEGACY_EXPORT_NAMES:
        mod = importlib.import_module(f"obsidiandroid.pipeline.manifest.{name}")
        sys.modules.setdefault(f"analysis.pipeline.manifest.{name}", mod)
        if package is not None:
            setattr(package, name, mod)


__all__ = ("LEGACY_EXPORT_NAMES", "register_analysis_pipeline_manifest_legacy_aliases")
