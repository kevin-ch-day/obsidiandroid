"""Legacy shim: implementation lives under ``obsidiandroid.matrix.enrich_malicious_scores``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.matrix.enrich_malicious_scores")
sys.modules[__name__] = _mod
