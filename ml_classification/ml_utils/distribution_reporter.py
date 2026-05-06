"""Legacy shim for ``ml_classification.ml_utils.distribution_reporter``.

Canonical implementation lives at ``obsidiandroid.modeling.distribution_reporter``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.distribution_reporter")
sys.modules[__name__] = _mod
