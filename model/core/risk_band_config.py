"""Legacy shim for ``model.core.risk_band_config``.

Canonical implementation lives at ``obsidiandroid.risk_band.risk_band_config``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.risk_band.risk_band_config")
sys.modules[__name__] = _mod
