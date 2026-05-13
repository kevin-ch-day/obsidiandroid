"""Lightweight checks for new ``obsidiandroid.*`` package surfaces (no slow integration)."""

from __future__ import annotations

import pytest


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


def test_ml_facades_match_ml_classification_modules() -> None:
    """Pass 47: minimal ML facades alias legacy module objects."""
    import importlib

    import obsidiandroid.features as features_facade
    import obsidiandroid.labeling as labeling_facade
    import obsidiandroid.modeling as modeling_facade

    modeling_pairs = (
        ("data_alignment", "obsidiandroid.modeling.data_alignment"),
        ("distribution_reporter", "obsidiandroid.modeling.distribution_reporter"),
        ("feature_label_alignment_helper", "obsidiandroid.modeling.feature_label_alignment_helper"),
        ("ml_result_analyzer", "obsidiandroid.modeling.ml_result_analyzer"),
        ("ml_result_validator", "obsidiandroid.modeling.ml_result_validator"),
        ("model_prediction", "obsidiandroid.modeling.model_prediction"),
        ("model_trainer_factory", "obsidiandroid.modeling.model_trainer_factory"),
        ("pipeline_core", "obsidiandroid.modeling.pipeline_core"),
    )
    for attr, canon_name in modeling_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(modeling_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.modeling.{attr}")
        assert alias_mod is canon_mod
        if attr in {
            "data_alignment",
            "distribution_reporter",
            "feature_label_alignment_helper",
            "ml_result_analyzer",
            "ml_result_validator",
            "model_prediction",
            "model_trainer_factory",
            "pipeline_core",
        }:
            if attr in {
                "data_alignment",
                "model_prediction",
                "model_trainer_factory",
                "pipeline_core",
            }:
                legacy_mod = importlib.import_module(f"ml_classification.training.{attr}")
            else:
                legacy_mod = importlib.import_module(f"ml_classification.ml_utils.{attr}")
            assert legacy_mod is canon_mod
    feature_alignment_canon = importlib.import_module("obsidiandroid.modeling.feature_alignment_utils")
    feature_alignment_legacy = importlib.import_module("ml_classification.ml_utils.feature_alignment_utils")
    assert feature_alignment_legacy is feature_alignment_canon

    for mod in (
        "pipeline_result_promoter",
        "train_model_executor",
        "model_training",
        "prediction_builder",
        "model_evaluation",
        "training_helpers",
    ):
        canon_tm = importlib.import_module(f"obsidiandroid.modeling.{mod}")
        legacy_tm = importlib.import_module(f"ml_classification.training.{mod}")
        assert legacy_tm is canon_tm
    for mod in (
        "random_forest_trainer",
        "balanced_random_forest_trainer",
        "logistic_regression_trainer",
        "svm_trainer",
        "xgboost_trainer",
    ):
        canon_tr = importlib.import_module(f"obsidiandroid.modeling.ml_trainers.{mod}")
        legacy_tr = importlib.import_module(f"ml_classification.training.ml_trainers.{mod}")
        assert legacy_tr is canon_tr

    features_pairs = (
        ("feature_encoder", "obsidiandroid.features.vectorization.feature_encoder"),
        ("feature_engine_selection", "obsidiandroid.features.vectorization.feature_engine_selection"),
        ("feature_schema_audit", "obsidiandroid.features.feature_schema_audit"),
        ("feature_vector_builder", "obsidiandroid.features.vectorization.feature_vector_builder"),
        ("feature_vendor_extractor", "obsidiandroid.features.vectorization.feature_vendor_extractor"),
    )
    for attr, canon_name in features_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(features_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.features.{attr}")
        assert alias_mod is canon_mod
        if attr == "feature_schema_audit":
            legacy_mod = importlib.import_module("ml_classification.training.feature_schema_audit")
        else:
            legacy_mod = importlib.import_module(f"ml_classification.vectorization.{attr}")
        assert legacy_mod is canon_mod

    labeling_pairs = (
        ("classification_label_resolver", "obsidiandroid.labeling.classification_label_resolver"),
        ("label_builder_wrapper", "obsidiandroid.labeling.label_builder_wrapper"),
        ("label_field_normalizer", "obsidiandroid.labeling.label_field_normalizer"),
        ("label_format_generator", "obsidiandroid.labeling.label_format_generator"),
        ("label_input_validator", "obsidiandroid.labeling.label_input_validator"),
        ("label_postprocessor", "obsidiandroid.labeling.label_postprocessor"),
    )
    for attr, canon_name in labeling_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(labeling_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.labeling.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"ml_classification.labeling.{attr}")
        assert legacy_mod is canon_mod

    cb_facade = importlib.import_module("obsidiandroid.classification_builder")
    for name in (
        "classification_constants",
        "classification_row_builder",
        "prediction_utils",
        "record_enrichment",
        "sample_classification_builder",
        "vendor_record_selector",
    ):
        canon_cb = importlib.import_module(f"obsidiandroid.classification_builder.{name}")
        assert getattr(cb_facade, name) is canon_cb
        assert importlib.import_module(f"ml_classification.builder.{name}") is canon_cb

    inf_facade = importlib.import_module("obsidiandroid.inference")
    for name in (
        "label_consensus_engine",
        "malware_type_engine",
        "signal_health_checker",
        "threat_class_engine",
    ):
        canon_inf = importlib.import_module(f"obsidiandroid.inference.{name}")
        assert getattr(inf_facade, name) is canon_inf
        assert importlib.import_module(f"ml_classification.inference.{name}") is canon_inf

    ew_facade = importlib.import_module("obsidiandroid.engine_weights")
    for name in (
        "assign_detection_tiers",
        "build_classification_weights",
        "classification_weight_inspector",
        "classification_weight_utils",
        "compute_reliability_score",
        "engine_weights_utils",
    ):
        canon_ew = importlib.import_module(f"obsidiandroid.engine_weights.{name}")
        assert getattr(ew_facade, name) is canon_ew
        assert importlib.import_module(f"ml_classification.engine_weights.{name}") is canon_ew

    assert (
        importlib.import_module("ml_classification.reporting.compile_classification_results")
        is importlib.import_module("obsidiandroid.reporting.compile_classification_results")
    )


def test_labeling_taxonomy_is_wrapper_not_legacy_module_alias() -> None:
    """Pass 58: taxonomy lives under ``src/`` and wraps (not aliases) legacy helpers."""
    import importlib
    from pathlib import Path

    tax = importlib.import_module("obsidiandroid.labeling.taxonomy")
    legacy = importlib.import_module("ml_classification.common.malware_family_constants")
    assert tax is not legacy
    path = Path(tax.__file__).resolve()
    assert path.name == "taxonomy.py"
    assert "obsidiandroid" in path.parts and "labeling" in path.parts


def test_malware_family_constants_legacy_shim_matches_canonical_module() -> None:
    """Malware-family constants live canonically under ``obsidiandroid.labeling``."""
    import importlib

    canon = importlib.import_module("obsidiandroid.labeling.malware_family_constants")
    legacy = importlib.import_module("ml_classification.common.malware_family_constants")
    assert legacy is canon
    assert canon.normalize_family_name("Flu-Bot") == "flubot"
    assert canon.canonicalize_family_label("Cabassous") == "FluBot"


def test_ml_classification_common_and_ml_utils_packages_lazy_attributes() -> None:
    """Pass 99: legacy package ``__getattr__`` matches explicit submodule imports."""
    import importlib

    mlu = importlib.import_module("ml_classification.ml_utils")
    mlu_ds = importlib.import_module("ml_classification.ml_utils.dataset_splitter")
    assert getattr(mlu, "dataset_splitter") is mlu_ds

    mlc = importlib.import_module("ml_classification.common")
    mlc_mfc = importlib.import_module("ml_classification.common.malware_family_constants")
    assert getattr(mlc, "malware_family_constants") is mlc_mfc


def test_ml_classification_subpackages_lazy_attributes_pass100() -> None:
    """Pass 100: shim subpackages expose known leaf names via ``__getattr__``."""
    import importlib

    slices: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "ml_classification.builder",
            (
                "classification_constants",
                "classification_row_builder",
                "prediction_utils",
                "record_enrichment",
                "sample_classification_builder",
                "vendor_record_selector",
            ),
        ),
        (
            "ml_classification.inference",
            (
                "label_consensus_engine",
                "malware_type_engine",
                "signal_health_checker",
                "threat_class_engine",
            ),
        ),
        (
            "ml_classification.engine_weights",
            (
                "assign_detection_tiers",
                "build_classification_weights",
                "classification_weight_inspector",
                "classification_weight_utils",
                "compute_reliability_score",
                "engine_weights_utils",
            ),
        ),
        (
            "ml_classification.labeling",
            (
                "classification_label_resolver",
                "label_builder_wrapper",
                "label_field_normalizer",
                "label_format_generator",
                "label_input_validator",
                "label_postprocessor",
            ),
        ),
        (
            "ml_classification.reporting",
            ("compile_classification_results", "ml_report_builder"),
        ),
        (
            "ml_classification.vectorization",
            (
                "feature_encoder",
                "feature_engine_selection",
                "feature_vendor_extractor",
                "feature_vector_builder",
            ),
        ),
        (
            "ml_classification.training",
            (
                "data_alignment",
                "feature_schema_audit",
                "model_evaluation",
                "model_prediction",
                "model_training",
                "model_trainer_factory",
                "ml_trainers",
                "pipeline_core",
                "pipeline_result_promoter",
                "prediction_builder",
                "train_model_executor",
                "training_helpers",
            ),
        ),
        (
            "ml_classification.training.ml_trainers",
            (
                "balanced_random_forest_trainer",
                "logistic_regression_trainer",
                "random_forest_trainer",
                "svm_trainer",
                "xgboost_trainer",
            ),
        ),
    )
    for pkg_qual, names in slices:
        pkg = importlib.import_module(pkg_qual)
        for name in names:
            sub = importlib.import_module(f"{pkg_qual}.{name}")
            assert getattr(pkg, name) is sub


