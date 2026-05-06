"""Legacy shim for ``ml_classification.ml_utils.feature_label_alignment_helper``.

Canonical implementation lives at ``obsidiandroid.modeling.feature_label_alignment_helper``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.feature_label_alignment_helper")
sys.modules[__name__] = _mod
