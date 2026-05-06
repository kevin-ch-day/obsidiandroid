"""Legacy shim: manifest helpers live under ``obsidiandroid.pipeline.manifest``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.manifest")
sys.modules[__name__] = _mod
