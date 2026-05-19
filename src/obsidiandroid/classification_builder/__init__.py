"""Canonical structured malware classification builder namespace.

Structured malware classification record builders now live under
``obsidiandroid.classification_builder``.
"""

from __future__ import annotations

import importlib
import sys

_LEGACY_BY_CANONICAL: dict[str, str] = {
    "classification_constants": "obsidiandroid.classification_builder.classification_constants",
    "classification_row_builder": "obsidiandroid.classification_builder.classification_row_builder",
    "prediction_utils": "obsidiandroid.classification_builder.prediction_utils",
    "record_enrichment": "obsidiandroid.classification_builder.record_enrichment",
    "sample_classification_builder": "obsidiandroid.classification_builder.sample_classification_builder",
    "vendor_record_selector": "obsidiandroid.classification_builder.vendor_record_selector",
}


def __getattr__(name: str):
    if name not in _LEGACY_BY_CANONICAL:
        raise AttributeError(name)
    mod = importlib.import_module(_LEGACY_BY_CANONICAL[name])
    globals()[name] = mod
    sys.modules.setdefault(f"obsidiandroid.classification_builder.{name}", mod)
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LEGACY_BY_CANONICAL.keys()))


__all__ = sorted(_LEGACY_BY_CANONICAL.keys())
