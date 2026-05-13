"""Legacy evaluation package shim.

Evaluation implementation modules live under ``src/obsidiandroid/evaluation``. This
package preserves legacy ``analysis.evaluation.<name>`` import paths and module
identity by registering the canonical submodules in ``sys.modules`` at package
import time (Passes 61–63).

Registration data lives in :mod:`obsidiandroid.evaluation.analysis_evaluation_shim`.
"""

from __future__ import annotations

from obsidiandroid.evaluation.analysis_evaluation_shim import (
    LEGACY_EXPORT_NAMES,
    register_analysis_evaluation_legacy_aliases,
)

register_analysis_evaluation_legacy_aliases()

__all__ = list(LEGACY_EXPORT_NAMES)
