"""Legacy shim for ``ml_classification.training.prediction_builder``.

Canonical implementation lives at ``obsidiandroid.modeling.prediction_builder``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.prediction_builder", __name__)
sys.modules[__name__] = _mod
