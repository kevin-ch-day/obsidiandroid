"""Legacy shim: AV/vendor stage lives under ``obsidiandroid.pipeline.stage_av_vendor``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.stage_av_vendor")
sys.modules[__name__] = _mod
