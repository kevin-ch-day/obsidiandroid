"""Legacy ``ml_classification.labeling`` (shim-only).

Canonical implementations live under ``obsidiandroid.labeling``.
Prefer ``obsidiandroid.labeling.taxonomy`` for public taxonomy helpers.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULE_NAMES = frozenset(
    {
        "classification_label_resolver",
        "label_builder_wrapper",
        "label_field_normalizer",
        "label_format_generator",
        "label_input_validator",
        "label_postprocessor",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_NAMES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULE_NAMES)


__all__ = tuple(sorted(_SUBMODULE_NAMES))
