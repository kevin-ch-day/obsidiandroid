"""Pipeline orchestration helpers: profile filters, permission features, methodology exports, runtime reporting."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "methodology_artifacts",
    "permission_features",
    "profile_filters",
    "runtime_reporting",
]


def __getattr__(name: str):
    if name in __all__:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
