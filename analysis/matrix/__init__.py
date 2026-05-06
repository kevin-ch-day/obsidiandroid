"""Legacy shim: implementation lives under ``obsidiandroid.matrix``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.matrix")
sys.modules[__name__] = _mod
