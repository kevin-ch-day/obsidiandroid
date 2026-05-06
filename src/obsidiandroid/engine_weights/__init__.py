"""AV engine ML weight scoring helpers (normalization, tiers, reliability).

Pass 98 moved implementation from ``ml_classification.engine_weights``; legacy
paths remain thin identity shims.
"""

from __future__ import annotations

import importlib
import sys

_LEGACY_BY_CANONICAL: dict[str, str] = {
    "assign_detection_tiers": "obsidiandroid.engine_weights.assign_detection_tiers",
    "build_classification_weights": "obsidiandroid.engine_weights.build_classification_weights",
    "classification_weight_inspector": "obsidiandroid.engine_weights.classification_weight_inspector",
    "classification_weight_utils": "obsidiandroid.engine_weights.classification_weight_utils",
    "compute_reliability_score": "obsidiandroid.engine_weights.compute_reliability_score",
    "engine_weights_utils": "obsidiandroid.engine_weights.engine_weights_utils",
}


def __getattr__(name: str):
    if name not in _LEGACY_BY_CANONICAL:
        raise AttributeError(name)
    mod = importlib.import_module(_LEGACY_BY_CANONICAL[name])
    globals()[name] = mod
    sys.modules.setdefault(f"obsidiandroid.engine_weights.{name}", mod)
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LEGACY_BY_CANONICAL.keys()))


__all__ = sorted(_LEGACY_BY_CANONICAL.keys())
