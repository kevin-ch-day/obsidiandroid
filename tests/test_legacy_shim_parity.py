"""Parity checks for legacy compatibility shims against canonical ``obsidiandroid.*`` modules."""

from __future__ import annotations


def test_pipeline_facade_matches_runner_public_surface() -> None:
    """``obsidiandroid.pipeline`` delegates to live ``runner`` bindings (PEP 562 __getattr__)."""
    from obsidiandroid.pipeline import runner as runner_mod
    import obsidiandroid.pipeline as facade

    assert facade.run_pipeline is runner_mod.run_pipeline
    assert facade.DIAGNOSTICS_DIR is runner_mod.DIAGNOSTICS_DIR
    assert facade.PIPELINE_MAIN_LOGGER is runner_mod.PIPELINE_MAIN_LOGGER
    assert facade.PARSER_QUALITY_PATH is runner_mod.PARSER_QUALITY_PATH

    module_pairs = (
        ("attach_engine_metadata", "analysis.pipeline.attach_engine_metadata"),
        ("av_engine_pipeline", "analysis.pipeline.av_engine_pipeline"),
        ("contract_filters", "analysis.pipeline.contract_filters"),
        ("engine_normalization", "analysis.pipeline.engine_normalization"),
        ("main_facade", "analysis.pipeline.main_facade"),
        ("runner", "analysis.pipeline.runner"),
        ("run_bounds", "analysis.pipeline.run_bounds"),
        ("runtime_policy", "analysis.pipeline.runtime_policy"),
        ("sample_exports", "analysis.pipeline.sample_exports"),
        ("sample_preparation", "analysis.pipeline.sample_preparation"),
        ("score_av_engines", "analysis.pipeline.score_av_engines"),
        ("stage_ablation", "analysis.pipeline.stage_ablation"),
        ("stage_av_vendor", "analysis.pipeline.stage_av_vendor"),
        ("stage_feature_enrichment", "analysis.pipeline.stage_feature_enrichment"),
        ("stage_manifest", "analysis.pipeline.stage_manifest"),
        ("stage_modeling", "analysis.pipeline.stage_modeling"),
        ("stage_permission_trends_report", "analysis.pipeline.stage_permission_trends_report"),
        ("stage_results_warehouse", "analysis.pipeline.stage_results_warehouse"),
        ("stage_samples", "analysis.pipeline.stage_samples"),
        ("vendor_metadata_pipeline", "analysis.pipeline.vendor_metadata_pipeline"),
    )
    import importlib

    for attr, canon_name in module_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(facade, attr) is canon_mod


def test_pipeline_physical_leaf_modules_share_identity_with_legacy_shims() -> None:
    """Canonical pipeline modules through Pass 71 share identity with ``analysis.pipeline`` shims."""
    import importlib

    for name in (
        "contract_filters",
        "run_bounds",
        "runtime_policy",
        "runner",
        "main_facade",
        "stage_samples",
        "sample_exports",
        "stage_av_vendor",
        "stage_manifest",
        "sample_preparation",
        "stage_feature_enrichment",
        "stage_modeling",
        "stage_ablation",
        "stage_results_warehouse",
        "stage_permission_trends_report",
        "engine_pipeline_utils",
        "attach_engine_metadata",
        "engine_normalization",
        "score_av_engines",
        "av_engine_pipeline",
        "vendor_metadata_pipeline",
    ):
        physical = importlib.import_module(f"obsidiandroid.pipeline.{name}")
        legacy = importlib.import_module(f"analysis.pipeline.{name}")
        assert physical is legacy


