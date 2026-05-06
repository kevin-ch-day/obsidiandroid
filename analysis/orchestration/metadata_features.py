"""Legacy shim: implementation lives under ``obsidiandroid.orchestration.metadata_features``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.orchestration.metadata_features")
sys.modules[__name__] = _mod
