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

    from obsidiandroid.features.features_facade_manifest import FEATURES_FACADE_ALIAS_TARGETS
    from obsidiandroid.modeling.modeling_facade_manifest import (
        MODELING_FACADE_EAGER_SUBMODULE_NAMES,
        MODELING_FACADE_LEGACY_VIA_ML_CLASSIFICATION_TRAINING,
    )
    from obsidiandroid.modeling.ml_classification_shim_facades import (
        ML_CLASSIFICATION_BUILDER_SUBMODULES,
        ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES,
        ML_CLASSIFICATION_INFERENCE_SUBMODULES,
        ML_CLASSIFICATION_LABELING_SUBMODULES,
        ML_CLASSIFICATION_TRAINING_ML_TRAINERS_SUBMODULES,
        ML_CLASSIFICATION_TRAINING_PHYSICAL_SUBMODULES,
    )

    import obsidiandroid.features as features_facade
    import obsidiandroid.labeling as labeling_facade
    import obsidiandroid.modeling as modeling_facade

    for attr in MODELING_FACADE_EAGER_SUBMODULE_NAMES:
        canon_name = f"obsidiandroid.modeling.{attr}"
        canon_mod = importlib.import_module(canon_name)
        assert getattr(modeling_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.modeling.{attr}")
        assert alias_mod is canon_mod
        if attr in MODELING_FACADE_LEGACY_VIA_ML_CLASSIFICATION_TRAINING:
            legacy_mod = importlib.import_module(f"ml_classification.training.{attr}")
        else:
            legacy_mod = importlib.import_module(f"ml_classification.ml_utils.{attr}")
        assert legacy_mod is canon_mod
    feature_alignment_canon = importlib.import_module("obsidiandroid.modeling.feature_alignment_utils")
    feature_alignment_legacy = importlib.import_module("ml_classification.ml_utils.feature_alignment_utils")
    assert feature_alignment_legacy is feature_alignment_canon

    for mod in sorted(ML_CLASSIFICATION_TRAINING_PHYSICAL_SUBMODULES):
        canon_tm = importlib.import_module(f"obsidiandroid.modeling.{mod}")
        legacy_tm = importlib.import_module(f"ml_classification.training.{mod}")
        assert legacy_tm is canon_tm
    for mod in sorted(ML_CLASSIFICATION_TRAINING_ML_TRAINERS_SUBMODULES):
        canon_tr = importlib.import_module(f"obsidiandroid.modeling.ml_trainers.{mod}")
        legacy_tr = importlib.import_module(f"ml_classification.training.ml_trainers.{mod}")
        assert legacy_tr is canon_tr

    for attr, canon_name in FEATURES_FACADE_ALIAS_TARGETS:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(features_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.features.{attr}")
        assert alias_mod is canon_mod
        if attr == "feature_schema_audit":
            legacy_mod = importlib.import_module("ml_classification.training.feature_schema_audit")
        else:
            legacy_mod = importlib.import_module(f"ml_classification.vectorization.{attr}")
        assert legacy_mod is canon_mod

    for attr in sorted(ML_CLASSIFICATION_LABELING_SUBMODULES):
        canon_name = f"obsidiandroid.labeling.{attr}"
        canon_mod = importlib.import_module(canon_name)
        assert getattr(labeling_facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.labeling.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"ml_classification.labeling.{attr}")
        assert legacy_mod is canon_mod

    cb_facade = importlib.import_module("obsidiandroid.classification_builder")
    for name in sorted(ML_CLASSIFICATION_BUILDER_SUBMODULES):
        canon_cb = importlib.import_module(f"obsidiandroid.classification_builder.{name}")
        assert getattr(cb_facade, name) is canon_cb
        assert importlib.import_module(f"ml_classification.builder.{name}") is canon_cb

    inf_facade = importlib.import_module("obsidiandroid.inference")
    for name in sorted(ML_CLASSIFICATION_INFERENCE_SUBMODULES):
        canon_inf = importlib.import_module(f"obsidiandroid.inference.{name}")
        assert getattr(inf_facade, name) is canon_inf
        assert importlib.import_module(f"ml_classification.inference.{name}") is canon_inf

    ew_facade = importlib.import_module("obsidiandroid.engine_weights")
    for name in sorted(ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES):
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

    from obsidiandroid.modeling.ml_classification_shim_facades import (
        ML_CLASSIFICATION_BUILDER_SUBMODULES,
        ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES,
        ML_CLASSIFICATION_INFERENCE_SUBMODULES,
        ML_CLASSIFICATION_LABELING_SUBMODULES,
        ML_CLASSIFICATION_REPORTING_SUBMODULES,
        ML_CLASSIFICATION_TRAINING_ML_TRAINERS_SUBMODULES,
        ML_CLASSIFICATION_TRAINING_SUBMODULES,
        ML_CLASSIFICATION_VECTORIZATION_SUBMODULES,
    )

    slices: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("ml_classification.builder", tuple(sorted(ML_CLASSIFICATION_BUILDER_SUBMODULES))),
        ("ml_classification.inference", tuple(sorted(ML_CLASSIFICATION_INFERENCE_SUBMODULES))),
        (
            "ml_classification.engine_weights",
            tuple(sorted(ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES)),
        ),
        ("ml_classification.labeling", tuple(sorted(ML_CLASSIFICATION_LABELING_SUBMODULES))),
        ("ml_classification.reporting", tuple(sorted(ML_CLASSIFICATION_REPORTING_SUBMODULES))),
        (
            "ml_classification.vectorization",
            tuple(sorted(ML_CLASSIFICATION_VECTORIZATION_SUBMODULES)),
        ),
        ("ml_classification.training", tuple(sorted(ML_CLASSIFICATION_TRAINING_SUBMODULES))),
        (
            "ml_classification.training.ml_trainers",
            tuple(sorted(ML_CLASSIFICATION_TRAINING_ML_TRAINERS_SUBMODULES)),
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

    from obsidiandroid.feature_engineering.feature_engineering_import_surface import (
        FEATURE_ENGINEERING_LEGACY_SHIM_MODULE_STEMS,
    )

    for attr in FEATURE_ENGINEERING_LEGACY_SHIM_MODULE_STEMS:
        canon_name = f"obsidiandroid.feature_engineering.{attr}"
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.feature_engineering.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.feature_engineering.{attr}")
        assert legacy_mod is canon_mod


def test_orchestration_submodules_match_analysis_shims() -> None:
    """Pass 80: orchestration helpers under ``obsidiandroid.orchestration``; legacy paths match."""
    import importlib

    orch = importlib.import_module("obsidiandroid.orchestration")
    for attr in orch.__all__:
        canon_name = f"obsidiandroid.orchestration.{attr}"
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.orchestration.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.orchestration.{attr}")
        assert legacy_mod is canon_mod


def test_matrix_submodules_match_analysis_shims() -> None:
    """Pass 80: AV matrix helpers under ``obsidiandroid.matrix``; legacy paths match."""
    import importlib

    matrix_pkg = importlib.import_module("obsidiandroid.matrix")
    for attr in matrix_pkg.__all__:
        canon_name = f"obsidiandroid.matrix.{attr}"
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.matrix.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.matrix.{attr}")
        assert legacy_mod is canon_mod


def test_risk_band_submodules_match_analysis_shims() -> None:
    """Pass 81: risk band helpers under ``obsidiandroid.risk_band``; legacy paths match."""
    import importlib

    rb = importlib.import_module("obsidiandroid.risk_band")
    for attr in rb.__all__:
        canon_name = f"obsidiandroid.risk_band.{attr}"
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.risk_band.{attr}")
        assert alias_mod is canon_mod
        legacy_mod = importlib.import_module(f"analysis.risk_band.{attr}")
        assert legacy_mod is canon_mod


def test_pipeline_permission_trends_facade_matches_permission_trends_modules() -> None:
    """Pipeline permission-trends facade aliases canonical modules (**Pass 74**); legacy paths match."""
    import importlib

    from obsidiandroid.pipeline.permission_trends.permission_trends_submodule_manifest import (
        PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES,
    )

    import obsidiandroid.pipeline.permission_trends as permission_trends_facade

    for attr in PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES:
        canon_name = f"obsidiandroid.pipeline.permission_trends.{attr}"
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

    from obsidiandroid.vendors.parsing.vendor_parser_submodule_manifest import (
        VENDOR_PARSER_SUBMODULE_NAMES,
    )

    import obsidiandroid.vendors.parsing as parsing_pkg

    for name in VENDOR_PARSER_SUBMODULE_NAMES:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{name}")
        assert getattr(parsing_pkg, name) is canon_mod
        legacy_mod = importlib.import_module(f"analysis.vendor_processing.{name}")
        assert legacy_mod is canon_mod


def test_evaluation_leaf_shims_match_canonical_modules() -> None:
    """Passes 61–63: analysis.evaluation package shim preserves module identity."""
    import importlib

    from obsidiandroid.evaluation.analysis_evaluation_shim import (
        LEGACY_EXPORT_NAMES as ANALYSIS_EVALUATION_LEGACY_EXPORT_NAMES,
    )

    for name in ANALYSIS_EVALUATION_LEGACY_EXPORT_NAMES:
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

    from obsidiandroid.vendors.execution.analysis_execution_shim import (
        LEGACY_EXPORT_NAMES as ANALYSIS_EXECUTION_LEGACY_EXPORT_NAMES,
    )

    for name in ANALYSIS_EXECUTION_LEGACY_EXPORT_NAMES:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.execution.{name}")
        legacy_mod = importlib.import_module(f"analysis.execution.{name}")
        assert legacy_mod is canon_mod


def test_governance_facade_matches_pipeline_governance_modules() -> None:
    """Pipeline governance primitives are canonical under obsidiandroid.governance (**Pass 75**)."""
    import importlib

    from obsidiandroid.governance.analysis_pipeline_governance_shim import (
        ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES,
    )

    import obsidiandroid.governance as governance_facade

    for attr in sorted(ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES):
        canon_name = f"obsidiandroid.governance.{attr}"
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
    import importlib

    # Side effect: registers ``analysis.diagnostics.*`` aliases to canonical modules.
    import analysis.diagnostics  # noqa: F401
    from obsidiandroid.diagnostics.analysis_diagnostics_shim import (
        DIAGNOSTICS_NESTED_LEGACY_PACKAGES,
        DIAGNOSTICS_TOP_LEVEL_MODULE_NAMES,
    )

    import obsidiandroid.diagnostics as facade

    for name in DIAGNOSTICS_TOP_LEVEL_MODULE_NAMES:
        canon = importlib.import_module(f"obsidiandroid.diagnostics.{name}")
        legacy = importlib.import_module(f"analysis.diagnostics.{name}")
        assert getattr(facade, name) is canon
        assert legacy is canon

    for pkg in DIAGNOSTICS_NESTED_LEGACY_PACKAGES:
        canon_pkg = importlib.import_module(f"obsidiandroid.diagnostics.{pkg}")
        legacy_pkg = importlib.import_module(f"analysis.diagnostics.{pkg}")
        assert getattr(facade, pkg) is canon_pkg
        assert legacy_pkg is canon_pkg
        bundle_legacy = importlib.import_module(f"analysis.diagnostics.{pkg}.bundle")
        bundle_canon = importlib.import_module(f"obsidiandroid.diagnostics.{pkg}.bundle")
        assert bundle_canon is bundle_legacy
    """``obsidiandroid.database`` exposes the same modules as ``database.*`` (Passes 38 + 43)."""
    import importlib

    from obsidiandroid.database.facade_manifest import FACADE_MODULE_PAIRS, LEGACY_SHIM_PAIRS

    import obsidiandroid.database as facade

    for attr, canon_name in FACADE_MODULE_PAIRS:
        canon_mod = importlib.import_module(canon_name)
        assert getattr(facade, attr) is canon_mod
        alias_mod = importlib.import_module(f"obsidiandroid.database.{attr}")
        assert alias_mod is canon_mod
    for _attr, _legacy in LEGACY_SHIM_PAIRS:
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
