#!/usr/bin/env python3
"""Smoke-check that ``obsidiandroid`` and CLI/pipeline entry modules import correctly.

Run from the repository root after ``pip install -e .`` or with ``PYTHONPATH`` including
``src/`` (see docs/AGENTS.md and docs/STRUCTURE_MIGRATION_PLAN.md). Exits nonzero on failure.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

# Ensure repo root is importable (``scripts.*``, ``utils``) when this
# file is run from another working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _module_path(mod: ModuleType) -> str:
    path = getattr(mod, "__file__", None)
    return str(path) if path else "(namespace package)"


def main() -> int:
    """Import key surfaces and verify ``run_pipeline`` identity."""
    try:
        pkg = importlib.import_module("obsidiandroid")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid -> {_module_path(pkg)}")

    for name in (
        "obsidiandroid.cli.startup_menu",
        "obsidiandroid.cli.pipeline_entry",
        "obsidiandroid.pipeline",
    ):
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            print(f"FAIL: import {name}: {exc}", file=sys.stderr)
            return 1
        print(f"OK   {name} -> {_module_path(mod)}")

    runner_mod = importlib.import_module("analysis.pipeline.runner")
    pipeline_mod = importlib.import_module("obsidiandroid.pipeline")
    if pipeline_mod.run_pipeline is not runner_mod.run_pipeline:
        print(
            "FAIL: obsidiandroid.pipeline.run_pipeline is not analysis.pipeline.runner.run_pipeline",
            file=sys.stderr,
        )
        return 1
    print("OK   obsidiandroid.pipeline.run_pipeline is analysis.pipeline.runner.run_pipeline")
    if pipeline_mod.DIAGNOSTICS_DIR != runner_mod.DIAGNOSTICS_DIR:
        print("FAIL: pipeline facade DIAGNOSTICS_DIR mismatch", file=sys.stderr)
        return 1
    if pipeline_mod.PARSER_QUALITY_PATH != runner_mod.PARSER_QUALITY_PATH:
        print("FAIL: pipeline facade PARSER_QUALITY_PATH mismatch", file=sys.stderr)
        return 1
    if pipeline_mod.PIPELINE_MAIN_LOGGER is not runner_mod.PIPELINE_MAIN_LOGGER:
        print("FAIL: pipeline facade PIPELINE_MAIN_LOGGER mismatch", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.pipeline public facade matches runner (DIAGNOSTICS_DIR, paths, logger)")

    common_checks = (
        "obsidiandroid.common.hash_utils",
        "obsidiandroid.common.ml_console",
        "obsidiandroid.common.display_distribution",
        "obsidiandroid.common.output_paths",
    )
    for name in common_checks:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            print(f"FAIL: import {name}: {exc}", file=sys.stderr)
            return 1
        print(f"OK   {name} -> {_module_path(mod)}")

    hash_pkg = importlib.import_module("obsidiandroid.common.hash_utils")
    shim_hash = importlib.import_module("utils.hash_utils")
    if shim_hash.sha256_hex is not hash_pkg.sha256_hex:
        print("FAIL: utils.hash_utils.sha256_hex is not obsidiandroid.common.hash_utils.sha256_hex", file=sys.stderr)
        return 1
    print("OK   utils.hash_utils re-exports match obsidiandroid.common.hash_utils")

    canon_op = importlib.import_module("obsidiandroid.common.output_paths")
    shim_op = importlib.import_module("utils.output_paths")
    if shim_op.output_root is not canon_op.output_root:
        print("FAIL: utils.output_paths.output_root shim mismatch", file=sys.stderr)
        return 1
    if shim_op.project_logs_root is not canon_op.project_logs_root:
        print("FAIL: utils.output_paths.project_logs_root shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.output_paths re-exports match obsidiandroid.common.output_paths")

    canon_occ = importlib.import_module("obsidiandroid.common.output_cleanup_clutter")
    shim_occ = importlib.import_module("utils.output_cleanup_clutter")
    if shim_occ.WORKBOOK_CORRUPT_GLOB != canon_occ.WORKBOOK_CORRUPT_GLOB:
        print("FAIL: output_cleanup_clutter shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.output_cleanup_clutter re-exports match obsidiandroid.common.output_cleanup_clutter")

    canon_av = importlib.import_module("obsidiandroid.common.av_detection_tiers")
    shim_av = importlib.import_module("utils.av_detection_tiers")
    if shim_av.get_detection_tier is not canon_av.get_detection_tier:
        print("FAIL: av_detection_tiers shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.av_detection_tiers re-exports match obsidiandroid.common.av_detection_tiers")

    canon_smp = importlib.import_module("obsidiandroid.common.sample_metadata_preprocessor")
    shim_smp = importlib.import_module("utils.sample_metadata_preprocessor")
    if shim_smp.prepare_sample_dataframe is not canon_smp.prepare_sample_dataframe:
        print("FAIL: sample_metadata_preprocessor shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.sample_metadata_preprocessor re-exports match obsidiandroid.common.sample_metadata_preprocessor")

    canon_cmp = importlib.import_module("obsidiandroid.governance.compliance")
    shim_cmp = importlib.import_module("utils.compliance")
    if shim_cmp.build_compliance_report is not canon_cmp.build_compliance_report:
        print("FAIL: utils.compliance shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.compliance re-exports match obsidiandroid.governance.compliance")

    canon_lt = importlib.import_module("obsidiandroid.reporting.latex_tables")
    shim_lt = importlib.import_module("utils.latex_tables")
    if shim_lt.LatexTableSpec is not canon_lt.LatexTableSpec:
        print("FAIL: utils.latex_tables LatexTableSpec shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.latex_tables re-exports match obsidiandroid.reporting.latex_tables")

    canon_fdr = importlib.import_module("obsidiandroid.reporting.family_distribution_report")
    shim_fdr = importlib.import_module("utils.family_distribution_report")
    if shim_fdr.print_family_distribution_stats is not canon_fdr.print_family_distribution_stats:
        print("FAIL: family_distribution_report shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.family_distribution_report re-exports match obsidiandroid.reporting.family_distribution_report")

    canon_pm = importlib.import_module("obsidiandroid.cli.profile_manager")
    shim_pm = importlib.import_module("utils.profile_manager")
    if shim_pm.load_profile is not canon_pm.load_profile:
        print("FAIL: profile_manager shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.profile_manager re-exports match obsidiandroid.cli.profile_manager")

    canon_crr = importlib.import_module("obsidiandroid.governance.cohort_readiness_report")
    shim_crr = importlib.import_module("utils.cohort_readiness_report")
    if shim_crr.print_cohort_readiness_report is not canon_crr.print_cohort_readiness_report:
        print("FAIL: cohort_readiness_report shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.cohort_readiness_report re-exports match obsidiandroid.governance.cohort_readiness_report")

    canon_crep = importlib.import_module("obsidiandroid.governance.cohort_reproducibility")
    shim_crep = importlib.import_module("utils.cohort_reproducibility")
    if shim_crep.apply_analysis_snapshot_lock is not canon_crep.apply_analysis_snapshot_lock:
        print("FAIL: cohort_reproducibility shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.cohort_reproducibility re-exports match obsidiandroid.governance.cohort_reproducibility")

    canon_rm = importlib.import_module("obsidiandroid.governance.run_manifest")
    shim_rm = importlib.import_module("utils.run_manifest")
    if shim_rm.generate_run_id is not canon_rm.generate_run_id:
        print("FAIL: run_manifest.generate_run_id shim mismatch", file=sys.stderr)
        return 1
    if shim_rm.write_run_manifest is not canon_rm.write_run_manifest:
        print("FAIL: run_manifest.write_run_manifest shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.run_manifest re-exports match obsidiandroid.governance.run_manifest")

    canon_art = importlib.import_module("obsidiandroid.governance.artifacts")
    shim_art = importlib.import_module("utils.artifacts")
    if shim_art.ManifestWriter is not canon_art.ManifestWriter:
        print("FAIL: artifacts.ManifestWriter shim mismatch", file=sys.stderr)
        return 1
    if shim_art.ArtifactKey is not canon_art.ArtifactKey:
        print("FAIL: artifacts.ArtifactKey shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.artifacts re-exports match obsidiandroid.governance.artifacts")

    canon_en = importlib.import_module("obsidiandroid.common.export_naming")
    shim_en = importlib.import_module("utils.exporting.naming")
    if shim_en.safe_sheet_name is not canon_en.safe_sheet_name:
        print(
            "FAIL: utils.exporting.naming.safe_sheet_name is not obsidiandroid.common.export_naming",
            file=sys.stderr,
        )
        return 1
    print("OK   utils.exporting.naming re-exports match obsidiandroid.common.export_naming")

    canon_ev = importlib.import_module("obsidiandroid.common.export_vendor_raw")
    shim_ev = importlib.import_module("utils.exporting.vendor_raw")
    if shim_ev.is_parquet_supported is not canon_ev.is_parquet_supported:
        print("FAIL: export_vendor_raw shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.exporting.vendor_raw re-exports match obsidiandroid.common.export_vendor_raw")

    canon_wb = importlib.import_module("obsidiandroid.common.export_workbook")
    shim_wb = importlib.import_module("utils.exporting.workbook")
    if shim_wb.WorkbookLock is not canon_wb.WorkbookLock:
        print("FAIL: export_workbook WorkbookLock shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.exporting.workbook re-exports match obsidiandroid.common.export_workbook")

    canon_cm = importlib.import_module("obsidiandroid.reporting.confusion_matrix_exporter")
    shim_cm = importlib.import_module("utils.confusion_matrix_exporter")
    if shim_cm.export_confusion_matrix_image is not canon_cm.export_confusion_matrix_image:
        print("FAIL: confusion_matrix_exporter export_confusion_matrix_image shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.confusion_matrix_exporter re-exports match obsidiandroid.reporting")

    canon_em = importlib.import_module("obsidiandroid.reporting.export_manager")
    shim_em = importlib.import_module("utils.export_manager")
    if shim_em is not canon_em:
        print(
            "FAIL: utils.export_manager must alias obsidiandroid.reporting.export_manager module object",
            file=sys.stderr,
        )
        return 1
    if shim_em.export_dataframe_to_excel is not canon_em.export_dataframe_to_excel:
        print("FAIL: export_manager.export_dataframe_to_excel shim mismatch", file=sys.stderr)
        return 1
    print("OK   utils.export_manager aliases obsidiandroid.reporting.export_manager")

    canon_me = importlib.import_module("obsidiandroid.modeling.model_exporter")
    shim_me = importlib.import_module("utils.model_exporter")
    if shim_me.export_model_to_file is not canon_me.export_model_to_file:
        print("FAIL: utils.model_exporter.export_model_to_file is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.model_exporter re-exports match obsidiandroid.modeling.model_exporter")

    canon_oh = importlib.import_module("obsidiandroid.common.output_hygiene")
    shim_oh = importlib.import_module("utils.output_hygiene")
    if shim_oh.resolve_stable_output_root_for_mirrors is not canon_oh.resolve_stable_output_root_for_mirrors:
        print("FAIL: utils.output_hygiene.resolve_stable_output_root_for_mirrors is not canonical", file=sys.stderr)
        return 1
    if shim_oh.mirror_csv_text_run_then_global is not canon_oh.mirror_csv_text_run_then_global:
        print("FAIL: utils.output_hygiene.mirror_csv_text_run_then_global is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.output_hygiene re-exports match obsidiandroid.common.output_hygiene")

    try:
        obs_pkg = importlib.import_module("obsidiandroid.observability")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.observability: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.observability -> {_module_path(obs_pkg)}")

    try:
        canon_olog = importlib.import_module("obsidiandroid.observability.logging")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.observability.logging: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.observability.logging -> {_module_path(canon_olog)}")

    if obs_pkg.get_logger is not canon_olog.get_logger:
        print("FAIL: obsidiandroid.observability.get_logger is not logging.get_logger", file=sys.stderr)
        return 1
    if obs_pkg.log_event is not canon_olog.log_event:
        print("FAIL: obsidiandroid.observability.log_event is not logging.log_event", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.observability re-exports get_logger / log_event from logging subpackage")

    shim_olog = importlib.import_module("utils.logging")
    if shim_olog.get_logger is not canon_olog.get_logger:
        print("FAIL: utils.logging.get_logger is not canonical", file=sys.stderr)
        return 1
    if shim_olog.log_event is not canon_olog.log_event:
        print("FAIL: utils.logging.log_event is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.logging re-exports match obsidiandroid.observability.logging")

    canon_olog_logger = importlib.import_module("obsidiandroid.observability.logging.logger")
    shim_olog_logger = importlib.import_module("utils.logging.logger")
    if shim_olog_logger.close_all_loggers is not canon_olog_logger.close_all_loggers:
        print("FAIL: utils.logging.logger.close_all_loggers is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.logging.logger re-exports match obsidiandroid.observability.logging.logger")

    canon_olog_rt = importlib.import_module("obsidiandroid.observability.logging.runtime")
    shim_olog_rt = importlib.import_module("utils.logging.runtime")
    if shim_olog_rt.start_runtime_logging is not canon_olog_rt.start_runtime_logging:
        print("FAIL: utils.logging.runtime.start_runtime_logging is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.logging.runtime re-exports match obsidiandroid.observability.logging.runtime")

    canon_pu = importlib.import_module("obsidiandroid.cli.prompt_utils")
    shim_pu = importlib.import_module("utils.prompt_utils")
    if shim_pu.prompt_yes_no is not canon_pu.prompt_yes_no:
        print("FAIL: utils.prompt_utils.prompt_yes_no is not canonical", file=sys.stderr)
        return 1
    print("OK   utils.prompt_utils re-exports match obsidiandroid.cli.prompt_utils")

    try:
        gov_mod = importlib.import_module("obsidiandroid.governance.evidence_mode_resolver")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.governance.evidence_mode_resolver: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.governance.evidence_mode_resolver -> {_module_path(gov_mod)}")

    shim_em = importlib.import_module("utils.evidence_mode_resolver")
    if shim_em.resolve_evidence_mode is not gov_mod.resolve_evidence_mode:
        print(
            "FAIL: utils.evidence_mode_resolver.resolve_evidence_mode is not canonical",
            file=sys.stderr,
        )
        return 1
    print("OK   utils.evidence_mode_resolver re-exports match governance canonical module")

    try:
        diag_facade = importlib.import_module("obsidiandroid.diagnostics")
    except Exception as exc:
        print(f"FAIL: import obsidiandroid.diagnostics: {exc}", file=sys.stderr)
        return 1
    print(f"OK   obsidiandroid.diagnostics -> {_module_path(diag_facade)}")
    ad_oi = importlib.import_module("analysis.diagnostics.output_inventory")
    ad_oap = importlib.import_module("analysis.diagnostics.output_artifact_policy")
    ad_flr = importlib.import_module("analysis.diagnostics.feature_lineage_report")
    if diag_facade.output_inventory is not ad_oi:
        print("FAIL: obsidiandroid.diagnostics.output_inventory facade mismatch", file=sys.stderr)
        return 1
    if diag_facade.output_artifact_policy is not ad_oap:
        print("FAIL: obsidiandroid.diagnostics.output_artifact_policy facade mismatch", file=sys.stderr)
        return 1
    if diag_facade.feature_lineage_report is not ad_flr:
        print("FAIL: obsidiandroid.diagnostics.feature_lineage_report facade mismatch", file=sys.stderr)
        return 1
    print("OK   obsidiandroid.diagnostics submodules match analysis.diagnostics")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