def test_analysis_pipeline_nested_package_submodules_resolve_to_canonical_modules() -> None:
    """Nested legacy package imports keep working after ordinary leaf shim retirement."""
    import importlib

    pairs = (
        ("analysis.pipeline.artifacts.paths", "obsidiandroid.pipeline.artifacts.paths"),
        ("analysis.pipeline.artifacts.registry", "obsidiandroid.pipeline.artifacts.registry"),
        ("analysis.pipeline.governance.exceptions", "obsidiandroid.governance.exceptions"),
        ("analysis.pipeline.governance.integrity", "obsidiandroid.governance.integrity"),
        ("analysis.pipeline.governance.policy", "obsidiandroid.governance.policy"),
        ("analysis.pipeline.governance.readiness", "obsidiandroid.governance.readiness"),
        ("analysis.pipeline.manifest.builder", "obsidiandroid.pipeline.manifest.builder"),
        ("analysis.pipeline.manifest.hashing", "obsidiandroid.pipeline.manifest.hashing"),
        (
            "analysis.pipeline.manifest.paper_compliance_checks",
            "obsidiandroid.pipeline.manifest.paper_compliance_checks",
        ),
        (
            "analysis.pipeline.manifest.paper_figure_renderers",
            "obsidiandroid.pipeline.manifest.paper_figure_renderers",
        ),
        ("analysis.pipeline.manifest.runtime_support", "obsidiandroid.pipeline.manifest.runtime_support"),
        ("analysis.pipeline.manifest.schema", "obsidiandroid.pipeline.manifest.schema"),
        ("analysis.pipeline.manifest.writer", "obsidiandroid.pipeline.manifest.writer"),
        (
            "analysis.pipeline.permission_trends.bundle_manifest",
            "obsidiandroid.pipeline.permission_trends.bundle_manifest",
        ),
        (
            "analysis.pipeline.permission_trends.constants",
            "obsidiandroid.pipeline.permission_trends.constants",
        ),
        (
            "analysis.pipeline.permission_trends.publish_paths",
            "obsidiandroid.pipeline.permission_trends.publish_paths",
        ),
        (
            "analysis.pipeline.permission_trends.reporting_support",
            "obsidiandroid.pipeline.permission_trends.reporting_support",
        ),
        (
            "analysis.pipeline.permission_trends.sample_permission_data",
            "obsidiandroid.pipeline.permission_trends.sample_permission_data",
        ),
        (
            "analysis.pipeline.permission_trends.stats_core",
            "obsidiandroid.pipeline.permission_trends.stats_core",
        ),
    )
    for legacy_name, canon_name in pairs:
        legacy_mod = importlib.import_module(legacy_name)
        canon_mod = importlib.import_module(canon_name)
        assert legacy_mod is canon_mod


def test_analysis_pipeline_nested_package_imports_resolve_to_canonical_packages() -> None:
    """Nested legacy package imports resolve through root alias registration."""
    import importlib

    pairs = (
        ("analysis.pipeline.artifacts", "obsidiandroid.pipeline.artifacts"),
        ("analysis.pipeline.governance", "obsidiandroid.governance"),
        ("analysis.pipeline.manifest", "obsidiandroid.pipeline.manifest"),
        ("analysis.pipeline.permission_trends", "obsidiandroid.pipeline.permission_trends"),
    )
    for legacy_name, canon_name in pairs:
        legacy_mod = importlib.import_module(legacy_name)
        canon_mod = importlib.import_module(canon_name)
        assert legacy_mod is canon_mod


