"""Legacy shim for ``ml_classification.training.pipeline_result_promoter``.

Canonical implementation lives at ``obsidiandroid.modeling.pipeline_result_promoter``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.pipeline_result_promoter", __name__)
sys.modules[__name__] = _mod
