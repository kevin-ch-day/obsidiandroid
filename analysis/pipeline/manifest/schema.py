"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.manifest.schema``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.manifest.schema")
sys.modules[__name__] = _mod
