"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.permission_trends.publish_paths``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.permission_trends.publish_paths")
sys.modules[__name__] = _mod
