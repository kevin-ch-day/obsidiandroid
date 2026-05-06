"""Legacy shim for ``ml_classification.labeling.label_builder_wrapper``.

Canonical implementation lives at ``obsidiandroid.labeling.label_builder_wrapper``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.labeling.label_builder_wrapper")
sys.modules[__name__] = _mod
