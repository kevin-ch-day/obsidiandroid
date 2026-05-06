"""Compatibility shim for ``obsidiandroid.modeling.ml_result_analyzer``."""

from __future__ import annotations

import sys
from importlib import import_module

_canonical = import_module("obsidiandroid.modeling.ml_result_analyzer")
sys.modules[__name__] = _canonical
