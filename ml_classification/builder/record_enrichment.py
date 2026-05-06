"""Legacy shim for ``ml_classification.builder.record_enrichment``.

Canonical implementation lives at ``obsidiandroid.classification_builder.record_enrichment``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.classification_builder.record_enrichment")
sys.modules[__name__] = _mod
