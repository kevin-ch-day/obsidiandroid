"""Canonical AV engine weight scoring namespace.

Normalization, tiering, and reliability helpers live under
``obsidiandroid.engine_weights``.
"""

from __future__ import annotations

import importlib

_LAZY_CANONICAL_SUBMODULES: dict[str, str] = {
    "assign_detection_tiers": "obsidiandroid.engine_weights.assign_detection_tiers",
    "build_classification_weights": "obsidiandroid.engine_weights.build_classification_weights",
    "classification_weight_inspector": "obsidiandroid.engine_weights.classification_weight_inspector",
    "classification_weight_utils": "obsidiandroid.engine_weights.classification_weight_utils",
    "compute_reliability_score": "obsidiandroid.engine_weights.compute_reliability_score",
    "engine_weights_utils": "obsidiandroid.engine_weights.engine_weights_utils",
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
