"""Legacy shim: implementation lives under ``obsidiandroid.orchestration.profile_filters``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.orchestration.profile_filters")
sys.modules[__name__] = _mod
