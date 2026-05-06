"""Legacy ``ml_classification.inference`` (shim-only).

Canonical implementations live under ``obsidiandroid.inference``.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULE_NAMES = frozenset(
    {
        "label_consensus_engine",
        "malware_type_engine",
        "signal_health_checker",
        "threat_class_engine",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_NAMES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULE_NAMES)


__all__ = tuple(sorted(_SUBMODULE_NAMES))
