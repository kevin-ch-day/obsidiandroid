"""Legacy ``ml_classification.reporting`` package shim.

``compile_classification_results`` is canonical at ``obsidiandroid.reporting``.
``ml_report_builder`` is canonical at ``obsidiandroid.evaluation``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_SUBMODULES = {
    "compile_classification_results": "obsidiandroid.reporting.compile_classification_results",
    "ml_report_builder": "obsidiandroid.evaluation.ml_report_builder",
}

for _name, _canonical in _SUBMODULES.items():
    _mod = import_legacy_shim(_canonical, f"{__name__}.{_name}", warn=True)
    globals()[_name] = _mod
    sys.modules[f"{__name__}.{_name}"] = _mod


def __dir__() -> list[str]:
    return sorted(_SUBMODULES)


__all__ = tuple(sorted(_SUBMODULES))
