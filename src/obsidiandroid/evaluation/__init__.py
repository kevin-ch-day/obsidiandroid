"""Evaluation canonical surface (in progress).

Pass 61: physically moved two low-risk evaluation helpers from
``analysis.evaluation`` into this package:

- ``model_tuning``
- ``random_forest_diagnostics``

Legacy import paths remain valid via leaf shims under ``analysis/evaluation``.
"""

from __future__ import annotations

import importlib
import sys

_LEGACY_BY_CANONICAL = {
    "model_tuning": "obsidiandroid.evaluation.model_tuning",
    "random_forest_diagnostics": "obsidiandroid.evaluation.random_forest_diagnostics",
    "vendor_parser_matching": "obsidiandroid.evaluation.vendor_parser_matching",
    "vendor_classification_inspector": "obsidiandroid.evaluation.vendor_classification_inspector",
}


def __getattr__(name: str):
    if name not in _LEGACY_BY_CANONICAL:
        raise AttributeError(name)
    mod = importlib.import_module(_LEGACY_BY_CANONICAL[name])
    globals()[name] = mod
    sys.modules.setdefault(f"obsidiandroid.evaluation.{name}", mod)
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LEGACY_BY_CANONICAL.keys()))


__all__ = sorted(_LEGACY_BY_CANONICAL.keys())
