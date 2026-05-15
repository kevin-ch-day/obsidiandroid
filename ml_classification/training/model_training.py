"""Legacy shim for ``ml_classification.training.model_training``.

Canonical implementation lives at ``obsidiandroid.modeling.model_training``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.model_training", __name__)
sys.modules[__name__] = _mod
