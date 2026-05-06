"""Legacy shim for ``ml_classification.builder.classification_constants``.

Canonical implementation lives at ``obsidiandroid.classification_builder.classification_constants``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.classification_builder.classification_constants")
sys.modules[__name__] = _mod
