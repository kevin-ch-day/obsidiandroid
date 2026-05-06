"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.manifest.paper_compliance_checks``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.manifest.paper_compliance_checks")
sys.modules[__name__] = _mod