def test_ml_facades_match_ml_classification_modules() -> None:
    """Pass 47+ canonical ML facades preserve identity with legacy shim modules."""
    import importlib

    from obsidiandroid.features.features_facade_manifest import FEATURES_FACADE_ALIAS_TARGETS
    from obsidiandroid.modeling.modeling_facade_manifest import (
        MODELING_FACADE_EAGER_SUBMODULE_NAMES,
        MODELING_FACADE_LEGACY_VIA_ML_CLASSIFICATION_TRAINING,
    )

    import obsidiandroid.features as features_facade
    import obsidiandroid.modeling as modeling_facade

    for attr in MODELING_FACADE_EAGER_SUBMODULE_NAMES:
        canon_name = f"obsidiandroid.modeling.{attr}"
        canon_mod = importlib.import_module(canon_name)
        assert getattr(modeling_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.modeling.{attr}")
        assert alias_mod is canon_mod
        assert attr not in MODELING_FACADE_LEGACY_VIA_ML_CLASSIFICATION_TRAINING

    for attr, canon_name in FEATURES_FACADE_ALIAS_TARGETS:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(features_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.features.{attr}")
        assert alias_mod is canon_mod

def test_labeling_taxonomy_is_wrapper_not_legacy_module_alias() -> None:
    """Pass 58: taxonomy lives under ``src/`` and wraps rather than aliases legacy helpers."""
    import importlib
    from pathlib import Path

    tax = importlib.import_module("obsidiandroid.labeling.taxonomy")
    canon = importlib.import_module("obsidiandroid.labeling.malware_family_constants")
    assert tax is not canon
    path = Path(tax.__file__).resolve()
    assert path.name == "taxonomy.py"
    assert "obsidiandroid" in path.parts and "labeling" in path.parts
    assert tax.normalize_family_name("Flu-Bot") == canon.normalize_family_name("Flu-Bot")


def test_malware_family_constants_canonical_behavior() -> None:
    """Malware-family constants live canonically under ``obsidiandroid.labeling``."""
    import importlib

    canon = importlib.import_module("obsidiandroid.labeling.malware_family_constants")
    assert canon.normalize_family_name("Flu-Bot") == "flubot"
    assert canon.canonicalize_family_label("Cabassous") == "FluBot"
    assert canon.normalize_family_name("Toxic Panda") == "toxicpanda"
    assert canon.canonicalize_family_label("GravityRAT") == "GravityRAT"
    assert canon.normalize_family_name("PixPirate") == "pixpirate"
    assert canon.canonicalize_family_label("BlankBot") == "BlankBot"


def test_ml_classification_ml_utils_namespace_is_retired() -> None:
    """``ml_utils`` compatibility imports are intentionally retired."""
    import importlib
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.ml_utils")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.ml_utils.distribution_reporter")


def test_ml_classification_training_namespace_is_retired() -> None:
    """Legacy training compatibility imports are intentionally retired."""
    import importlib
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.training")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.training.pipeline_core")


def test_ml_classification_training_ml_trainers_namespace_is_retired() -> None:
    """Legacy trainer subpackage imports are intentionally retired."""
    import importlib
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.training.ml_trainers")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("ml_classification.training.ml_trainers.random_forest_trainer")


def test_labeling_classification_builder_inference_and_engine_weights_packages_export_canonical_modules() -> None:
    """Canonical package attributes expose the remaining physically canonical helper modules."""
    import importlib

    package_to_names = {
        "obsidiandroid.labeling": (
            "classification_label_resolver",
            "label_builder_wrapper",
            "label_field_normalizer",
            "label_format_generator",
            "label_input_validator",
            "label_postprocessor",
        ),
        "obsidiandroid.classification_builder": (
            "classification_constants",
            "classification_row_builder",
            "prediction_utils",
            "record_enrichment",
            "sample_classification_builder",
            "vendor_record_selector",
        ),
        "obsidiandroid.inference": (
            "label_consensus_engine",
            "malware_type_engine",
            "signal_health_checker",
            "threat_class_engine",
        ),
        "obsidiandroid.engine_weights": (
            "assign_detection_tiers",
            "build_classification_weights",
            "classification_weight_inspector",
            "classification_weight_utils",
            "compute_reliability_score",
            "engine_weights_utils",
        ),
    }
    for pkg_name, names in package_to_names.items():
        pkg = importlib.import_module(pkg_name)
        for name in names:
            sub = importlib.import_module(f"{pkg_name}.{name}")
            assert getattr(pkg, name) is sub

