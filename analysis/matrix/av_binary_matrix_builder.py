"""Legacy shim: implementation lives under ``obsidiandroid.matrix.av_binary_matrix_builder``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.matrix.av_binary_matrix_builder")
sys.modules[__name__] = _mod
