"""Legacy shim: permission trends report stage lives under ``obsidiandroid.pipeline.stage_permission_trends_report``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.stage_permission_trends_report")
sys.modules[__name__] = _mod
