"""Permission-trends pipeline helpers."""

from __future__ import annotations

from importlib import import_module

from .permission_trends_submodule_manifest import PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES

__all__ = list(PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES)


def __getattr__(name: str):
    if name in __all__:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
