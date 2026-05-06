"""Legacy shim for ``ml_classification.training.data_alignment``.

Canonical implementation lives at ``obsidiandroid.modeling.data_alignment``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.data_alignment")
sys.modules[__name__] = _mod
