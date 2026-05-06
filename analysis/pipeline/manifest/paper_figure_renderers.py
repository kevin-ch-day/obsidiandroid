"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.manifest.paper_figure_renderers``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.manifest.paper_figure_renderers")
sys.modules[__name__] = _mod
