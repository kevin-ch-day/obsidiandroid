"""Legacy shim: runtime policy helpers live under ``obsidiandroid.pipeline``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.runtime_policy")
sys.modules[__name__] = _mod
