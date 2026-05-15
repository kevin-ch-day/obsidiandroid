"""Compatibility shim for ``obsidiandroid.modeling.model_prediction``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_canonical = import_legacy_shim("obsidiandroid.modeling.model_prediction", __name__)
sys.modules[__name__] = _canonical
