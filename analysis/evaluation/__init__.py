"""Legacy evaluation package shim.

Evaluation implementation modules live under ``src/obsidiandroid/evaluation``. This
package preserves legacy ``analysis.evaluation.<name>`` import paths and module
identity by registering the canonical submodules in ``sys.modules`` at package
import time (Passes 61–63).
"""

from __future__ import annotations

import importlib
import sys

_MOVED_SUBMODULES: dict[str, str] = {
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

for _name, _target in _MOVED_SUBMODULES.items():
    _mod = importlib.import_module(_target)
    sys.modules.setdefault(f"{__name__}.{_name}", _mod)

__all__ = sorted(_MOVED_SUBMODULES.keys())

del _MOVED_SUBMODULES, _name, _target, _mod
