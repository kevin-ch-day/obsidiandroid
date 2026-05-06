"""Legacy shim for ``ml_classification.builder.classification_row_builder``.

Canonical implementation lives at ``obsidiandroid.classification_builder.classification_row_builder``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.classification_builder.classification_row_builder")
sys.modules[__name__] = _mod
