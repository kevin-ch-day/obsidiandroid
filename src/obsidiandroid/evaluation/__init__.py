"""Canonical evaluation namespace.

Implementation modules live in this package.
"""

from __future__ import annotations

import importlib

from obsidiandroid.evaluation.vendor_classification_parser import (
    VendorClassificationParseResult,  # noqa: F401
    parse_vendor_classifications,  # noqa: F401
)

_LAZY_CANONICAL_SUBMODULES = {
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
    if name not in _LAZY_CANONICAL_SUBMODULES:
        raise AttributeError(name)
    mod = importlib.import_module(_LAZY_CANONICAL_SUBMODULES[name])
    globals()[name] = mod
    return mod


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LAZY_CANONICAL_SUBMODULES.keys()))


__all__ = sorted(_LAZY_CANONICAL_SUBMODULES.keys())

# Stable function entrypoints (so callers don't need to import deep submodules).
__all__.extend(["VendorClassificationParseResult", "parse_vendor_classifications"])
