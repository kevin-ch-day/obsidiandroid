"""Legacy shim for ``ml_classification.labeling.label_postprocessor``.

Canonical implementation lives at ``obsidiandroid.labeling.label_postprocessor``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.labeling.label_postprocessor")
sys.modules[__name__] = _mod
