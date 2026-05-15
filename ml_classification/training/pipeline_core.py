"""Legacy shim for ``ml_classification.training.pipeline_core``.

Canonical implementation lives at ``obsidiandroid.modeling.pipeline_core``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.pipeline_core", __name__)
sys.modules[__name__] = _mod
