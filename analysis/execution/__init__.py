"""Legacy vendor execution package shim.

Implementation for vendor parser execution moved to
``obsidiandroid.vendors.execution``. This package preserves legacy
``analysis.execution.<name>`` import paths and module identity by registering
the canonical submodules in ``sys.modules`` at package import time.

Registration data lives in :mod:`obsidiandroid.vendors.execution.analysis_execution_shim`.
"""

from __future__ import annotations

from obsidiandroid.vendors.execution.analysis_execution_shim import (
    LEGACY_EXPORT_NAMES,
    register_analysis_execution_legacy_aliases,
)

register_analysis_execution_legacy_aliases()

__all__ = list(LEGACY_EXPORT_NAMES)
