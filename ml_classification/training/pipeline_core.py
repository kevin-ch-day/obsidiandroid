"""Legacy shim for ``ml_classification.training.pipeline_core``.

Canonical implementation lives at ``obsidiandroid.modeling.pipeline_core``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.pipeline_core")
sys.modules[__name__] = _mod
