"""Legacy shim: implementation lives under ``obsidiandroid.governance.exceptions``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.governance.exceptions")
sys.modules[__name__] = _mod
