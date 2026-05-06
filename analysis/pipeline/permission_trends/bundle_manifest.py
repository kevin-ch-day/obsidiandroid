"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.permission_trends.bundle_manifest``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.permission_trends.bundle_manifest")
sys.modules[__name__] = _mod
