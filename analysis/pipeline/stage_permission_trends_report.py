"""Legacy shim: permission trends report stage lives under ``obsidiandroid.pipeline.stage_permission_trends_report``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.stage_permission_trends_report", __name__)
sys.modules[__name__] = _mod
