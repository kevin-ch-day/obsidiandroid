"""Legacy shim for ``model.core.record_diagnostics``.

Canonical implementation lives at ``obsidiandroid.vendors.contracts.record_diagnostics``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.vendors.contracts.record_diagnostics")
sys.modules[__name__] = _mod
