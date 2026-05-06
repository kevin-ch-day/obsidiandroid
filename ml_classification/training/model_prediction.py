"""Compatibility shim for ``obsidiandroid.modeling.model_prediction``."""

from __future__ import annotations

import sys
from importlib import import_module

_canonical = import_module("obsidiandroid.modeling.model_prediction")
sys.modules[__name__] = _canonical
