"""Legacy ``ml_classification.labeling`` package shim.

Prefer ``obsidiandroid.labeling.taxonomy`` for public taxonomy helpers.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim
from obsidiandroid.modeling.ml_classification_shim_facades import (
    ML_CLASSIFICATION_LABELING_SUBMODULES,
)

for _name in sorted(ML_CLASSIFICATION_LABELING_SUBMODULES):
    _canonical = f"obsidiandroid.labeling.{_name}"
    _mod = import_legacy_shim(_canonical, f"{__name__}.{_name}")
    globals()[_name] = _mod
    sys.modules[f"{__name__}.{_name}"] = _mod


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_LABELING_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_LABELING_SUBMODULES))
