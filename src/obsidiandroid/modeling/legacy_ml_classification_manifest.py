"""Legacy ``ml_classification.*`` shim submodule manifests.

These name sets exist to keep repo-root compatibility shims thin while the canonical
implementation surface lives under ``src/obsidiandroid``.
"""

from __future__ import annotations

ML_CLASSIFICATION_BUILDER_SUBMODULES: frozenset[str] = frozenset(
    {
        "classification_constants",
        "classification_row_builder",
        "prediction_utils",
        "record_enrichment",
        "sample_classification_builder",
        "vendor_record_selector",
    }
)

ML_CLASSIFICATION_COMMON_SUBMODULES: frozenset[str] = frozenset({"malware_family_constants"})

ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES: frozenset[str] = frozenset(
    {
        "assign_detection_tiers",
        "build_classification_weights",
        "classification_weight_inspector",
        "classification_weight_utils",
        "compute_reliability_score",
        "engine_weights_utils",
    }
)

ML_CLASSIFICATION_INFERENCE_SUBMODULES: frozenset[str] = frozenset(
    {
        "label_consensus_engine",
        "malware_type_engine",
        "signal_health_checker",
        "threat_class_engine",
    }
)

ML_CLASSIFICATION_LABELING_SUBMODULES: frozenset[str] = frozenset(
    {
        "classification_label_resolver",
        "label_builder_wrapper",
        "label_field_normalizer",
        "label_format_generator",
        "label_input_validator",
        "label_postprocessor",
    }
)

ML_CLASSIFICATION_REPORTING_SUBMODULES: frozenset[str] = frozenset(
    {
        "compile_classification_results",
        "ml_report_builder",
    }
)

ML_CLASSIFICATION_VECTORIZATION_SUBMODULES: frozenset[str] = frozenset(
    {
        "feature_encoder",
        "feature_engine_selection",
        "feature_vendor_extractor",
        "feature_vector_builder",
    }
)


__all__ = (
    "ML_CLASSIFICATION_BUILDER_SUBMODULES",
    "ML_CLASSIFICATION_COMMON_SUBMODULES",
    "ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES",
    "ML_CLASSIFICATION_INFERENCE_SUBMODULES",
    "ML_CLASSIFICATION_LABELING_SUBMODULES",
    "ML_CLASSIFICATION_REPORTING_SUBMODULES",
    "ML_CLASSIFICATION_VECTORIZATION_SUBMODULES",
)
