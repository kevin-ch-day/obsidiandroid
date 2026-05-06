"""Legacy shim for ``ml_classification.ml_utils.dataset_splitter``.

Canonical implementation lives at ``obsidiandroid.modeling.dataset_splitter``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.dataset_splitter")
sys.modules[__name__] = _mod
