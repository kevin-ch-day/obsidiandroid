# Filename: src/obsidiandroid/modeling/ml_classification_shim_facades.py
"""Submodule name sets for lazy ``ml_classification.*`` package facades (Pass 99+).

Centralizes allowed-name frozensets next to canonical modeling code so repo-root
``ml_classification/*/`` package ``__init__.py`` files stay thin ``__getattr__``
wrappers without duplicating lists across the legacy tree.
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

ML_CLASSIFICATION_ML_UTILS_SUBMODULES: frozenset[str] = frozenset(
    {
        "accuracy_band_utils",
        "dataset_splitter",
        "distribution_reporter",
        "feature_alignment_utils",
        "feature_label_alignment_helper",
        "ml_comparator_summary",
        "ml_eval_engine",
        "ml_result_analyzer",
        "ml_result_validator",
    }
)

ML_CLASSIFICATION_REPORTING_SUBMODULES: frozenset[str] = frozenset(
    {
        "compile_classification_results",
        "ml_report_builder",
    }
)

ML_CLASSIFICATION_TRAINING_ML_TRAINERS_SUBMODULES: frozenset[str] = frozenset(
    {
        "balanced_random_forest_trainer",
        "logistic_regression_trainer",
        "random_forest_trainer",
        "svm_trainer",
        "xgboost_trainer",
    }
)

ML_CLASSIFICATION_TRAINING_SUBMODULES: frozenset[str] = frozenset(
    {
        "data_alignment",
        "feature_schema_audit",
        "model_evaluation",
        "model_prediction",
        "model_training",
        "model_trainer_factory",
        "pipeline_core",
        "pipeline_result_promoter",
        "prediction_builder",
        "train_model_executor",
        "training_helpers",
        "ml_trainers",
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
    "ML_CLASSIFICATION_ML_UTILS_SUBMODULES",
    "ML_CLASSIFICATION_REPORTING_SUBMODULES",
    "ML_CLASSIFICATION_TRAINING_ML_TRAINERS_SUBMODULES",
    "ML_CLASSIFICATION_TRAINING_SUBMODULES",
    "ML_CLASSIFICATION_VECTORIZATION_SUBMODULES",
)