def test_vendors_facade_matches_vendor_processing_modules() -> None:
    """Pass 59+: vendors facade points at canonical parsing package."""
    import importlib

    import obsidiandroid.vendors as vendors_facade

    canon_mod = importlib.import_module("obsidiandroid.vendors.parsing.vendor_parser_map")
    assert getattr(vendors_facade, "vendor_parser_map") is canon_mod
    alias_mod = importlib.import_module("obsidiandroid.vendors.vendor_parser_map")
    assert alias_mod is canon_mod


def test_vendors_parsing_modules_match_package_attributes() -> None:
    """Vendor parser package attributes resolve to canonical submodules."""
    import importlib

    from obsidiandroid.vendors.parsing.vendor_parser_submodule_manifest import (
        VENDOR_PARSER_SUBMODULE_NAMES,
    )

    import obsidiandroid.vendors.parsing as parsing_pkg

    for name in VENDOR_PARSER_SUBMODULE_NAMES:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{name}")
        assert getattr(parsing_pkg, name) is canon_mod


def test_evaluation_package_exports_canonical_modules() -> None:
    """Evaluation package attributes resolve to canonical submodules."""
    import importlib

    import obsidiandroid.evaluation as evaluation_pkg

    for name in evaluation_pkg.__all__:
        if name in {"VendorClassificationParseResult", "parse_vendor_classifications"}:
            continue
        canon_mod = importlib.import_module(f"obsidiandroid.evaluation.{name}")
        assert getattr(evaluation_pkg, name) is canon_mod

    for mod in ("ml_eval_engine", "ml_comparator_summary", "accuracy_band_utils"):
        importlib.import_module(f"obsidiandroid.evaluation.{mod}")


def test_vendor_execution_package_exports_match_canonical_modules() -> None:
    """Vendor execution package exports resolve to canonical submodules."""
    import importlib

    import obsidiandroid.vendors.execution as execution_pkg

    for name in execution_pkg.__all__:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.execution.{name}")
        assert canon_mod.__name__ == f"obsidiandroid.vendors.execution.{name}"

def test_diagnostics_facade_modules_match_canonical_submodules() -> None:
    """Diagnostics package attributes resolve to canonical submodules."""
    import importlib

    import obsidiandroid.diagnostics as facade

    top_level_names = (
        "ablation_cohort_diagnostics",
        "alignment_gap_diagnostics",
        "cohort_foundation_export",
        "cohort_sample_id_audit",
        "cohort_vocabulary",
        "feature_builder_drop_trace",
        "feature_build_coverage_export",
        "feature_column_survival_export",
        "feature_lineage_report",
        "feature_matrix_gap_lineage",
        "family_label_taxonomy_audit",
        "reproducibility_workbench",
        "fused_permission_matrix_audit",
        "headline_evaluation_export",
        "output_artifact_policy",
        "rf_feature_importance_export",
        "split_ledger_resolve",
        "output_inventory",
        "permission_training_survival_audit",
    )
    for name in top_level_names:
        canon = importlib.import_module(f"obsidiandroid.diagnostics.{name}")
        assert getattr(facade, name) is canon

    for pkg in ("research_validity", "hostile_audit"):
        canon_pkg = importlib.import_module(f"obsidiandroid.diagnostics.{pkg}")
        assert getattr(facade, pkg) is canon_pkg
        bundle_canon = importlib.import_module(f"obsidiandroid.diagnostics.{pkg}.bundle")
        assert bundle_canon is getattr(canon_pkg, "bundle")


def test_database_facade_modules_match_legacy_database_shims() -> None:
    """``obsidiandroid.database`` exposes the same modules as legacy ``database.*`` shims."""
    import importlib

    from obsidiandroid.database.facade_manifest import FACADE_MODULE_PAIRS, LEGACY_SHIM_PAIRS

    import obsidiandroid.database as facade

    for attr, canon_name in FACADE_MODULE_PAIRS:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.database.{attr}")
        assert alias_mod is canon_mod

    for attr, legacy_name in LEGACY_SHIM_PAIRS:
        assert importlib.import_module(legacy_name) is importlib.import_module(
            f"obsidiandroid.database.{attr}"
        )
