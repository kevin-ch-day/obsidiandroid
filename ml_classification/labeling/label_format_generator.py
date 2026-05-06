"""Legacy shim for ``ml_classification.labeling.label_format_generator``.

Canonical implementation lives at ``obsidiandroid.labeling.label_format_generator``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.labeling.label_format_generator")
sys.modules[__name__] = _mod
