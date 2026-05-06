"""Legacy shim for ``ml_classification.labeling.classification_label_resolver``.

Canonical implementation lives at ``obsidiandroid.labeling.classification_label_resolver``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.labeling.classification_label_resolver")
sys.modules[__name__] = _mod
