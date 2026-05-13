# Filename: src/obsidiandroid/evaluation/analysis_evaluation_shim.py
"""Register ``analysis.evaluation.*`` :class:`sys.modules` aliases (Passes 61–63).

Single source for the evaluation legacy surface; :mod:`analysis.evaluation` calls
:func:`register_analysis_evaluation_legacy_aliases` at import time.
"""

from __future__ import annotations

import importlib
import sys

_LEGACY_PKG = "analysis.evaluation"

_LEGACY_NAME_TO_CANON: dict[str, str] = {
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


def register_analysis_evaluation_legacy_aliases() -> None:
    for name, target in _LEGACY_NAME_TO_CANON.items():
        mod = importlib.import_module(target)
        sys.modules.setdefault(f"{_LEGACY_PKG}.{name}", mod)


LEGACY_EXPORT_NAMES: tuple[str, ...] = tuple(sorted(_LEGACY_NAME_TO_CANON.keys()))

__all__ = ("LEGACY_EXPORT_NAMES", "register_analysis_evaluation_legacy_aliases")
