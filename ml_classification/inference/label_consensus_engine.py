"""Legacy shim for ``ml_classification.inference.label_consensus_engine``.

Canonical implementation lives at ``obsidiandroid.inference.label_consensus_engine``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.inference.label_consensus_engine")
sys.modules[__name__] = _mod
