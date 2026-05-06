"""Evaluation canonical surface.

Implementation modules live in this package. Legacy ``analysis.evaluation.<name>``
paths remain valid via :mod:`analysis.evaluation` registering submodules at
package import time (Passes 61–63; **Pass 94** adds classifier training eval and
reporting helpers with matching ``ml_classification.*`` identity shims).
"""

from __future__ import annotations

import importlib
import sys

_LEGACY_BY_CANONICAL = {
    "accuracy_band_utils": "obsidiandroid.evaluation.accuracy_band_utils",
    "av_results_fetcher": "obsidiandroid.evaluation.av_results_fetcher",
    "engine_scoring_summary": "obsidiandroid.evaluation.engine_scoring_summary",
    "evaluate_av_classifications": "obsidiandroid.evaluation.evaluate_av_classifications",
    "ml_comparator_summary": "obsidiandroid.evaluation.ml_comparator_summary",
    "ml_eval_engine": "obsidiandroid.evaluation.ml_eval_engine",
    "ml_report_builder": "obsidiandroid.evaluation.ml_report_builder",
    "model_tuning": "obsidiandroid.evaluation.model_tuning",
    "random_forest_diagnostics": "obsidiandroid.evaluation.random_forest_diagnostics",
    "vendor_classification_inspector": "obsidiandroid.evaluation.vendor_classification_inspector",
    "vendor_classification_parser": "obsidiandroid.evaluation.vendor_classification_parser",
    "vendor_feature_extractor": "obsidiandroid.evaluation.vendor_feature_extractor",
    "vendor_parser_matching": "obsidiandroid.evaluation.vendor_parser_matching",
    "vendor_parser_utils": "obsidiandroid.evaluation.vendor_parser_utils",
    "vendor_score_calculator": "obsidiandroid.evaluation.vendor_score_calculator",
    "vendor_summary_builder": "obsidiandroid.evaluation.vendor_summary_builder",
}


def __getattr__(name: str):
    if name not in _LEGACY_BY_CANONICAL:
        raise AttributeError(name)
    mod = importlib.import_module(_LEGACY_BY_CANONICAL[name])
    globals()[name] = mod
    sys.modules.setdefault(f"obsidiandroid.evaluation.{name}", mod)
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LEGACY_BY_CANONICAL.keys()))


__all__ = sorted(_LEGACY_BY_CANONICAL.keys())
