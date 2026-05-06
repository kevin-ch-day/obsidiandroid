"""Legacy shim for ``ml_classification.training.pipeline_result_promoter``.

Canonical implementation lives at ``obsidiandroid.modeling.pipeline_result_promoter``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.pipeline_result_promoter")
sys.modules[__name__] = _mod
