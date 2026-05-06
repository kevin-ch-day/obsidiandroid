"""Legacy shim for ``ml_classification.labeling.label_field_normalizer``.

Canonical implementation lives at ``obsidiandroid.labeling.label_field_normalizer``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.labeling.label_field_normalizer")
sys.modules[__name__] = _mod
