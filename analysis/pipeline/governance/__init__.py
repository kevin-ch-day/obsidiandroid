"""Legacy ``analysis.pipeline.governance`` package (shim-only).

Canonical implementations live under ``obsidiandroid.governance``; leaf modules
``exceptions``, ``integrity``, ``policy``, and ``readiness`` are thin ``sys.modules``
identity shims to the same ``ModuleType`` objects as ``obsidiandroid.governance.*``.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULE_NAMES = frozenset({"exceptions", "integrity", "policy", "readiness"})


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_NAMES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULE_NAMES)


__all__ = tuple(sorted(_SUBMODULE_NAMES))
