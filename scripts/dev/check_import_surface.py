#!/usr/bin/env python3
"""Smoke-check that ``obsidiandroid`` and CLI/pipeline entry modules import correctly.

Static policy scans (legacy-root imports in ``src/``/``scripts``, tests, BOM, and retired
compatibility-path checks) live in
:mod:`scripts.dev.import_surface_policy`.

Fails if any tracked-style ``*.py`` tree under the repo starts with a **UTF-8 BOM**
(``\ufeff``), which breaks :func:`ast.parse` and confuses diffs—see
:func:`scripts.dev.import_surface_policy.collect_utf8_bom_python_sources`.

Static AST/file-system ratchets (legacy-root imports in ``src/`` / ``scripts`` / tests,
``# Filename:`` headers under ``src/`` (first segment must not be ``analysis``,
``ml_classification``, or repo-root ``database``)) live in
:mod:`scripts.dev.import_surface_policy`. Database façade tuples live in
:mod:`obsidiandroid.database.facade_manifest` (imported by this script after
``src/`` is prepended to ``sys.path``).

Run from the repository root after ``pip install -e .`` or with ``PYTHONPATH`` including
``src/`` (see docs/AGENTS.md and docs/STRUCTURE_MIGRATION_PLAN.md). Exits nonzero on failure.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.database.facade_manifest import FACADE_MODULE_PAIRS
from obsidiandroid.features.features_facade_manifest import FEATURES_FACADE_ALIAS_TARGETS
from obsidiandroid.modeling.modeling_facade_manifest import (
    MODELING_FACADE_EAGER_SUBMODULE_NAMES,
    MODELING_FACADE_LEGACY_VIA_ML_CLASSIFICATION_TRAINING,
)
from obsidiandroid.modeling.legacy_ml_classification_manifest import (
    ML_CLASSIFICATION_BUILDER_SUBMODULES,
    ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES,
    ML_CLASSIFICATION_INFERENCE_SUBMODULES,
    ML_CLASSIFICATION_LABELING_SUBMODULES,
)
from obsidiandroid.pipeline.permission_trends.permission_trends_submodule_manifest import (
    PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES,
)
from obsidiandroid.vendors.parsing.vendor_parser_submodule_manifest import (
    VENDOR_PARSER_SUBMODULE_NAMES,
)

from scripts.dev.import_surface_policy import (
    THIN_COMPAT_SHIM_POLICIES,
    collect_canonical_code_legacy_imports,
    collect_ml_training_plain_shim_violations,
    collect_nonparity_test_legacy_imports,
    collect_ready_now_shim_helper_violations,
    collect_retired_compatibility_file_violations,
    collect_retired_compatibility_tree_violations,
    collect_stale_canonical_filename_headers,
    collect_thin_compat_shim_violations,
    collect_utf8_bom_python_sources,
)

DIAGNOSTICS_TOP_LEVEL_MODULE_NAMES: tuple[str, ...] = (
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
DIAGNOSTICS_NESTED_PACKAGES: tuple[str, ...] = ("research_validity", "hostile_audit")


def _module_path(mod: ModuleType) -> str:
    path = getattr(mod, "__file__", None)
    return str(path) if path else "(namespace package)"


def _legacy_ml_pkg_getattr_errors(pkg_qual: str, submodule_names: tuple[str, ...]) -> list[str]:
    """Return human-readable failures when ``pkg.<name>`` disagrees with ``import pkg.name``."""

    errors: list[str] = []
    pkg_mod = importlib.import_module(pkg_qual)
    for name in submodule_names:
        sub_mod = importlib.import_module(f"{pkg_qual}.{name}")
        if getattr(pkg_mod, name) is not sub_mod:
            errors.append(f"{pkg_qual}.{name} getattr mismatch vs explicit submodule import")
    return errors


def _check_import_smoke() -> bool:
    """Import top-level canonical surfaces used by contributors and operators."""
    try:
        pkg = importlib.import_module("obsidiandroid")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid: {exc}", file=sys.stderr)
        return False
    print(f"OK   obsidiandroid -> {_module_path(pkg)}")

    for name in (
        "obsidiandroid.cli.startup_menu",
        "obsidiandroid.cli.pipeline_entry",
        "obsidiandroid.pipeline",
        "obsidiandroid.modeling",
        "obsidiandroid.features",
        "obsidiandroid.labeling",
        "obsidiandroid.labeling.taxonomy",
        "obsidiandroid.vendors",
        "obsidiandroid.vendors.parsing",
        "obsidiandroid.vendors.contracts",
        "obsidiandroid.evaluation",
    ):
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            print(f"FAIL: import {name}: {exc}", file=sys.stderr)
            return False
        print(f"OK   {name} -> {_module_path(mod)}")

    return True


def _check_static_policy_scans() -> bool:
    """Run file-system/AST guardrails that do not need imported module state."""
    legacy_imports = collect_canonical_code_legacy_imports(_REPO_ROOT)
    if legacy_imports:
        print(
            "FAIL: canonical src/scripts code imports legacy compatibility roots "
            "(use obsidiandroid.*; forbidden roots: analysis, ml_classification, main):",
            file=sys.stderr,
        )
        for item in legacy_imports:
            print(f"  {item}", file=sys.stderr)
        return False
    print("OK   canonical src/scripts imports avoid legacy compatibility roots")

    test_legacy_imports = collect_nonparity_test_legacy_imports(_REPO_ROOT)
    if test_legacy_imports:
        print(
            "FAIL: non-parity tests import legacy compatibility roots "
            "(use obsidiandroid.*; analysis and ml_classification are retired import roots):",
            file=sys.stderr,
        )
        for item in test_legacy_imports:
            print(f"  {item}", file=sys.stderr)
        return False
    print("OK   non-parity tests avoid legacy compatibility roots")

    stale_headers = collect_stale_canonical_filename_headers(_REPO_ROOT)
    if stale_headers:
        print(
            "FAIL: canonical src files have disallowed # Filename: headers:",
            file=sys.stderr,
        )
        for item in stale_headers:
            print(f"  {item}", file=sys.stderr)
        return False
    print("OK   canonical src filename headers avoid disallowed roots")

    bom_paths = collect_utf8_bom_python_sources(_REPO_ROOT)
    if bom_paths:
        print(
            "FAIL: UTF-8 BOM (U+FEFF) at start of Python source — breaks ast.parse / tooling:",
            file=sys.stderr,
        )
        for item in bom_paths:
            print(f"  {item}", file=sys.stderr)
        print(
            "  Fix: save as UTF-8 without BOM, or re-save via utf-8-sig read + utf-8 write.",
            file=sys.stderr,
        )
        return False
    print("OK   Python sources: no UTF-8 BOM prefix (repo scan)")

    thin_errors = collect_thin_compat_shim_violations(_REPO_ROOT)
    if thin_errors:
        for msg in thin_errors:
            print(f"FAIL: thin compat shim policy: {msg}", file=sys.stderr)
        return False
    if THIN_COMPAT_SHIM_POLICIES:
        for policy in THIN_COMPAT_SHIM_POLICIES:
            print(f"OK   {policy.label}")
    else:
        print("OK   no repo-root thin-compat shim policies (utils/ removed)")

    ready_now_helper_errors = collect_ready_now_shim_helper_violations(_REPO_ROOT)
    if ready_now_helper_errors:
        print(
            "FAIL: ready-now legacy shim batches must use shared helper + opt-in warning path:",
            file=sys.stderr,
        )
        for item in ready_now_helper_errors:
            print(f"  {item}", file=sys.stderr)
        return False
    print("OK   ready-now legacy shim batches use shared helper/warning pattern")

    retired_file_errors = collect_retired_compatibility_file_violations(_REPO_ROOT)
    if retired_file_errors:
        print(
            "FAIL: retired root-level compatibility file reappeared on disk:",
            file=sys.stderr,
        )
        for item in retired_file_errors:
            print(f"  {item}", file=sys.stderr)
        return False
    print("OK   retired root-level compatibility files stay absent")

    retired_tree_errors = collect_retired_compatibility_tree_violations(_REPO_ROOT)
    if retired_tree_errors:
        print(
            "FAIL: retired compatibility tree reappeared on disk:",
            file=sys.stderr,
        )
        for item in retired_tree_errors:
            print(f"  {item}", file=sys.stderr)
        return False
    print("OK   retired compatibility trees stay absent")

    ml_training_plain_errors = collect_ml_training_plain_shim_violations(_REPO_ROOT)
    if ml_training_plain_errors:
        print(
            "FAIL: ordinary ml_classification/training shims must use shared helper pattern:",
            file=sys.stderr,
        )
        for item in ml_training_plain_errors:
            print(f"  {item}", file=sys.stderr)
        return False
    print("OK   ml_classification/training shim tree retired or still follows shared helper pattern")

    return True


def _check_common_reporting_surfaces() -> bool:
    """Smoke-import canonical common / CLI / governance / reporting modules (no legacy ``utils``)."""
    common_checks = (
        "obsidiandroid.common.hash_utils",
        "obsidiandroid.common.ml_console",
        "obsidiandroid.common.display_distribution",
        "obsidiandroid.common.output_paths",
        "obsidiandroid.common.output_cleanup_clutter",
        "obsidiandroid.common.av_detection_tiers",
        "obsidiandroid.common.sample_metadata_preprocessor",
        "obsidiandroid.governance.compliance",
        "obsidiandroid.reporting.latex_tables",
        "obsidiandroid.reporting.family_distribution_report",
        "obsidiandroid.cli.profile_manager",
        "obsidiandroid.governance.cohort_readiness_report",
        "obsidiandroid.governance.cohort_reproducibility",
        "obsidiandroid.governance.run_manifest",
        "obsidiandroid.governance.artifacts",
        "obsidiandroid.common.export_naming",
        "obsidiandroid.common.export_vendor_raw",
        "obsidiandroid.common.export_workbook",
        "obsidiandroid.reporting.confusion_matrix_exporter",
        "obsidiandroid.reporting.export_manager",
        "obsidiandroid.modeling.model_exporter",
        "obsidiandroid.common.output_hygiene",
        "obsidiandroid.cli.ui.display",
    )
    for name in common_checks:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            print(f"FAIL: import {name}: {exc}", file=sys.stderr)
            return False
        print(f"OK   {name} -> {_module_path(mod)}")
    return True


def _check_observability_diagnostics_database_shims() -> bool:
    """Verify observability, diagnostics, and database package compatibility surfaces."""
    try:
        obs_pkg = importlib.import_module("obsidiandroid.observability")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.observability: {exc}", file=sys.stderr)
        return False
    print(f"OK   obsidiandroid.observability -> {_module_path(obs_pkg)}")

    try:
        canon_olog = importlib.import_module("obsidiandroid.observability.logging")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.observability.logging: {exc}", file=sys.stderr)
        return False
    print(f"OK   obsidiandroid.observability.logging -> {_module_path(canon_olog)}")

    if obs_pkg.get_logger is not canon_olog.get_logger:
        print("FAIL: obsidiandroid.observability.get_logger is not logging.get_logger", file=sys.stderr)
        return False
    if obs_pkg.log_event is not canon_olog.log_event:
        print("FAIL: obsidiandroid.observability.log_event is not logging.log_event", file=sys.stderr)
        return False
    print("OK   obsidiandroid.observability re-exports get_logger / log_event from logging subpackage")

    canon_olog_logger = importlib.import_module("obsidiandroid.observability.logging.logger")
    print(f"OK   obsidiandroid.observability.logging.logger -> {_module_path(canon_olog_logger)}")

    canon_olog_rt = importlib.import_module("obsidiandroid.observability.logging.runtime")
    print(f"OK   obsidiandroid.observability.logging.runtime -> {_module_path(canon_olog_rt)}")

    try:
        pop_pkg = importlib.import_module("obsidiandroid.observability.pipeline_observability")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.observability.pipeline_observability: {exc}", file=sys.stderr)
        return False
    print(f"OK   obsidiandroid.observability.pipeline_observability -> {_module_path(pop_pkg)}")

    try:
        pu_mod = importlib.import_module("obsidiandroid.cli.prompt_utils")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.cli.prompt_utils: {exc}", file=sys.stderr)
        return False
    print(f"OK   obsidiandroid.cli.prompt_utils -> {_module_path(pu_mod)}")

    try:
        gov_mod = importlib.import_module("obsidiandroid.governance.evidence_mode_resolver")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.governance.evidence_mode_resolver: {exc}", file=sys.stderr)
        return False
    print(f"OK   obsidiandroid.governance.evidence_mode_resolver -> {_module_path(gov_mod)}")

    try:
        diag_facade = importlib.import_module("obsidiandroid.diagnostics")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.diagnostics: {exc}", file=sys.stderr)
        return False
    print(f"OK   obsidiandroid.diagnostics -> {_module_path(diag_facade)}")
    for name in DIAGNOSTICS_TOP_LEVEL_MODULE_NAMES:
        canon_mod = importlib.import_module(f"obsidiandroid.diagnostics.{name}")
        facade_mod = getattr(diag_facade, name)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.diagnostics.{name} facade mismatch vs canonical",
                file=sys.stderr,
            )
            return False
    for pkg_name in DIAGNOSTICS_NESTED_PACKAGES:
        canon_pkg = importlib.import_module(f"obsidiandroid.diagnostics.{pkg_name}")
        if getattr(diag_facade, pkg_name) is not canon_pkg:
            print(
                f"FAIL: obsidiandroid.diagnostics.{pkg_name} façade mismatch vs canonical package",
                file=sys.stderr,
            )
            return False

    _rv_bundle_canon = importlib.import_module("obsidiandroid.diagnostics.research_validity.bundle")
    _ha_bundle_canon = importlib.import_module("obsidiandroid.diagnostics.hostile_audit.bundle")
    del _rv_bundle_canon, _ha_bundle_canon
    print("OK   obsidiandroid.diagnostics package exports canonical diagnostics modules")

    try:
        db_facade = importlib.import_module("obsidiandroid.database")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.database: {exc}", file=sys.stderr)
        return False
    print(f"OK   obsidiandroid.database -> {_module_path(db_facade)}")
    for attr, canon_name in FACADE_MODULE_PAIRS:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(db_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.database.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return False
        alias_mod = importlib.import_module(f"obsidiandroid.database.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.database.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return False
    print("OK   obsidiandroid.database facade submodules resolve canonically")

    return True


def main() -> int:
    """Import key surfaces and verify ``run_pipeline`` identity."""
    if not _check_import_smoke():
        return 1

    canon_runner = importlib.import_module("obsidiandroid.pipeline.runner")
    pipeline_mod = importlib.import_module("obsidiandroid.pipeline")
    if pipeline_mod.run_pipeline is not canon_runner.run_pipeline:
        print(
            "FAIL: obsidiandroid.pipeline.run_pipeline is not obsidiandroid.pipeline.runner.run_pipeline",
            file=sys.stderr,
        )
        return 1
    print("OK   obsidiandroid.pipeline.run_pipeline is obsidiandroid.pipeline.runner.run_pipeline")
    if pipeline_mod.DIAGNOSTICS_DIR != canon_runner.DIAGNOSTICS_DIR:
        print("FAIL: pipeline facade DIAGNOSTICS_DIR mismatch", file=sys.stderr)
        return 1
    if pipeline_mod.PARSER_QUALITY_PATH != canon_runner.PARSER_QUALITY_PATH:
        print("FAIL: pipeline facade PARSER_QUALITY_PATH mismatch", file=sys.stderr)
        return 1
    if pipeline_mod.PIPELINE_MAIN_LOGGER is not canon_runner.PIPELINE_MAIN_LOGGER:
        print("FAIL: pipeline facade PIPELINE_MAIN_LOGGER mismatch", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.pipeline public facade matches runner (DIAGNOSTICS_DIR, paths, logger)")
    _pipeline_physical_attrs = (
        "attach_engine_metadata",
        "av_engine_pipeline",
        "contract_filters",
        "engine_normalization",
        "main_facade",
        "runner",
        "run_bounds",
        "runtime_policy",
        "sample_exports",
        "sample_preparation",
        "score_av_engines",
        "stage_ablation",
        "stage_av_vendor",
        "stage_feature_enrichment",
        "stage_manifest",
        "stage_modeling",
        "stage_permission_trends_report",
        "stage_results_warehouse",
        "stage_samples",
        "vendor_metadata_pipeline",
        "engine_pipeline_utils",
        "permission_trends_selection",
    )
    for attr in _pipeline_physical_attrs:
        physical_mod = importlib.import_module(f"obsidiandroid.pipeline.{attr}")
        facade_mod = getattr(pipeline_mod, attr)
        if facade_mod is not physical_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.{attr} façade mismatch vs obsidiandroid.pipeline.{attr}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline facade exports canonical pipeline modules")

    _manifest_facade = importlib.import_module("obsidiandroid.pipeline.manifest")
    _manifest_pairs = (
        ("hashing", "obsidiandroid.pipeline.manifest.hashing"),
        ("paper_compliance_checks", "obsidiandroid.pipeline.manifest.paper_compliance_checks"),
        ("paper_figure_renderers", "obsidiandroid.pipeline.manifest.paper_figure_renderers"),
        ("runtime_support", "obsidiandroid.pipeline.manifest.runtime_support"),
        ("writer", "obsidiandroid.pipeline.manifest.writer"),
    )
    for attr, canon_name in _manifest_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_manifest_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.manifest.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.manifest.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.pipeline.manifest.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.manifest canonical package")

    _artifacts_facade = importlib.import_module("obsidiandroid.pipeline.artifacts")
    _artifacts_pairs = (
        ("paths", "obsidiandroid.pipeline.artifacts.paths"),
        ("registry", "obsidiandroid.pipeline.artifacts.registry"),
    )
    for attr, canon_name in _artifacts_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_artifacts_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.artifacts.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.artifacts.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.pipeline.artifacts.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.artifacts canonical package")

    _permission_trends_facade = importlib.import_module("obsidiandroid.pipeline.permission_trends")
    for attr in PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES:
        canon_name = f"obsidiandroid.pipeline.permission_trends.{attr}"
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_permission_trends_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.permission_trends.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.pipeline.permission_trends.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.pipeline.permission_trends.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.permission_trends submodules resolve canonically")

    _modeling_facade = importlib.import_module("obsidiandroid.modeling")
    for attr in MODELING_FACADE_EAGER_SUBMODULE_NAMES:
        canon_name = f"obsidiandroid.modeling.{attr}"
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_modeling_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.modeling.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.modeling.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.modeling.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        if attr in MODELING_FACADE_LEGACY_VIA_ML_CLASSIFICATION_TRAINING:
            print(
                f"FAIL: modeling facade still expects retired ml_classification.training parity for {attr}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.modeling submodules resolve canonically")

    _features_facade = importlib.import_module("obsidiandroid.features")
    for attr, canon_name in FEATURES_FACADE_ALIAS_TARGETS:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_features_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.features.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.features.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.features.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.features canonical aliases resolve")

    _labeling_facade = importlib.import_module("obsidiandroid.labeling")
    for attr in sorted(ML_CLASSIFICATION_LABELING_SUBMODULES):
        canon_name = f"obsidiandroid.labeling.{attr}"
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_labeling_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.labeling.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.labeling.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.labeling.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.labeling physical/alias submodules resolve canonically")

    # Pass 58: ``labeling.taxonomy`` is a deliberate wrapper module (not a ModuleType alias).
    taxonomy_mod = importlib.import_module("obsidiandroid.labeling.taxonomy")
    tax_path = Path(taxonomy_mod.__file__).resolve()
    if tax_path != (_REPO_ROOT / "src/obsidiandroid/labeling/taxonomy.py").resolve():
        print(
            f"FAIL: obsidiandroid.labeling.taxonomy expected at src/obsidiandroid/labeling/taxonomy.py, got {tax_path}",
            file=sys.stderr,
        )
        return 1
    mfc_canon = importlib.import_module("obsidiandroid.labeling.malware_family_constants")
    if taxonomy_mod.normalize_family_name("Flu-Bot") != mfc_canon.normalize_family_name("Flu-Bot"):
        print("FAIL: labeling.taxonomy.normalize_family_name diverged from legacy", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.labeling.taxonomy wrapper resolves and matches legacy normalization")
    print("OK   malware-family constants canonical module resolves")

    try:
        importlib.import_module("ml_classification")
    except ModuleNotFoundError:
        print("OK   ml_classification root namespace retired")
    else:
        print(
            "FAIL: ml_classification root namespace should be retired",
            file=sys.stderr,
        )
        return 1

    try:
        importlib.import_module("ml_classification.ml_utils")
    except ModuleNotFoundError:
        print("OK   ml_classification.ml_utils namespace retired")
    else:
        print(
            "FAIL: ml_classification.ml_utils should be retired",
            file=sys.stderr,
        )
        return 1

    try:
        importlib.import_module("ml_classification.training")
    except ModuleNotFoundError:
        pass
    else:
        print(
            "FAIL: ml_classification.training should be retired",
            file=sys.stderr,
        )
        return 1
    try:
        importlib.import_module("ml_classification.training.ml_trainers")
    except ModuleNotFoundError:
        pass
    else:
        print(
            "FAIL: ml_classification.training.ml_trainers should be retired",
            file=sys.stderr,
        )
        return 1
    print("OK   ml_classification.training and trainer namespaces retired")

    _cb_facade = importlib.import_module("obsidiandroid.classification_builder")
    for name in sorted(ML_CLASSIFICATION_BUILDER_SUBMODULES):
        canon_cb = importlib.import_module(f"obsidiandroid.classification_builder.{name}")
        facade_cb = getattr(_cb_facade, name)
        if facade_cb is not canon_cb:
            print(
                f"FAIL: obsidiandroid.classification_builder.{name} facade mismatch vs canonical submodule",
                file=sys.stderr,
            )
            return 1
    del _cb_facade, name, canon_cb, facade_cb
    print("OK   obsidiandroid.classification_builder exports canonical builder modules")

    _inf_facade = importlib.import_module("obsidiandroid.inference")
    for name in sorted(ML_CLASSIFICATION_INFERENCE_SUBMODULES):
        canon_inf = importlib.import_module(f"obsidiandroid.inference.{name}")
        facade_inf = getattr(_inf_facade, name)
        if facade_inf is not canon_inf:
            print(
                f"FAIL: obsidiandroid.inference.{name} facade mismatch vs canonical submodule",
                file=sys.stderr,
            )
            return 1
    del _inf_facade, name, canon_inf, facade_inf
    print("OK   obsidiandroid.inference exports canonical inference modules")

    _ew_facade = importlib.import_module("obsidiandroid.engine_weights")
    for name in sorted(ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES):
        canon_ew = importlib.import_module(f"obsidiandroid.engine_weights.{name}")
        facade_ew = getattr(_ew_facade, name)
        if facade_ew is not canon_ew:
            print(
                f"FAIL: obsidiandroid.engine_weights.{name} facade mismatch vs canonical submodule",
                file=sys.stderr,
            )
            return 1
    del _ew_facade, name, canon_ew, facade_ew
    print("OK   obsidiandroid.engine_weights exports canonical engine-weight modules")

    _vendors_facade = importlib.import_module("obsidiandroid.vendors")
    _vendors_parsing_pkg = importlib.import_module("obsidiandroid.vendors.parsing")
    _vendors_pairs = (
        ("vendor_parser_map", "obsidiandroid.vendors.parsing.vendor_parser_map"),
    )
    for attr, canon_name in _vendors_pairs:
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_vendors_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.vendors.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.vendors.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.vendors.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.vendors top-level aliases match obsidiandroid.vendors.parsing")

    # Vendor public-ish entrypoints (new surface): contracts + generic parser.
    from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata as _plm_canon
    from obsidiandroid.vendors.contracts.record_core import VendorClassificationRecord as _vcr_canon

    if getattr(_vendors_facade, "ParsedLabelMetadata") is not _plm_canon:
        print(
            "FAIL: obsidiandroid.vendors.ParsedLabelMetadata must re-export vendors.contracts.parsed_label_metadata.ParsedLabelMetadata",
            file=sys.stderr,
        )
        return 1
    if getattr(_vendors_facade, "VendorClassificationRecord") is not _vcr_canon:
        print(
            "FAIL: obsidiandroid.vendors.VendorClassificationRecord must re-export vendors.contracts.record_core.VendorClassificationRecord",
            file=sys.stderr,
        )
        return 1

    _generic_mod = importlib.import_module("obsidiandroid.vendors.parsing.generic_label_parser")
    if getattr(_vendors_facade, "parse_generic_classification") is not getattr(
        _generic_mod, "parse_generic_classification"
    ):
        print(
            "FAIL: obsidiandroid.vendors.parse_generic_classification must re-export vendors.parsing.generic_label_parser.parse_generic_classification",
            file=sys.stderr,
        )
        return 1
    del _plm_canon, _vcr_canon, _generic_mod
    print("OK   obsidiandroid.vendors public surface exports contracts + generic parser entrypoint")

    for name in VENDOR_PARSER_SUBMODULE_NAMES:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{name}")
        pkg_attr = getattr(_vendors_parsing_pkg, name)
        if pkg_attr is not canon_mod:
            print(
                f"FAIL: obsidiandroid.vendors.parsing.{name} package attr mismatch",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.vendors.parsing submodules resolve canonically")

    # Passes 61–63+: evaluation physical moves; canonical package exports stable submodules.
    _eval_export_names = tuple(
        name
        for name in importlib.import_module("obsidiandroid.evaluation").__all__
        if name not in {"VendorClassificationParseResult", "parse_vendor_classifications"}
    )
    for name in _eval_export_names:
        canon_mod = importlib.import_module(f"obsidiandroid.evaluation.{name}")
        eval_attr = getattr(importlib.import_module("obsidiandroid.evaluation"), name)
        if eval_attr is not canon_mod:
            print(
                f"FAIL: obsidiandroid.evaluation.{name} package attr mismatch vs canonical module",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.evaluation package exports canonical evaluation modules")

    # Evaluation public-ish entrypoint: parse_vendor_classifications should be importable from package root.
    _eval_pkg = importlib.import_module("obsidiandroid.evaluation")
    _eval_vcp = importlib.import_module("obsidiandroid.evaluation.vendor_classification_parser")
    if getattr(_eval_pkg, "parse_vendor_classifications") is not getattr(_eval_vcp, "parse_vendor_classifications"):
        print(
            "FAIL: obsidiandroid.evaluation.parse_vendor_classifications must re-export vendor_classification_parser.parse_vendor_classifications",
            file=sys.stderr,
        )
        return 1
    del _eval_pkg, _eval_vcp
    print("OK   obsidiandroid.evaluation exports parse_vendor_classifications entrypoint")

    _ml_cls_eval_three = ("ml_eval_engine", "ml_comparator_summary", "accuracy_band_utils")
    for mod in _ml_cls_eval_three:
        importlib.import_module(f"obsidiandroid.evaluation.{mod}")
    del mod, _ml_cls_eval_three

    # Vendor execution: canonical package remains importable and leaf modules resolve directly.
    _exec_pkg = importlib.import_module("obsidiandroid.vendors.execution")
    for name in getattr(_exec_pkg, "__all__", []):
        importlib.import_module(f"obsidiandroid.vendors.execution.{name}")
    print("OK   obsidiandroid.vendors.execution canonical modules import cleanly")

    _governance_facade = importlib.import_module("obsidiandroid.governance")
    for attr in getattr(_governance_facade, "__all__", []):
        canon_name = f"obsidiandroid.governance.{attr}"
        canon_mod = importlib.import_module(canon_name)
        facade_mod = getattr(_governance_facade, attr)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.governance.{attr} facade mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
        alias_mod = importlib.import_module(f"obsidiandroid.governance.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.governance.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.governance submodules resolve canonically")

    if not _check_common_reporting_surfaces():
        return 1

    if not _check_observability_diagnostics_database_shims():
        return 1

    if not _check_static_policy_scans():
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
DIAGNOSTICS_TOP_LEVEL_MODULE_NAMES: tuple[str, ...] = (
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
DIAGNOSTICS_NESTED_PACKAGES: tuple[str, ...] = ("research_validity", "hostile_audit")
