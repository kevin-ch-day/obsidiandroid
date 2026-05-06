"""Legacy shim: canonical module is ``obsidiandroid.features.vectorization.feature_vector_builder``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.features.vectorization.feature_vector_builder")
sys.modules[__name__] = _mod
