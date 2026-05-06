"""Compatibility shim for ``obsidiandroid.modeling.ml_result_validator``."""

from __future__ import annotations

import sys
from importlib import import_module

_canonical = import_module("obsidiandroid.modeling.ml_result_validator")
sys.modules[__name__] = _canonical
