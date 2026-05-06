"""Legacy shim for ``ml_classification.labeling.label_input_validator``.

Canonical implementation lives at ``obsidiandroid.labeling.label_input_validator``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.labeling.label_input_validator")
sys.modules[__name__] = _mod
