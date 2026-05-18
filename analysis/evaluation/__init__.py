"""Legacy evaluation package shim.

Evaluation implementation modules live under ``src/obsidiandroid/evaluation``. This
package preserves legacy ``analysis.evaluation.<name>`` import paths and module
identity by registering the canonical submodules in ``sys.modules`` at package
import time (Passes 61–63).

Registration data lives in :mod:`obsidiandroid.legacy.analysis_evaluation_registry`.
"""

from __future__ import annotations

from obsidiandroid.legacy.analysis_evaluation_registry import (
    LEGACY_EXPORT_NAMES,
    register_analysis_evaluation_legacy_aliases,
)

register_analysis_evaluation_legacy_aliases()

__all__ = list(LEGACY_EXPORT_NAMES)
