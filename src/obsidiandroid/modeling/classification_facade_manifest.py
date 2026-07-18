"""Canonical classification-package facade submodule names.

Used by :mod:`scripts.dev.check_import_surface` to keep the package
facades for labeling, classification building, inference, and engine weights
aligned with their physical canonical modules.
"""

from __future__ import annotations

CLASSIFICATION_BUILDER_FACADE_SUBMODULE_NAMES: frozenset[str] = frozenset(
    {
        "classification_constants",
        "classification_row_builder",
        "prediction_utils",
        "record_enrichment",
        "sample_classification_builder",
        "vendor_record_selector",
    }
)

ENGINE_WEIGHT_FACADE_SUBMODULE_NAMES: frozenset[str] = frozenset(
    {
        "assign_detection_tiers",
        "build_classification_weights",
        "classification_weight_inspector",
        "classification_weight_utils",
        "compute_reliability_score",
        "engine_weights_utils",
    }
)

INFERENCE_FACADE_SUBMODULE_NAMES: frozenset[str] = frozenset(
    {
        "label_consensus_engine",
        "malware_type_engine",
        "signal_health_checker",
        "threat_class_engine",
    }
)

LABELING_FACADE_SUBMODULE_NAMES: frozenset[str] = frozenset(
    {
        "classification_label_resolver",
        "label_builder_wrapper",
        "label_field_normalizer",
        "label_format_generator",
        "label_input_validator",
        "label_postprocessor",
    }
)

__all__ = (
    "CLASSIFICATION_BUILDER_FACADE_SUBMODULE_NAMES",
    "ENGINE_WEIGHT_FACADE_SUBMODULE_NAMES",
    "INFERENCE_FACADE_SUBMODULE_NAMES",
    "LABELING_FACADE_SUBMODULE_NAMES",
)
