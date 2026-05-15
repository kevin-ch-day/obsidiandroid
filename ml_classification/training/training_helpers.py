"""Legacy shim for ``ml_classification.training.training_helpers``.

Canonical implementation lives at ``obsidiandroid.modeling.training_helpers``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.training_helpers", __name__)
sys.modules[__name__] = _mod
