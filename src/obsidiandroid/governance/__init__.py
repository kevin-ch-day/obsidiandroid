"""Canonical governance namespace.

Evidence mode, compliance, cohort reproducibility, manifest, and governance
policy helpers live under :mod:`obsidiandroid.governance`.
"""

from __future__ import annotations

from importlib import import_module

_CANONICAL_SUBMODULE_NAMES = (
    "artifacts",
    "cohort_readiness_report",
    "cohort_reproducibility",
    "compliance",
    "evidence_mode_resolver",
    "exceptions",
    "integrity",
    "paper_family_display_policy",
    "policy",
    "readiness",
    "run_manifest",
)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)


def __getattr__(name: str):
    if name in __all__:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
