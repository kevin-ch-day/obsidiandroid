"""Legacy ``ml_classification.reporting`` (shim-only).

``compile_classification_results`` is canonical at ``obsidiandroid.reporting``.
``ml_report_builder`` is canonical at ``obsidiandroid.evaluation``.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULE_NAMES = frozenset(
    {
        "compile_classification_results",
        "ml_report_builder",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_NAMES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULE_NAMES)


__all__ = tuple(sorted(_SUBMODULE_NAMES))
