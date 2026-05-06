"""Legacy shim for ``ml_classification.builder.vendor_record_selector``.

Canonical implementation lives at ``obsidiandroid.classification_builder.vendor_record_selector``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.classification_builder.vendor_record_selector")
sys.modules[__name__] = _mod
