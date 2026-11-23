"""Canonical ML modeling namespace with on-demand public submodules."""

from importlib import import_module

from .modeling_facade_manifest import MODELING_FACADE_SUBMODULE_NAMES

__all__ = list(MODELING_FACADE_SUBMODULE_NAMES)


def __getattr__(name: str):
    if name in MODELING_FACADE_SUBMODULE_NAMES:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
