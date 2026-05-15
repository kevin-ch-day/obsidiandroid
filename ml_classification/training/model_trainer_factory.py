"""Legacy shim for ``ml_classification.training.model_trainer_factory``.

Canonical implementation lives at ``obsidiandroid.modeling.model_trainer_factory``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.model_trainer_factory", __name__)
sys.modules[__name__] = _mod
