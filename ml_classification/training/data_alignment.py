"""Legacy shim for ``ml_classification.training.data_alignment``.

Canonical implementation lives at ``obsidiandroid.modeling.data_alignment``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.data_alignment", __name__)
sys.modules[__name__] = _mod
