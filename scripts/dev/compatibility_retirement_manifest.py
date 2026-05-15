"""Single source of truth for canonical-relocation completion and legacy-compat surfaces.

This module is intentionally data-only. It exists to keep the final migration
phase honest and maintainable:

- canonical relocation complete domains live in one place
- legacy compatibility roots / shim trees are declared once
- test allowlists for shim-parity coverage stay explicit

Consumers include import-surface guardrails, docs, and future compatibility
retirement tooling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Core domains whose implementation is now treated as canonical under
# ``src/obsidiandroid``. Remaining work in these areas is shim retirement,
# boundary cleanup, or docs/tests rather than physical code relocation.
CANONICAL_RELOCATION_COMPLETE_DOMAINS = (
    "pipeline",
    "common",
    "governance",
    "observability",
    "diagnostics",
    "database",
    "modeling",
    "evaluation",
    "reporting",
    "vendors",
    "features",
    "feature_engineering",
    "labeling",
    "classification_builder",
    "inference",
    "engine_weights",
    "risk_band",
    "matrix",
    "orchestration",
)

# Legacy roots that canonical code must not import directly.
LEGACY_COMPATIBILITY_IMPORT_ROOTS = (
    "analysis",
    "ml_classification",
)

# Repo-root compatibility trees whose non-``__init__`` leaves must remain thin
# ModuleType identity shims until retirement.
LEGACY_LEAF_SHIM_ROOTS = (
    "analysis",
    "ml_classification",
)

# Repo-root shim namespace that remains intentionally compatibility-only while
# implementations live under ``src/obsidiandroid/database``.
LEGACY_DATABASE_SHIM_ROOT = "database"

# Allowlisted files that intentionally exercise legacy compatibility behavior.
CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST = (
    Path("scripts/dev/check_import_surface.py"),
)

NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST = (
    Path("tests/test_legacy_shim_parity.py"),
)

ANALYSIS_PIPELINE_PATCH_SENSITIVE_SHIMS = (
    "analysis/pipeline/main_facade.py",
    "analysis/pipeline/runner.py",
)

ANALYSIS_PIPELINE_PACKAGE_SPECIAL_CASES = (
    "analysis/pipeline/__init__.py",
    "analysis/pipeline/governance/__init__.py",
    "analysis/pipeline/permission_trends/__init__.py",
)

ANALYSIS_PIPELINE_PLAIN_IDENTITY_SHIMS = (
    "analysis/pipeline/artifacts/__init__.py",
    "analysis/pipeline/artifacts/paths.py",
    "analysis/pipeline/artifacts/registry.py",
    "analysis/pipeline/attach_engine_metadata.py",
    "analysis/pipeline/av_engine_pipeline.py",
    "analysis/pipeline/contract_filters.py",
    "analysis/pipeline/engine_normalization.py",
    "analysis/pipeline/engine_pipeline_utils.py",
    "analysis/pipeline/governance/exceptions.py",
    "analysis/pipeline/governance/integrity.py",
    "analysis/pipeline/governance/policy.py",
    "analysis/pipeline/governance/readiness.py",
    "analysis/pipeline/manifest/__init__.py",
    "analysis/pipeline/manifest/builder.py",
    "analysis/pipeline/manifest/hashing.py",
    "analysis/pipeline/manifest/paper_compliance_checks.py",
    "analysis/pipeline/manifest/paper_figure_renderers.py",
    "analysis/pipeline/manifest/runtime_support.py",
    "analysis/pipeline/manifest/schema.py",
    "analysis/pipeline/manifest/writer.py",
    "analysis/pipeline/permission_trends/bundle_manifest.py",
    "analysis/pipeline/permission_trends/constants.py",
    "analysis/pipeline/permission_trends/publish_paths.py",
    "analysis/pipeline/permission_trends/reporting_support.py",
    "analysis/pipeline/permission_trends/sample_permission_data.py",
    "analysis/pipeline/permission_trends/stats_core.py",
    "analysis/pipeline/permission_trends_selection.py",
    "analysis/pipeline/run_bounds.py",
    "analysis/pipeline/runtime_policy.py",
    "analysis/pipeline/sample_exports.py",
    "analysis/pipeline/sample_preparation.py",
    "analysis/pipeline/score_av_engines.py",
    "analysis/pipeline/stage_ablation.py",
    "analysis/pipeline/stage_av_vendor.py",
    "analysis/pipeline/stage_feature_enrichment.py",
    "analysis/pipeline/stage_manifest.py",
    "analysis/pipeline/stage_modeling.py",
    "analysis/pipeline/stage_permission_trends_report.py",
    "analysis/pipeline/stage_results_warehouse.py",
    "analysis/pipeline/stage_samples.py",
    "analysis/pipeline/vendor_metadata_pipeline.py",
)

ML_CLASSIFICATION_TRAINING_PACKAGE_SPECIAL_CASES = (
    "ml_classification/training/__init__.py",
    "ml_classification/training/ml_trainers/__init__.py",
)

ML_CLASSIFICATION_BUILDER_PACKAGE_SPECIAL_CASES = (
    "ml_classification/builder/__init__.py",
)

ML_CLASSIFICATION_BUILDER_PLAIN_IDENTITY_SHIMS = (
    "ml_classification/builder/classification_constants.py",
    "ml_classification/builder/classification_row_builder.py",
    "ml_classification/builder/prediction_utils.py",
    "ml_classification/builder/record_enrichment.py",
    "ml_classification/builder/sample_classification_builder.py",
    "ml_classification/builder/vendor_record_selector.py",
)

ML_CLASSIFICATION_ENGINE_WEIGHTS_PACKAGE_SPECIAL_CASES = (
    "ml_classification/engine_weights/__init__.py",
)

ML_CLASSIFICATION_ENGINE_WEIGHTS_PLAIN_IDENTITY_SHIMS = (
    "ml_classification/engine_weights/assign_detection_tiers.py",
    "ml_classification/engine_weights/build_classification_weights.py",
    "ml_classification/engine_weights/classification_weight_inspector.py",
    "ml_classification/engine_weights/classification_weight_utils.py",
    "ml_classification/engine_weights/compute_reliability_score.py",
    "ml_classification/engine_weights/engine_weights_utils.py",
)

ML_CLASSIFICATION_INFERENCE_PACKAGE_SPECIAL_CASES = (
    "ml_classification/inference/__init__.py",
)

ML_CLASSIFICATION_INFERENCE_PLAIN_IDENTITY_SHIMS = (
    "ml_classification/inference/label_consensus_engine.py",
    "ml_classification/inference/malware_type_engine.py",
    "ml_classification/inference/signal_health_checker.py",
    "ml_classification/inference/threat_class_engine.py",
)

ML_CLASSIFICATION_LABELING_PACKAGE_SPECIAL_CASES = (
    "ml_classification/labeling/__init__.py",
)

ML_CLASSIFICATION_LABELING_PLAIN_IDENTITY_SHIMS = (
    "ml_classification/labeling/classification_label_resolver.py",
    "ml_classification/labeling/label_builder_wrapper.py",
    "ml_classification/labeling/label_field_normalizer.py",
    "ml_classification/labeling/label_format_generator.py",
    "ml_classification/labeling/label_input_validator.py",
    "ml_classification/labeling/label_postprocessor.py",
)

ML_CLASSIFICATION_ML_UTILS_PACKAGE_SPECIAL_CASES = (
    "ml_classification/ml_utils/__init__.py",
)

ML_CLASSIFICATION_ML_UTILS_PLAIN_IDENTITY_SHIMS = (
    "ml_classification/ml_utils/accuracy_band_utils.py",
    "ml_classification/ml_utils/dataset_splitter.py",
    "ml_classification/ml_utils/distribution_reporter.py",
    "ml_classification/ml_utils/feature_alignment_utils.py",
    "ml_classification/ml_utils/feature_label_alignment_helper.py",
    "ml_classification/ml_utils/ml_comparator_summary.py",
    "ml_classification/ml_utils/ml_eval_engine.py",
    "ml_classification/ml_utils/ml_result_analyzer.py",
    "ml_classification/ml_utils/ml_result_validator.py",
)

ML_CLASSIFICATION_TRAINING_PLAIN_IDENTITY_SHIMS = (
    "ml_classification/training/data_alignment.py",
    "ml_classification/training/feature_schema_audit.py",
    "ml_classification/training/model_evaluation.py",
    "ml_classification/training/model_prediction.py",
    "ml_classification/training/model_trainer_factory.py",
    "ml_classification/training/model_training.py",
    "ml_classification/training/pipeline_core.py",
    "ml_classification/training/pipeline_result_promoter.py",
    "ml_classification/training/prediction_builder.py",
    "ml_classification/training/train_model_executor.py",
    "ml_classification/training/training_helpers.py",
    "ml_classification/training/ml_trainers/balanced_random_forest_trainer.py",
    "ml_classification/training/ml_trainers/logistic_regression_trainer.py",
    "ml_classification/training/ml_trainers/random_forest_trainer.py",
    "ml_classification/training/ml_trainers/svm_trainer.py",
    "ml_classification/training/ml_trainers/xgboost_trainer.py",
)

CANONICAL_FILENAME_HEADER_BAD_ROOTS = (
    *LEGACY_COMPATIBILITY_IMPORT_ROOTS,
    LEGACY_DATABASE_SHIM_ROOT,
)


@dataclass(frozen=True)
class LegacyTreeRetirementEntry:
    """Status snapshot for one legacy compatibility tree."""

    root: str
    file_count: int
    implementation_status: str
    compatibility_role: str
    blockers: tuple[str, ...]
    next_step: str


@dataclass(frozen=True)
class LegacySubtreeRetirementBucket:
    """Retirement status for one legacy subtree or special compatibility surface."""

    tree: str
    canonical_target: str
    bucket: str
    file_count: int
    readiness: str
    rationale: str
    next_step: str
    import_prefixes: tuple[str, ...] = ()


LEGACY_TREE_RETIREMENT_MATRIX = (
    LegacyTreeRetirementEntry(
        root="analysis",
        file_count=75,
        implementation_status="canonical relocation complete; tree is mostly shim-only",
        compatibility_role="legacy import identity and monkeypatch-sensitive pipeline/test seams",
        blockers=(
            "pipeline monkeypatch surfaces still target analysis.pipeline in some parity flows",
            "package-level shim identity is still exercised by explicit parity tests",
            "retirement needs staged caller/test deprecation, not drive-by deletion",
        ),
        next_step="narrow parity-test coverage and define per-subtree deletion criteria",
    ),
    LegacyTreeRetirementEntry(
        root="ml_classification",
        file_count=35,
        implementation_status="canonical relocation complete; tree is shim-only plus lazy facade packages",
        compatibility_role="legacy ML import compatibility for training, labeling, inference, and reporting paths",
        blockers=(
            "lazy __getattr__ package facades remain part of compatibility API",
            "shim parity is still explicitly tested for builder/inference/engine_weights/training",
            "sunset criteria for external callers are not yet documented module-by-module",
        ),
        next_step="publish deprecation buckets for subpackages and trim parity surfaces incrementally",
    ),
    LegacyTreeRetirementEntry(
        root="database",
        file_count=45,
        implementation_status="canonical relocation complete under src/obsidiandroid/database",
        compatibility_role="repo-root import compatibility and python -m database.split_db_health entrypoint",
        blockers=(
            "repo-root database.* remains an intentional compatibility namespace",
            "facade/implementation distinction must stay clear to avoid circular import regressions",
            "split_db_health still needs the repo-root execution surface",
        ),
        next_step="separate module-retirement candidates from entrypoint-compatibility shims",
    ),
)

LEGACY_SUBTREE_RETIREMENT_BUCKETS = (
    LegacySubtreeRetirementBucket(
        tree="analysis/pipeline",
        canonical_target="obsidiandroid.pipeline",
        bucket="monkeypatch-sensitive shim tree",
        file_count=46,
        readiness="deprecate later",
        rationale="imports are shim-only but runner/main_facade remain stable monkeypatch and compatibility surfaces",
        next_step="split patch-target parity from import-identity parity, then define deletion order for non-patch leaves",
        import_prefixes=("analysis.pipeline",),
    ),
    LegacySubtreeRetirementBucket(
        tree="analysis/diagnostics",
        canonical_target="obsidiandroid.diagnostics",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready for later retirement once parity tests narrow",
        rationale="implementation is canonical under obsidiandroid.diagnostics and legacy package is registration-only",
        next_step="reduce explicit analysis.diagnostics parity coverage to bundle-critical checks only",
        import_prefixes=("analysis.diagnostics",),
    ),
    LegacySubtreeRetirementBucket(
        tree="analysis/evaluation",
        canonical_target="obsidiandroid.evaluation",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready for later retirement once parity tests narrow",
        rationale="implementation is canonical under obsidiandroid.evaluation and legacy package is registration-only",
        next_step="keep public entrypoint parity, then remove package-level shim once callers are gone",
        import_prefixes=("analysis.evaluation",),
    ),
    LegacySubtreeRetirementBucket(
        tree="analysis/execution",
        canonical_target="obsidiandroid.vendors.execution",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready for later retirement once parity tests narrow",
        rationale="implementation is canonical under obsidiandroid.vendors.execution and legacy package is registration-only",
        next_step="retain only parity coverage needed for vendor execution import identity",
        import_prefixes=("analysis.execution",),
    ),
    LegacySubtreeRetirementBucket(
        tree="analysis/feature_engineering",
        canonical_target="obsidiandroid.feature_engineering",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready to deprecate now",
        rationale="legacy leaf shims were removed; package import now anchors canonical alias registration only",
        next_step="document any remaining external callers, then deprecate the package shim",
        import_prefixes=("analysis.feature_engineering",),
    ),
    LegacySubtreeRetirementBucket(
        tree="analysis/matrix",
        canonical_target="obsidiandroid.matrix",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready to deprecate now",
        rationale="legacy leaf shims were removed; package import now anchors canonical alias registration only",
        next_step="deprecate the package shim after parity coverage is trimmed",
        import_prefixes=("analysis.matrix",),
    ),
    LegacySubtreeRetirementBucket(
        tree="analysis/orchestration",
        canonical_target="obsidiandroid.orchestration",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready to deprecate now",
        rationale="legacy leaf shims were removed; package import now anchors canonical alias registration only",
        next_step="deprecate once any patch-target uses are confirmed absent",
        import_prefixes=("analysis.orchestration",),
    ),
    LegacySubtreeRetirementBucket(
        tree="analysis/risk_band",
        canonical_target="obsidiandroid.risk_band",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready to deprecate now",
        rationale="legacy leaf shims were removed; package import now anchors canonical alias registration only",
        next_step="retire together with other non-pipeline analysis package shims",
        import_prefixes=("analysis.risk_band",),
    ),
    LegacySubtreeRetirementBucket(
        tree="analysis/vendor_processing",
        canonical_target="obsidiandroid.vendors.parsing",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready for later retirement once vendor parity narrows",
        rationale="vendor parser implementation is canonical under obsidiandroid.vendors.parsing",
        next_step="keep explicit parser parity while public wrapper API settles, then retire package shim",
        import_prefixes=("analysis.vendor_processing",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/builder",
        canonical_target="obsidiandroid.classification_builder",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="deprecate later",
        rationale="legacy leaf shims were removed; package import now registers canonical classification-builder aliases",
        next_step="publish subpackage deprecation notice and reduce parity to a smaller manifest-driven subset",
        import_prefixes=("ml_classification.builder",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/common",
        canonical_target="obsidiandroid.labeling",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready to deprecate now",
        rationale="legacy leaf shim was removed; package import now registers the canonical malware-family constants alias",
        next_step="prefer taxonomy wrapper everywhere and deprecate the package shim",
        import_prefixes=("ml_classification.common",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/engine_weights",
        canonical_target="obsidiandroid.engine_weights",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="deprecate later",
        rationale="legacy leaf shims were removed; package import now registers canonical engine-weight aliases",
        next_step="trim parity to public-weighting entrypoints before subtree retirement",
        import_prefixes=("ml_classification.engine_weights",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/inference",
        canonical_target="obsidiandroid.inference",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="deprecate later",
        rationale="legacy leaf shims were removed; package import now registers canonical inference aliases",
        next_step="define inference public API and deprecate legacy package imports against that contract",
        import_prefixes=("ml_classification.inference",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/labeling",
        canonical_target="obsidiandroid.labeling",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="deprecate later",
        rationale="legacy leaf shims were removed; package import now registers canonical labeling aliases",
        next_step="bucket labeling names into keep/public vs retire/legacy before removal work",
        import_prefixes=("ml_classification.labeling",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/ml_utils",
        canonical_target="obsidiandroid.modeling",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="high-risk; retire last within ml_classification",
        rationale="legacy leaf shims were removed; package import now registers the remaining modeling/evaluation utility aliases",
        next_step="shrink to documented compatibility-only entrypoints, then retire by helper cluster",
        import_prefixes=("ml_classification.ml_utils",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/reporting",
        canonical_target="obsidiandroid.reporting",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready to deprecate now",
        rationale="legacy leaf shims were removed; package import now registers the remaining reporting aliases",
        next_step="deprecate report-builder/compile-results package shim together",
        import_prefixes=("ml_classification.reporting",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/training",
        canonical_target="obsidiandroid.modeling",
        bucket="large lazy facade plus leaf shims",
        file_count=18,
        readiness="high-risk; retire last within ml_classification",
        rationale="training remains the largest compatibility surface and includes patch-sensitive flows",
        next_step="separate trainer parity, pipeline-core parity, and utility parity before retirement",
        import_prefixes=("ml_classification.training",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/training/ml_trainers",
        canonical_target="obsidiandroid.modeling.ml_trainers",
        bucket="trainer shim leaf set",
        file_count=6,
        readiness="deprecate later",
        rationale="canonical trainer implementations exist but training parity still references legacy package paths",
        next_step="retire after parent training package parity narrows",
        import_prefixes=("ml_classification.training.ml_trainers",),
    ),
    LegacySubtreeRetirementBucket(
        tree="ml_classification/vectorization",
        canonical_target="obsidiandroid.features.vectorization",
        bucket="package-only shim namespace",
        file_count=1,
        readiness="ready to deprecate now",
        rationale="legacy leaf shims were removed; package import now registers canonical vectorization aliases directly",
        next_step="deprecate the vectorization package shim as a batch once remaining external callers are audited",
        import_prefixes=("ml_classification.vectorization",),
    ),
    LegacySubtreeRetirementBucket(
        tree="database/__init__.py",
        canonical_target="obsidiandroid.database",
        bucket="repo-root compatibility package",
        file_count=1,
        readiness="keep for now",
        rationale="defines the repo-root compatibility namespace for database.* imports",
        next_step="keep until broader database shim retirement plan is approved",
        import_prefixes=("database",),
    ),
    LegacySubtreeRetirementBucket(
        tree="database/split_db_health.py",
        canonical_target="obsidiandroid.database.split_db_health",
        bucket="entrypoint compatibility shim",
        file_count=1,
        readiness="keep for now",
        rationale="supports python -m database.split_db_health in addition to import compatibility",
        next_step="preserve until CLI/ops entrypoint migration is explicitly approved",
        import_prefixes=("database.split_db_health",),
    ),
    LegacySubtreeRetirementBucket(
        tree="database/*.py (other leaf shims)",
        canonical_target="obsidiandroid.database",
        bucket="leaf identity shims",
        file_count=19,
        readiness="deprecate later",
        rationale="canonical implementation is complete but repo-root database namespace still intentionally exists",
        next_step="separate pure import-compat leaves from any remaining ops-facing surfaces",
        import_prefixes=("database",),
    ),
)

EARLY_DEPRECATION_READY_TREES = tuple(
    entry.tree for entry in LEGACY_SUBTREE_RETIREMENT_BUCKETS if entry.readiness == "ready to deprecate now"
)

__all__ = (
    "CANONICAL_CODE_IMPORT_SCAN_ALLOWLIST",
    "CANONICAL_FILENAME_HEADER_BAD_ROOTS",
    "CANONICAL_RELOCATION_COMPLETE_DOMAINS",
    "ML_CLASSIFICATION_BUILDER_PACKAGE_SPECIAL_CASES",
    "ML_CLASSIFICATION_BUILDER_PLAIN_IDENTITY_SHIMS",
    "ML_CLASSIFICATION_ENGINE_WEIGHTS_PACKAGE_SPECIAL_CASES",
    "ML_CLASSIFICATION_ENGINE_WEIGHTS_PLAIN_IDENTITY_SHIMS",
    "ML_CLASSIFICATION_INFERENCE_PACKAGE_SPECIAL_CASES",
    "ML_CLASSIFICATION_INFERENCE_PLAIN_IDENTITY_SHIMS",
    "ML_CLASSIFICATION_LABELING_PACKAGE_SPECIAL_CASES",
    "ML_CLASSIFICATION_LABELING_PLAIN_IDENTITY_SHIMS",
    "ML_CLASSIFICATION_ML_UTILS_PACKAGE_SPECIAL_CASES",
    "ML_CLASSIFICATION_ML_UTILS_PLAIN_IDENTITY_SHIMS",
    "ANALYSIS_PIPELINE_PACKAGE_SPECIAL_CASES",
    "ANALYSIS_PIPELINE_PATCH_SENSITIVE_SHIMS",
    "ANALYSIS_PIPELINE_PLAIN_IDENTITY_SHIMS",
    "ML_CLASSIFICATION_TRAINING_PACKAGE_SPECIAL_CASES",
    "ML_CLASSIFICATION_TRAINING_PLAIN_IDENTITY_SHIMS",
    "EARLY_DEPRECATION_READY_TREES",
    "LEGACY_SUBTREE_RETIREMENT_BUCKETS",
    "LEGACY_TREE_RETIREMENT_MATRIX",
    "LegacyTreeRetirementEntry",
    "LegacySubtreeRetirementBucket",
    "LEGACY_COMPATIBILITY_IMPORT_ROOTS",
    "LEGACY_DATABASE_SHIM_ROOT",
    "LEGACY_LEAF_SHIM_ROOTS",
    "NONPARITY_TEST_LEGACY_IMPORT_ALLOWLIST",
)
