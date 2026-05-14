#!/usr/bin/env python3
"""Smoke-check that ``obsidiandroid`` and CLI/pipeline entry modules import correctly.

Static policy scans (legacy-root imports in ``src/``/``scripts``, tests, BOM, legacy leaf
shims under ``analysis``/``ml_classification``) live in
:mod:`scripts.dev.import_surface_policy`.

Fails if any tracked-style ``*.py`` tree under the repo starts with a **UTF-8 BOM**
(``\ufeff``), which breaks :func:`ast.parse` and confuses diffs—see
:func:`scripts.dev.import_surface_policy.collect_utf8_bom_python_sources`.

Static AST/file-system ratchets (legacy-root imports in ``src/`` / ``scripts`` / tests,
``# Filename:`` headers under ``src/`` (first segment must not be ``analysis``,
``ml_classification``, or repo-root ``database``), legacy leaf shim shape) live in
:mod:`scripts.dev.import_surface_policy`. Database façade / legacy-shim identity tuples
live in :mod:`obsidiandroid.database.facade_manifest` (imported by this script after
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
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from obsidiandroid.database.facade_manifest import FACADE_MODULE_PAIRS, LEGACY_SHIM_PAIRS
from obsidiandroid.governance.analysis_pipeline_governance_shim import (
    ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES,
)

from scripts.dev.import_surface_policy import (
    THIN_COMPAT_SHIM_POLICIES,
    collect_canonical_code_legacy_imports,
    collect_legacy_leaf_shim_violations,
    collect_nonparity_test_legacy_imports,
    collect_stale_canonical_filename_headers,
    collect_thin_compat_shim_violations,
    collect_utf8_bom_python_sources,
)


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
            "(use obsidiandroid.*; forbidden roots: analysis, ml_classification):",
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
            "(use obsidiandroid.* unless the file is allowlisted for parity on analysis/ml_classification):",
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

    legacy_leaf_errors = collect_legacy_leaf_shim_violations(_REPO_ROOT)
    if legacy_leaf_errors:
        print(
            "FAIL: legacy analysis/ml_classification leaf modules must stay thin shims:",
            file=sys.stderr,
        )
        for item in legacy_leaf_errors:
            print(f"  {item}", file=sys.stderr)
        return False
    print("OK   legacy analysis/ml_classification leaf shims")

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
    _diag_names = (
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
        "fused_permission_matrix_audit",
        "output_artifact_policy",
        "output_inventory",
        "permission_training_survival_audit",
        "rf_feature_importance_export",
        "split_ledger_resolve",
    )
    for name in _diag_names:
        canon_mod = importlib.import_module(f"obsidiandroid.diagnostics.{name}")
        legacy_mod = importlib.import_module(f"analysis.diagnostics.{name}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.diagnostics.{name} did not resolve to "
                f"obsidiandroid.diagnostics.{name}",
                file=sys.stderr,
            )
            return False
        facade_mod = getattr(diag_facade, name)
        if facade_mod is not canon_mod:
            print(
                f"FAIL: obsidiandroid.diagnostics.{name} facade mismatch vs canonical",
                file=sys.stderr,
            )
            return False
    _diag_pkg_names = ("research_validity", "hostile_audit")
    for pkg_name in _diag_pkg_names:
        canon_pkg = importlib.import_module(f"obsidiandroid.diagnostics.{pkg_name}")
        legacy_pkg = importlib.import_module(f"analysis.diagnostics.{pkg_name}")
        if legacy_pkg is not canon_pkg:
            print(
                f"FAIL: analysis.diagnostics.{pkg_name} did not resolve to "
                f"obsidiandroid.diagnostics.{pkg_name}",
                file=sys.stderr,
            )
            return False
        if getattr(diag_facade, pkg_name) is not canon_pkg:
            print(
                f"FAIL: obsidiandroid.diagnostics.{pkg_name} façade mismatch vs canonical package",
                file=sys.stderr,
            )
            return False

    _rv_bundle_canon = importlib.import_module("obsidiandroid.diagnostics.research_validity.bundle")
    _rv_bundle_legacy = importlib.import_module("analysis.diagnostics.research_validity.bundle")
    if _rv_bundle_legacy is not _rv_bundle_canon:
        print(
            "FAIL: research_validity.bundle identity mismatch "
            "(analysis.diagnostics vs obsidiandroid.diagnostics)",
            file=sys.stderr,
        )
        return False
    _ha_bundle_canon = importlib.import_module("obsidiandroid.diagnostics.hostile_audit.bundle")
    _ha_bundle_legacy = importlib.import_module("analysis.diagnostics.hostile_audit.bundle")
    if _ha_bundle_legacy is not _ha_bundle_canon:
        print(
            "FAIL: hostile_audit.bundle identity mismatch "
            "(analysis.diagnostics vs obsidiandroid.diagnostics)",
            file=sys.stderr,
        )
        return False
    print("OK   obsidiandroid.diagnostics package matches analysis.diagnostics shim")

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
    for _attr, _legacy_mod in LEGACY_SHIM_PAIRS:
        _legacy = importlib.import_module(_legacy_mod)
        _physical = importlib.import_module(f"obsidiandroid.database.{_attr}")
        if _legacy is not _physical:
            print(
                f"FAIL: {_legacy_mod} shim must match obsidiandroid.database.{_attr}",
                file=sys.stderr,
            )
            return False
    print("OK   obsidiandroid.database submodules match database")

    return True


def main() -> int:
    """Import key surfaces and verify ``run_pipeline`` identity."""
    if not _check_import_smoke():
        return 1

    canon_runner = importlib.import_module("obsidiandroid.pipeline.runner")
    legacy_runner = importlib.import_module("analysis.pipeline.runner")
    if canon_runner is not legacy_runner:
        print(
            "FAIL: obsidiandroid.pipeline.runner must be identical ModuleType to analysis.pipeline.runner shim",
            file=sys.stderr,
        )
        return 1
    pipeline_mod = importlib.import_module("obsidiandroid.pipeline")
    if pipeline_mod.run_pipeline is not canon_runner.run_pipeline:
        print(
            "FAIL: obsidiandroid.pipeline.run_pipeline is not obsidiandroid.pipeline.runner.run_pipeline",
            file=sys.stderr,
        )
        return 1
    print("OK   obsidiandroid.pipeline.run_pipeline is obsidiandroid.pipeline.runner.run_pipeline (legacy shim identical)")
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
        legacy_mod = importlib.import_module(f"analysis.pipeline.{attr}")
        if physical_mod is not legacy_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.{attr} physical vs analysis.pipeline.{attr} shim mismatch",
                file=sys.stderr,
            )
            return 1
        facade_mod = getattr(pipeline_mod, attr)
        if facade_mod is not physical_mod:
            print(
                f"FAIL: obsidiandroid.pipeline.{attr} façade mismatch vs obsidiandroid.pipeline.{attr}",
                file=sys.stderr,
            )
            return 1
    print(
        "OK   obsidiandroid.pipeline façade + leaf identity (Pass 66–71, 74); analysis.pipeline shims identical"
    )

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
        legacy_mod = importlib.import_module(f"analysis.pipeline.manifest.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.pipeline.manifest.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.manifest physical; analysis.pipeline.manifest shims (Pass 76)")

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
        legacy_mod = importlib.import_module(f"analysis.pipeline.artifacts.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.pipeline.artifacts.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.artifacts physical; analysis.pipeline.artifacts shims (Pass 76)")

    _fe_pairs = (
        ("assign_tier_scores", "obsidiandroid.feature_engineering.assign_tier_scores"),
        ("compute_vendor_scores", "obsidiandroid.feature_engineering.compute_vendor_scores"),
        ("prepare_engine_metrics", "obsidiandroid.feature_engineering.prepare_engine_metrics"),
        ("pattern_analysis", "obsidiandroid.feature_engineering.pattern_analysis"),
    )
    for attr, canon_name in _fe_pairs:
        canon_mod = importlib.import_module(canon_name)
        # Package namespace binds ``assign_tier_scores`` to a function, not the submodule — skip getattr.
        alias_mod = importlib.import_module(f"obsidiandroid.feature_engineering.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.feature_engineering.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.feature_engineering.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.feature_engineering.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.feature_engineering physical; analysis.feature_engineering shims (Pass 78)")

    _orch_pairs = (
        ("metadata_features", "obsidiandroid.orchestration.metadata_features"),
        ("methodology_artifacts", "obsidiandroid.orchestration.methodology_artifacts"),
        ("permission_features", "obsidiandroid.orchestration.permission_features"),
        ("profile_filters", "obsidiandroid.orchestration.profile_filters"),
        ("runtime_reporting", "obsidiandroid.orchestration.runtime_reporting"),
    )
    for attr, canon_name in _orch_pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.orchestration.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.orchestration.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.orchestration.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.orchestration.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.orchestration physical; analysis.orchestration shims (Pass 80)")

    _matrix_pairs = (
        ("av_binary_matrix_builder", "obsidiandroid.matrix.av_binary_matrix_builder"),
        ("enrich_malicious_scores", "obsidiandroid.matrix.enrich_malicious_scores"),
        ("enrich_score_features", "obsidiandroid.matrix.enrich_score_features"),
    )
    for attr, canon_name in _matrix_pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.matrix.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.matrix.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.matrix.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.matrix.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.matrix physical; analysis.matrix shims (Pass 80)")

    _risk_band_pairs = (
        ("assign_risk_band", "obsidiandroid.risk_band.assign_risk_band"),
        ("phase_score_engines", "obsidiandroid.risk_band.phase_score_engines"),
    )
    for attr, canon_name in _risk_band_pairs:
        canon_mod = importlib.import_module(canon_name)
        alias_mod = importlib.import_module(f"obsidiandroid.risk_band.{attr}")
        if alias_mod is not canon_mod:
            print(
                f"FAIL: import obsidiandroid.risk_band.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.risk_band.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.risk_band.{attr} shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.risk_band physical; analysis.risk_band shims (Pass 81)")

    _permission_trends_facade = importlib.import_module("obsidiandroid.pipeline.permission_trends")
    _permission_trends_pairs = (
        ("bundle_manifest", "obsidiandroid.pipeline.permission_trends.bundle_manifest"),
        ("constants", "obsidiandroid.pipeline.permission_trends.constants"),
        ("publish_paths", "obsidiandroid.pipeline.permission_trends.publish_paths"),
        ("reporting_support", "obsidiandroid.pipeline.permission_trends.reporting_support"),
        ("sample_permission_data", "obsidiandroid.pipeline.permission_trends.sample_permission_data"),
        ("stats_core", "obsidiandroid.pipeline.permission_trends.stats_core"),
    )
    for attr, canon_name in _permission_trends_pairs:
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
        legacy_mod = importlib.import_module(f"analysis.pipeline.permission_trends.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.pipeline.permission_trends.{attr} legacy shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.pipeline.permission_trends submodules match legacy shims (Pass 74)")

    _modeling_facade = importlib.import_module("obsidiandroid.modeling")
    _modeling_pairs = (
        ("data_alignment", "obsidiandroid.modeling.data_alignment"),
        ("distribution_reporter", "obsidiandroid.modeling.distribution_reporter"),
        ("feature_label_alignment_helper", "obsidiandroid.modeling.feature_label_alignment_helper"),
        ("ml_result_analyzer", "obsidiandroid.modeling.ml_result_analyzer"),
        ("ml_result_validator", "obsidiandroid.modeling.ml_result_validator"),
        ("model_prediction", "obsidiandroid.modeling.model_prediction"),
        ("model_trainer_factory", "obsidiandroid.modeling.model_trainer_factory"),
        ("pipeline_core", "obsidiandroid.modeling.pipeline_core"),
    )
    for attr, canon_name in _modeling_pairs:
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
                legacy_name = f"ml_classification.training.{attr}"
            else:
                legacy_name = f"ml_classification.ml_utils.{attr}"
            legacy_mod = importlib.import_module(legacy_name)
            if legacy_mod is not canon_mod:
                print(
                    f"FAIL: {legacy_name} did not resolve to {canon_name}",
                    file=sys.stderr,
                )
                return 1
    feature_alignment_canon = importlib.import_module("obsidiandroid.modeling.feature_alignment_utils")
    feature_alignment_legacy = importlib.import_module("ml_classification.ml_utils.feature_alignment_utils")
    if feature_alignment_legacy is not feature_alignment_canon:
        print(
            "FAIL: ml_classification.ml_utils.feature_alignment_utils did not resolve to "
            "obsidiandroid.modeling.feature_alignment_utils",
            file=sys.stderr,
        )
        return 1
    _physical_training_slices = (
        "pipeline_result_promoter",
        "train_model_executor",
        "model_training",
        "prediction_builder",
        "model_evaluation",
        "training_helpers",
    )
    for mod in _physical_training_slices:
        canon_tm = importlib.import_module(f"obsidiandroid.modeling.{mod}")
        legacy_tm = importlib.import_module(f"ml_classification.training.{mod}")
        if legacy_tm is not canon_tm:
            print(
                f"FAIL: ml_classification.training.{mod} did not resolve to "
                f"obsidiandroid.modeling.{mod}",
                file=sys.stderr,
            )
            return 1
    del mod, canon_tm, legacy_tm, _physical_training_slices
    for mod in (
        "random_forest_trainer",
        "balanced_random_forest_trainer",
        "logistic_regression_trainer",
        "svm_trainer",
        "xgboost_trainer",
    ):
        canon_tr = importlib.import_module(f"obsidiandroid.modeling.ml_trainers.{mod}")
        legacy_tr = importlib.import_module(f"ml_classification.training.ml_trainers.{mod}")
        if legacy_tr is not canon_tr:
            print(
                f"FAIL: ml_classification.training.ml_trainers.{mod} did not resolve to "
                f"obsidiandroid.modeling.ml_trainers.{mod}",
                file=sys.stderr,
            )
            return 1
    del mod, canon_tr, legacy_tr
    print("OK   obsidiandroid.modeling submodules match ml_classification")

    _features_facade = importlib.import_module("obsidiandroid.features")
    _features_pairs = (
        ("feature_encoder", "obsidiandroid.features.vectorization.feature_encoder"),
        ("feature_engine_selection", "obsidiandroid.features.vectorization.feature_engine_selection"),
        ("feature_schema_audit", "obsidiandroid.features.feature_schema_audit"),
        ("feature_vector_builder", "obsidiandroid.features.vectorization.feature_vector_builder"),
        ("feature_vendor_extractor", "obsidiandroid.features.vectorization.feature_vendor_extractor"),
    )
    for attr, canon_name in _features_pairs:
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
        if attr == "feature_schema_audit":
            legacy_name = "ml_classification.training.feature_schema_audit"
        else:
            legacy_name = f"ml_classification.vectorization.{attr}"
        legacy_mod = importlib.import_module(legacy_name)
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: {legacy_name} legacy shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print(
        "OK   obsidiandroid.features physical vectorization; ml_classification.vectorization shims identical (Pass 83)"
    )

    _labeling_facade = importlib.import_module("obsidiandroid.labeling")
    _labeling_pairs = (
        ("classification_label_resolver", "obsidiandroid.labeling.classification_label_resolver"),
        ("label_builder_wrapper", "obsidiandroid.labeling.label_builder_wrapper"),
        ("label_field_normalizer", "obsidiandroid.labeling.label_field_normalizer"),
        ("label_format_generator", "obsidiandroid.labeling.label_format_generator"),
        ("label_input_validator", "obsidiandroid.labeling.label_input_validator"),
        ("label_postprocessor", "obsidiandroid.labeling.label_postprocessor"),
    )
    for attr, canon_name in _labeling_pairs:
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
        legacy_mod = importlib.import_module(f"ml_classification.labeling.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: ml_classification.labeling.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.labeling physical/alias submodules match legacy shims")

    # Pass 58: ``labeling.taxonomy`` is a deliberate wrapper module (not a ModuleType alias).
    taxonomy_mod = importlib.import_module("obsidiandroid.labeling.taxonomy")
    tax_path = Path(taxonomy_mod.__file__).resolve()
    if tax_path != (_REPO_ROOT / "src/obsidiandroid/labeling/taxonomy.py").resolve():
        print(
            f"FAIL: obsidiandroid.labeling.taxonomy expected at src/obsidiandroid/labeling/taxonomy.py, got {tax_path}",
            file=sys.stderr,
        )
        return 1
    import ml_classification.common.malware_family_constants as _mfc_tax

    if taxonomy_mod.normalize_family_name("Flu-Bot") != _mfc_tax.normalize_family_name("Flu-Bot"):
        print("FAIL: labeling.taxonomy.normalize_family_name diverged from legacy", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.labeling.taxonomy wrapper resolves and matches legacy normalization")

    mfc_canon = importlib.import_module("obsidiandroid.labeling.malware_family_constants")
    mfc_legacy = importlib.import_module("ml_classification.common.malware_family_constants")
    if mfc_legacy is not mfc_canon:
        print(
            "FAIL: ml_classification.common.malware_family_constants did not resolve to "
            "obsidiandroid.labeling.malware_family_constants",
            file=sys.stderr,
        )
        return 1
    print("OK   malware-family constants canonical module matches legacy shim")

    _mlu = importlib.import_module("ml_classification.ml_utils")
    _mlu_ds = importlib.import_module("ml_classification.ml_utils.dataset_splitter")
    if getattr(_mlu, "dataset_splitter") is not _mlu_ds:
        print(
            "FAIL: ml_classification.ml_utils.dataset_splitter getattr mismatch vs explicit submodule import",
            file=sys.stderr,
        )
        return 1
    _mlc = importlib.import_module("ml_classification.common")
    _mlc_mfc = importlib.import_module("ml_classification.common.malware_family_constants")
    if getattr(_mlc, "malware_family_constants") is not _mlc_mfc:
        print(
            "FAIL: ml_classification.common.malware_family_constants getattr mismatch "
            "vs explicit submodule import",
            file=sys.stderr,
        )
        return 1
    del _mlu, _mlu_ds, _mlc, _mlc_mfc
    print(
        "OK   ml_classification.ml_utils / common package accessors match submodule imports (Pass 99)"
    )

    _pass100_ml_subpackages: tuple[tuple[str, tuple[str, ...]], ...] = (
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
            (
                "compile_classification_results",
                "ml_report_builder",
            ),
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
    for _pkg_qual, _subnames in _pass100_ml_subpackages:
        _pass100_errors = _legacy_ml_pkg_getattr_errors(_pkg_qual, _subnames)
        if _pass100_errors:
            for _msg in _pass100_errors:
                print(f"FAIL: {_msg}", file=sys.stderr)
            return 1
    del _pkg_qual, _subnames, _pass100_ml_subpackages, _pass100_errors
    print(
        "OK   ml_classification subpackage accessors match submodule imports (Pass 100)"
    )

    _cb_facade = importlib.import_module("obsidiandroid.classification_builder")
    _cb_submods = (
        "classification_constants",
        "classification_row_builder",
        "prediction_utils",
        "record_enrichment",
        "sample_classification_builder",
        "vendor_record_selector",
    )
    for name in _cb_submods:
        canon_cb = importlib.import_module(f"obsidiandroid.classification_builder.{name}")
        facade_cb = getattr(_cb_facade, name)
        if facade_cb is not canon_cb:
            print(
                f"FAIL: obsidiandroid.classification_builder.{name} facade mismatch vs canonical submodule",
                file=sys.stderr,
            )
            return 1
        legacy_cb = importlib.import_module(f"ml_classification.builder.{name}")
        if legacy_cb is not canon_cb:
            print(
                f"FAIL: ml_classification.builder.{name} did not resolve to "
                f"obsidiandroid.classification_builder.{name}",
                file=sys.stderr,
            )
            return 1
    del _cb_facade, _cb_submods, name, canon_cb, facade_cb, legacy_cb
    print("OK   obsidiandroid.classification_builder matches ml_classification.builder shims")

    _inf_facade = importlib.import_module("obsidiandroid.inference")
    _inf_submods = (
        "label_consensus_engine",
        "malware_type_engine",
        "signal_health_checker",
        "threat_class_engine",
    )
    for name in _inf_submods:
        canon_inf = importlib.import_module(f"obsidiandroid.inference.{name}")
        facade_inf = getattr(_inf_facade, name)
        if facade_inf is not canon_inf:
            print(
                f"FAIL: obsidiandroid.inference.{name} facade mismatch vs canonical submodule",
                file=sys.stderr,
            )
            return 1
        legacy_inf = importlib.import_module(f"ml_classification.inference.{name}")
        if legacy_inf is not canon_inf:
            print(
                f"FAIL: ml_classification.inference.{name} did not resolve to "
                f"obsidiandroid.inference.{name}",
                file=sys.stderr,
            )
            return 1
    del _inf_facade, _inf_submods, name, canon_inf, facade_inf, legacy_inf
    print("OK   obsidiandroid.inference matches ml_classification.inference shims")

    _ew_facade = importlib.import_module("obsidiandroid.engine_weights")
    _ew_submods = (
        "assign_detection_tiers",
        "build_classification_weights",
        "classification_weight_inspector",
        "classification_weight_utils",
        "compute_reliability_score",
        "engine_weights_utils",
    )
    for name in _ew_submods:
        canon_ew = importlib.import_module(f"obsidiandroid.engine_weights.{name}")
        facade_ew = getattr(_ew_facade, name)
        if facade_ew is not canon_ew:
            print(
                f"FAIL: obsidiandroid.engine_weights.{name} facade mismatch vs canonical submodule",
                file=sys.stderr,
            )
            return 1
        legacy_ew = importlib.import_module(f"ml_classification.engine_weights.{name}")
        if legacy_ew is not canon_ew:
            print(
                f"FAIL: ml_classification.engine_weights.{name} did not resolve to "
                f"obsidiandroid.engine_weights.{name}",
                file=sys.stderr,
            )
            return 1
    del _ew_facade, _ew_submods, name, canon_ew, facade_ew, legacy_ew
    print("OK   obsidiandroid.engine_weights matches ml_classification.engine_weights shims")

    canon_ccr = importlib.import_module("obsidiandroid.reporting.compile_classification_results")
    legacy_ccr = importlib.import_module("ml_classification.reporting.compile_classification_results")
    if legacy_ccr is not canon_ccr:
        print(
            "FAIL: ml_classification.reporting.compile_classification_results did not resolve to "
            "obsidiandroid.reporting.compile_classification_results",
            file=sys.stderr,
        )
        return 1
    del canon_ccr, legacy_ccr
    print("OK   obsidiandroid.reporting.compile_classification_results shim matches canonical")

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
        legacy_mod = importlib.import_module(f"analysis.vendor_processing.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: import analysis.vendor_processing.{attr} did not resolve to {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.vendors top-level aliases match obsidiandroid.vendors.parsing + legacy shim")

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

    _vendors_parsing_pairs = (
        "generic_label_parser",
        "vendor_parser_map",
        "parser_defaults",
        "parser_confidence_estimator",
    )
    for name in _vendors_parsing_pairs:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{name}")
        pkg_attr = getattr(_vendors_parsing_pkg, name)
        if pkg_attr is not canon_mod:
            print(
                f"FAIL: obsidiandroid.vendors.parsing.{name} package attr mismatch",
                file=sys.stderr,
            )
            return 1
        legacy_mod = importlib.import_module(f"analysis.vendor_processing.{name}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.vendor_processing.{name} legacy shim mismatch",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.vendors.parsing key modules preserve identity with legacy shim")

    # Passes 61–63: evaluation physical moves; legacy package registers identity.
    eval_pairs = (
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
    )
    for name in eval_pairs:
        canon_mod = importlib.import_module(f"obsidiandroid.evaluation.{name}")
        legacy_mod = importlib.import_module(f"analysis.evaluation.{name}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.evaluation.{name} did not resolve to obsidiandroid.evaluation.{name}",
                file=sys.stderr,
            )
            return 1
    print("OK   analysis.evaluation package shim matches obsidiandroid.evaluation")

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
        canon_ml = importlib.import_module(f"obsidiandroid.evaluation.{mod}")
        legacy_ml = importlib.import_module(f"ml_classification.ml_utils.{mod}")
        if legacy_ml is not canon_ml:
            print(
                f"FAIL: ml_classification.ml_utils.{mod} did not resolve to "
                f"obsidiandroid.evaluation.{mod}",
                file=sys.stderr,
            )
            return 1
    canon_rb = importlib.import_module("obsidiandroid.evaluation.ml_report_builder")
    legacy_rb = importlib.import_module("ml_classification.reporting.ml_report_builder")
    if legacy_rb is not canon_rb:
        print(
            "FAIL: ml_classification.reporting.ml_report_builder did not resolve to "
            "obsidiandroid.evaluation.ml_report_builder",
            file=sys.stderr,
        )
        return 1
    splitter_canon = importlib.import_module("obsidiandroid.modeling.dataset_splitter")
    splitter_legacy = importlib.import_module("ml_classification.ml_utils.dataset_splitter")
    if splitter_legacy is not splitter_canon:
        print(
            "FAIL: ml_classification.ml_utils.dataset_splitter did not resolve to "
            "obsidiandroid.modeling.dataset_splitter",
            file=sys.stderr,
        )
        return 1
    del mod, canon_ml, legacy_ml, _ml_cls_eval_three, canon_rb, legacy_rb, splitter_canon, splitter_legacy

    # Vendor execution: physical move from analysis.execution to obsidiandroid.vendors.execution.
    exec_pairs = (
        "av_parser_executor",
        "vendor_parser_runner",
        "vendor_record_factory",
        "vendor_classification_processor",
    )
    for name in exec_pairs:
        canon_mod = importlib.import_module(f"obsidiandroid.vendors.execution.{name}")
        legacy_mod = importlib.import_module(f"analysis.execution.{name}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.execution.{name} did not resolve to obsidiandroid.vendors.execution.{name}",
                file=sys.stderr,
            )
            return 1
    print("OK   analysis.execution package shim matches obsidiandroid.vendors.execution")

    _governance_facade = importlib.import_module("obsidiandroid.governance")
    for attr in sorted(ANALYSIS_PIPELINE_GOVERNANCE_SUBMODULES):
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
        legacy_mod = importlib.import_module(f"analysis.pipeline.governance.{attr}")
        if legacy_mod is not canon_mod:
            print(
                f"FAIL: analysis.pipeline.governance.{attr} legacy shim mismatch vs {canon_name}",
                file=sys.stderr,
            )
            return 1
    print("OK   obsidiandroid.governance pipeline governance matches legacy shims (Pass 75)")

    if not _check_common_reporting_surfaces():
        return 1

    if not _check_observability_diagnostics_database_shims():
        return 1

    if not _check_static_policy_scans():
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
