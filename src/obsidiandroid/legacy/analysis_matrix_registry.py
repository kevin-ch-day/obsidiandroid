"""Legacy ``analysis.matrix`` shim registry."""

from __future__ import annotations

import importlib
import sys

LEGACY_EXPORT_NAMES: tuple[str, ...] = (
    "av_binary_matrix_builder",
    "enrich_malicious_scores",
    "enrich_score_features",
)


def register_analysis_matrix_legacy_aliases(package: object | None = None) -> None:
    for name in LEGACY_EXPORT_NAMES:
        mod = importlib.import_module(f"obsidiandroid.matrix.{name}")
        sys.modules.setdefault(f"analysis.matrix.{name}", mod)
        if package is not None:
            setattr(package, name, mod)


__all__ = ("LEGACY_EXPORT_NAMES", "register_analysis_matrix_legacy_aliases")
