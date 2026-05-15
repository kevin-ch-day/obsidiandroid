"""Legacy shim for ``ml_classification.training.train_model_executor``.

Canonical implementation lives at ``obsidiandroid.modeling.train_model_executor``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.train_model_executor", __name__)
sys.modules[__name__] = _mod
