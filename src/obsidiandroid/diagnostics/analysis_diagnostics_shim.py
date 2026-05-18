# Filename: src/obsidiandroid/diagnostics/analysis_diagnostics_shim.py
"""Compatibility wrapper for the legacy ``analysis.diagnostics`` registry."""

from __future__ import annotations

from obsidiandroid.legacy.analysis_diagnostics_registry import *  # noqa: F403
from obsidiandroid.legacy.analysis_diagnostics_registry import __all__
