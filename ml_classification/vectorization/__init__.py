"""Legacy ``ml_classification.vectorization`` (shim-only).

Canonical implementations live under ``obsidiandroid.features.vectorization``.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULE_NAMES = frozenset(
    {
        "feature_encoder",
        "feature_engine_selection",
        "feature_vendor_extractor",
        "feature_vector_builder",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_NAMES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULE_NAMES)


__all__ = tuple(sorted(_SUBMODULE_NAMES))