def test_pipeline_manifest_facade_matches_manifest_modules() -> None:
    """Pipeline manifest: canonical under ``obsidiandroid.pipeline.manifest``; analysis shims match."""
    import importlib

    import obsidiandroid.pipeline.manifest as manifest_facade

    manifest_pairs = (
        ("hashing", "obsidiandroid.pipeline.manifest.hashing"),
        ("paper_compliance_checks", "obsidiandroid.pipeline.manifest.paper_compliance_checks"),
        ("paper_figure_renderers", "obsidiandroid.pipeline.manifest.paper_figure_renderers"),
        ("runtime_support", "obsidiandroid.pipeline.manifest.runtime_support"),
        ("writer", "obsidiandroid.pipeline.manifest.writer"),
    )
    for attr, canon_name in manifest_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(manifest_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.manifest.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.pipeline.manifest.{attr}")
        assert legacy_mod is canon_mod


def test_pipeline_artifacts_facade_matches_artifact_modules() -> None:
    """Pipeline artifacts: canonical under ``obsidiandroid.pipeline.artifacts``; analysis shims match."""
    import importlib

    import obsidiandroid.pipeline.artifacts as artifacts_facade

    artifacts_pairs = (
        ("paths", "obsidiandroid.pipeline.artifacts.paths"),
        ("registry", "obsidiandroid.pipeline.artifacts.registry"),
    )
    for attr, canon_name in artifacts_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(artifacts_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.artifacts.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.pipeline.artifacts.{attr}")
        assert legacy_mod is canon_mod


def test_feature_engineering_facade_matches_analysis_shims() -> None:
    """Pass 78: vendor/feature helpers under ``obsidiandroid.feature_engineering``; legacy paths match."""
    import importlib

    fe_pairs = (
        ("assign_tier_scores", "obsidiandroid.feature_engineering.assign_tier_scores"),
        ("compute_vendor_scores", "obsidiandroid.feature_engineering.compute_vendor_scores"),
        ("prepare_engine_metrics", "obsidiandroid.feature_engineering.prepare_engine_metrics"),
        ("pattern_analysis", "obsidiandroid.feature_engineering.pattern_analysis"),
    )
    for attr, canon_name in fe_pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.feature_engineering.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.feature_engineering.{attr}")
        assert legacy_mod is canon_mod


def test_orchestration_submodules_match_analysis_shims() -> None:
    """Pass 80: orchestration helpers under ``obsidiandroid.orchestration``; legacy paths match."""
    import importlib

    pairs = (
        ("metadata_features", "obsidiandroid.orchestration.metadata_features"),
        ("methodology_artifacts", "obsidiandroid.orchestration.methodology_artifacts"),
        ("permission_features", "obsidiandroid.orchestration.permission_features"),
        ("profile_filters", "obsidiandroid.orchestration.profile_filters"),
        ("runtime_reporting", "obsidiandroid.orchestration.runtime_reporting"),
    )
    for attr, canon_name in pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.orchestration.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.orchestration.{attr}")
        assert legacy_mod is canon_mod


def test_matrix_submodules_match_analysis_shims() -> None:
    """Pass 80: AV matrix helpers under ``obsidiandroid.matrix``; legacy paths match."""
    import importlib

    pairs = (
        ("av_binary_matrix_builder", "obsidiandroid.matrix.av_binary_matrix_builder"),
        ("enrich_malicious_scores", "obsidiandroid.matrix.enrich_malicious_scores"),
        ("enrich_score_features", "obsidiandroid.matrix.enrich_score_features"),
    )
    for attr, canon_name in pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.matrix.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.matrix.{attr}")
        assert legacy_mod is canon_mod


def test_risk_band_submodules_match_analysis_shims() -> None:
    """Pass 81: risk band helpers under ``obsidiandroid.risk_band``; legacy paths match."""
    import importlib

    pairs = (
        ("assign_risk_band", "obsidiandroid.risk_band.assign_risk_band"),
        ("phase_score_engines", "obsidiandroid.risk_band.phase_score_engines"),
    )
    for attr, canon_name in pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.risk_band.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.risk_band.{attr}")
        assert legacy_mod is canon_mod


def test_pipeline_permission_trends_facade_matches_permission_trends_modules() -> None:
    """Pipeline permission-trends facade aliases canonical modules (**Pass 74**); legacy paths match."""
    import importlib

    import obsidiandroid.pipeline.permission_trends as permission_trends_facade

    permission_trends_pairs = (
        ("bundle_manifest", "obsidiandroid.pipeline.permission_trends.bundle_manifest"),
        ("constants", "obsidiandroid.pipeline.permission_trends.constants"),
        ("publish_paths", "obsidiandroid.pipeline.permission_trends.publish_paths"),
        ("reporting_support", "obsidiandroid.pipeline.permission_trends.reporting_support"),
        ("sample_permission_data", "obsidiandroid.pipeline.permission_trends.sample_permission_data"),
        ("stats_core", "obsidiandroid.pipeline.permission_trends.stats_core"),
    )
    for attr, canon_name in permission_trends_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(permission_trends_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.permission_trends.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.pipeline.permission_trends.{attr}")
        assert legacy_mod is canon_mod


def test_vendors_facade_matches_vendor_processing_modules() -> None:
    """Pass 59: vendors facade points at canonical parsing package with legacy parity."""
    import importlib

    import obsidiandroid.vendors as vendors_facade

    vendors_pairs = (
        ("vendor_parser_map", "obsidiandroid.vendors.parsing.vendor_parser_map"),
    )
    for attr, canon_name in vendors_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(vendors_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.vendors.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.vendor_processing.{attr}")
        assert legacy_mod is canon_mod


def test_vendors_parsing_modules_match_legacy_shim_identity() -> None:
    """Pass 59: key parser modules preserve ModuleType identity via legacy shim."""
    import importlib

    import obsidiandroid.vendors.parsing as parsing_pkg

    keys = (
        "generic_label_parser",
        "vendor_parser_map",
        "parser_defaults",
        "parser_confidence_estimator",
    )
    for name in keys:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{name}")
        assert getattr(parsing_pkg, name) is canon_mod
        legacy_mod = importlib.import_module(f"analysis.vendor_processing.{name}")
        assert legacy_mod is canon_mod


def test_evaluation_leaf_shims_match_canonical_modules() -> None:
    """Passes 61–63: analysis.evaluation package shim preserves module identity."""
    import importlib

    for name in (
        "accuracy_band_utils",
        "av_results_fetcher",
        "engine_scoring_summary",
        "evaluate_av_classifications",
        "ml_comparator_summary",
        "ml_eval_engine",
        "ml_report_builder",
        "model_tuning",
        "random_forest_diagnostics",
        "vendor_classification_inspector",
        "vendor_classification_parser",
        "vendor_feature_extractor",
        "vendor_parser_matching",
        "vendor_parser_utils",
        "vendor_score_calculator",
        "vendor_summary_builder",
    ):
        canon_mod = importlib.import_module(f"obsidiandroid.evaluation.{name}")
        legacy_mod = importlib.import_module(f"analysis.evaluation.{name}")
        assert legacy_mod is canon_mod

    for mod in ("ml_eval_engine", "ml_comparator_summary", "accuracy_band_utils"):
        canon_ml = importlib.import_module(f"obsidiandroid.evaluation.{mod}")
        legacy_ml = importlib.import_module(f"ml_classification.ml_utils.{mod}")
        assert legacy_ml is canon_ml

    canon_rb = importlib.import_module("obsidiandroid.evaluation.ml_report_builder")
    legacy_rb = importlib.import_module("ml_classification.reporting.ml_report_builder")
    assert legacy_rb is canon_rb

    assert (
        importlib.import_module("ml_classification.ml_utils.dataset_splitter")
        is importlib.import_module("obsidiandroid.modeling.dataset_splitter")
    )


def test_vendor_execution_shims_match_canonical_modules() -> None:
    """Pass 64: analysis.execution package shim preserves module identity."""
    import importlib

    for name in (
        "av_parser_executor",
        "vendor_parser_runner",
        "vendor_record_factory",
        "vendor_classification_processor",
    ):
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.execution.{name}")
        legacy_mod = importlib.import_module(f"analysis.execution.{name}")
        assert legacy_mod is canon_mod


def test_governance_facade_matches_pipeline_governance_modules() -> None:
    """Pipeline governance primitives are canonical under obsidiandroid.governance (**Pass 75**)."""
    import importlib

    import obsidiandroid.governance as governance_facade

    governance_pairs = (
        ("exceptions", "obsidiandroid.governance.exceptions"),
        ("integrity", "obsidiandroid.governance.integrity"),
        ("policy", "obsidiandroid.governance.policy"),
        ("readiness", "obsidiandroid.governance.readiness"),
    )
    for attr, canon_name in governance_pairs:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(governance_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.governance.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.pipeline.governance.{attr}")
        assert legacy_mod is canon_mod


def test_observability_package_reexports_logging() -> None:
    """``obsidiandroid.observability`` re-exports ``get_logger`` / ``log_event``."""
    import obsidiandroid.observability as obs
    import obsidiandroid.observability.logging as olog

    assert obs.get_logger is olog.get_logger
    assert obs.log_event is olog.log_event


def test_thin_compat_shim_trees_follow_policy() -> None:
    """Legacy shim dirs stay star-import / bootstrap only (see check_import_surface)."""
    from pathlib import Path

    from scripts.dev.import_surface_policy import collect_thin_compat_shim_violations

    repo_root = Path(__file__).resolve().parents[1]
    errs = collect_thin_compat_shim_violations(repo_root)
    assert errs == [], "thin compat shim violations:\n" + "\n".join(errs)


def test_python_sources_have_no_utf8_bom_prefix() -> None:
    """BOM-prefixed ``*.py`` files break ast.parse and CI shim checks (see check_import_surface)."""
    from pathlib import Path

    from scripts.dev.import_surface_policy import collect_utf8_bom_python_sources

    repo_root = Path(__file__).resolve().parents[1]
    bad = collect_utf8_bom_python_sources(repo_root)
    assert not bad, "UTF-8 BOM at start of:\n" + "\n".join(bad)


def test_diagnostics_facade_modules_match_analysis_diagnostics() -> None:
    """Pass 65: ``obsidiandroid.diagnostics`` is canonical; legacy ``analysis.diagnostics`` matches identity."""
    import analysis.diagnostics.ablation_cohort_diagnostics as acd_a
    import analysis.diagnostics.alignment_gap_diagnostics as agd_a
    import analysis.diagnostics.cohort_foundation_export as cfe_a
    import analysis.diagnostics.cohort_sample_id_audit as csia_a
    import analysis.diagnostics.cohort_vocabulary as cv_a
    import analysis.diagnostics.feature_builder_drop_trace as fbdt_a
    import analysis.diagnostics.feature_build_coverage_export as fbce_a
    import analysis.diagnostics.feature_column_survival_export as fcse_a
    import analysis.diagnostics.feature_lineage_report as flr_a
    import analysis.diagnostics.feature_matrix_gap_lineage as fmgl_a
    import analysis.diagnostics.fused_permission_matrix_audit as fpma_a
    import analysis.diagnostics.output_artifact_policy as oap_a
    import analysis.diagnostics.output_inventory as oi_a
    import analysis.diagnostics.permission_training_survival_audit as ptsa_a

    import obsidiandroid.diagnostics as facade

    assert facade.ablation_cohort_diagnostics is acd_a
    assert facade.alignment_gap_diagnostics is agd_a
    assert facade.cohort_foundation_export is cfe_a
    assert facade.cohort_sample_id_audit is csia_a
    assert facade.cohort_vocabulary is cv_a
    assert facade.feature_builder_drop_trace is fbdt_a
    assert facade.feature_build_coverage_export is fbce_a
    assert facade.feature_column_survival_export is fcse_a
    assert facade.feature_lineage_report is flr_a
    assert facade.feature_matrix_gap_lineage is fmgl_a
    assert facade.fused_permission_matrix_audit is fpma_a
    assert facade.output_artifact_policy is oap_a
    assert facade.output_inventory is oi_a
    assert facade.permission_training_survival_audit is ptsa_a

    import analysis.diagnostics.hostile_audit as hostile_canon_pkg
    import analysis.diagnostics.research_validity as rv_canon_pkg

    assert facade.hostile_audit is hostile_canon_pkg
    assert facade.research_validity is rv_canon_pkg
    import obsidiandroid.diagnostics.hostile_audit as hostile_alias_pkg
    import obsidiandroid.diagnostics.research_validity as rv_alias_pkg

    assert hostile_alias_pkg is hostile_canon_pkg
    assert rv_alias_pkg is rv_canon_pkg

    import analysis.diagnostics.hostile_audit.bundle as ha_bundle_a
    import analysis.diagnostics.research_validity.bundle as rv_bundle_a
    import obsidiandroid.diagnostics.hostile_audit.bundle as ha_bundle_f
    import obsidiandroid.diagnostics.research_validity.bundle as rv_bundle_f

    assert ha_bundle_f is ha_bundle_a
    assert rv_bundle_f is rv_bundle_a


def test_database_facade_matches_database_modules() -> None:
    """``obsidiandroid.database`` exposes the same modules as ``database.*`` (Passes 38 + 43)."""
    import importlib

    from scripts.dev.import_surface_policy import (
        DATABASE_FACADE_MODULE_PAIRS,
        DATABASE_LEGACY_SHIM_PAIRS,
    )

    import obsidiandroid.database as facade

    for attr, canon_name in DATABASE_FACADE_MODULE_PAIRS:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.database.{attr}")
        assert alias_mod is canon_mod
    for _attr, _legacy in DATABASE_LEGACY_SHIM_PAIRS:
        assert importlib.import_module(_legacy) is importlib.import_module(
            f"obsidiandroid.database.{_attr}"
        )


def test_vendors_and_evaluation_public_entrypoints_exist() -> None:
    import importlib

    import obsidiandroid.evaluation as eval_pkg
    import obsidiandroid.vendors as vendors_pkg

    vcp = importlib.import_module("obsidiandroid.evaluation.vendor_classification_parser")
    generic = importlib.import_module("obsidiandroid.vendors.parsing.generic_label_parser")

    assert eval_pkg.parse_vendor_classifications is vcp.parse_vendor_classifications
    assert vendors_pkg.parse_generic_classification is generic.parse_generic_classification

    # Evaluation return contract: named result object that still supports tuple unpacking.
    assert eval_pkg.VendorClassificationParseResult is vcp.VendorClassificationParseResult


def test_common_repo_paths_ensure_is_idempotent() -> None:
    """Repeated calls must not duplicate the checkout ``src`` entry."""
    import sys
    from pathlib import Path

    from obsidiandroid.common import repo_paths

    here = Path(repo_paths.__file__).resolve()
    if len(here.parents) < 3 or here.parents[2].name != "src":
        pytest.skip("repo_paths not loaded from a checkout tree under src/")
    src = str(here.parents[2])
    repo_paths.ensure_repo_src_on_sys_path()
    repo_paths.ensure_repo_src_on_sys_path()
    assert sys.path.count(src) == 1
