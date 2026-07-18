"""Canonical structured malware classification builder namespace.

Structured malware classification record builders now live under
``obsidiandroid.classification_builder``.
"""

from __future__ import annotations

import importlib

_LAZY_CANONICAL_SUBMODULES: dict[str, str] = {
    "classification_constants": "obsidiandroid.classification_builder.classification_constants",
    "classification_row_builder": "obsidiandroid.classification_builder.classification_row_builder",
    "prediction_utils": "obsidiandroid.classification_builder.prediction_utils",
    "record_enrichment": "obsidiandroid.classification_builder.record_enrichment",
    "sample_classification_builder": "obsidiandroid.classification_builder.sample_classification_builder",
    "vendor_record_selector": "obsidiandroid.classification_builder.vendor_record_selector",
}


def __getattr__(name: str):
    if name not in _LAZY_CANONICAL_SUBMODULES:
        raise AttributeError(name)
    mod = importlib.import_module(_LAZY_CANONICAL_SUBMODULES[name])
    globals()[name] = mod
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LAZY_CANONICAL_SUBMODULES.keys()))


__all__ = sorted(_LAZY_CANONICAL_SUBMODULES.keys())
