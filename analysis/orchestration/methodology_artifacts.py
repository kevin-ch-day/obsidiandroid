"""Legacy shim: implementation lives under ``obsidiandroid.orchestration.methodology_artifacts``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.orchestration.methodology_artifacts")
sys.modules[__name__] = _mod
