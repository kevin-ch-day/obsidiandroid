"""Legacy shim for ``model.utils.metadata_normalizer``.

Canonical implementation lives at ``obsidiandroid.vendors.contracts.metadata_normalizer``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.vendors.contracts.metadata_normalizer")
sys.modules[__name__] = _mod
