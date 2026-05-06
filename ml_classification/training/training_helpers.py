"""Legacy shim for ``ml_classification.training.training_helpers``.

Canonical implementation lives at ``obsidiandroid.modeling.training_helpers``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.training_helpers")
sys.modules[__name__] = _mod
