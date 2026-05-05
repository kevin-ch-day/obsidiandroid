"""Lightweight checks for new ``obsidiandroid.*`` package surfaces (no slow integration)."""

from __future__ import annotations

import pytest


def test_pipeline_facade_matches_runner_public_surface() -> None:
    """``obsidiandroid.pipeline`` delegates to live ``runner`` bindings (PEP 562 __getattr__)."""
    from analysis.pipeline import runner as runner_mod
    import obsidiandroid.pipeline as facade

    assert facade.run_pipeline is runner_mod.run_pipeline
    assert facade.DIAGNOSTICS_DIR is runner_mod.DIAGNOSTICS_DIR
    assert facade.PIPELINE_MAIN_LOGGER is runner_mod.PIPELINE_MAIN_LOGGER
    assert facade.PARSER_QUALITY_PATH is runner_mod.PARSER_QUALITY_PATH


def test_output_cleanup_clutter_shim_matches_canonical() -> None:
    """``utils.output_cleanup_clutter`` delegates to ``obsidiandroid.common``."""
    from obsidiandroid.common import output_cleanup_clutter as canon
    from utils import output_cleanup_clutter as shim

    assert shim.WORKBOOK_CORRUPT_GLOB == canon.WORKBOOK_CORRUPT_GLOB
    assert shim.PAPER_BUNDLE_SMOKE_GLOBS == canon.PAPER_BUNDLE_SMOKE_GLOBS


def test_output_paths_shim_matches_canonical() -> None:
    """``utils.output_paths`` re-exports :mod:`obsidiandroid.common.output_paths`."""
    from obsidiandroid.common import output_paths as canon
    from utils import output_paths as shim

    assert shim.output_root is canon.output_root
    assert shim.ensure_output_layout is canon.ensure_output_layout


def test_sample_metadata_preprocessor_shim_matches_canonical() -> None:
    """``utils.sample_metadata_preprocessor`` delegates to ``obsidiandroid.common``."""
    import obsidiandroid.common.sample_metadata_preprocessor as canon
    from utils import sample_metadata_preprocessor as shim

    assert shim.prepare_sample_dataframe is canon.prepare_sample_dataframe


def test_compliance_shim_matches_canonical() -> None:
    """``utils.compliance`` delegates to ``obsidiandroid.governance.compliance``."""
    import obsidiandroid.governance.compliance as canon
    from utils import compliance as shim

    assert shim.build_compliance_report is canon.build_compliance_report


def test_run_manifest_shim_matches_canonical() -> None:
    """``utils.run_manifest`` re-exports governance canonical module."""
    import obsidiandroid.governance.run_manifest as canon
    from utils import run_manifest as shim

    assert shim.generate_run_id is canon.generate_run_id
    assert shim.MANIFEST_SCHEMA_VERSION == canon.MANIFEST_SCHEMA_VERSION


def test_artifacts_shim_matches_canonical() -> None:
    """``utils.artifacts`` re-exports governance canonical module."""
    import obsidiandroid.governance.artifacts as canon
    from utils import artifacts as shim

    assert shim.ManifestWriter is canon.ManifestWriter
    assert shim.ArtifactKey.SPLIT_AUDIT_CSV == canon.ArtifactKey.SPLIT_AUDIT_CSV


def test_cohort_reproducibility_shim_matches_canonical() -> None:
    """``utils.cohort_reproducibility`` re-exports governance canonical module."""
    import obsidiandroid.governance.cohort_reproducibility as canon
    from utils import cohort_reproducibility as shim

    assert shim.apply_analysis_snapshot_lock is canon.apply_analysis_snapshot_lock
    assert shim.export_analysis_snapshot is canon.export_analysis_snapshot


def test_cohort_readiness_report_shim_matches_canonical() -> None:
    """``utils.cohort_readiness_report`` re-exports governance canonical module."""
    import obsidiandroid.governance.cohort_readiness_report as canon
    from utils import cohort_readiness_report as shim

    assert shim.print_cohort_readiness_report is canon.print_cohort_readiness_report
    assert shim.print_cohort_sql_scope_gate_summary is canon.print_cohort_sql_scope_gate_summary


def test_profile_manager_shim_matches_canonical() -> None:
    """``utils.profile_manager`` re-exports :mod:`obsidiandroid.cli.profile_manager`."""
    import obsidiandroid.cli.profile_manager as canon
    from utils import profile_manager as shim

    assert shim.load_profile is canon.load_profile
    assert shim.list_profiles is canon.list_profiles


def test_display_utils_shim_matches_canonical_display() -> None:
    """``utils.display_utils`` re-exports :mod:`obsidiandroid.cli.ui.display`."""
    from obsidiandroid.cli.ui import display as canon
    from utils import display_utils as shim

    assert shim.print_subheader is canon.print_subheader
    assert shim.print_table is canon.print_table


def test_ml_console_shim_matches_canonical() -> None:
    """``utils.ml_console`` re-exports :mod:`obsidiandroid.common.ml_console`."""
    import obsidiandroid.common.ml_console as canon
    from utils import ml_console as shim

    assert shim.is_minimal is canon.is_minimal
    assert shim.get_mode is canon.get_mode


def test_family_distribution_report_shim_matches_canonical() -> None:
    """``utils.family_distribution_report`` delegates to ``obsidiandroid.reporting``."""
    import obsidiandroid.reporting.family_distribution_report as canon
    from utils import family_distribution_report as shim

    assert shim.print_family_distribution_stats is canon.print_family_distribution_stats


def test_latex_tables_shim_matches_canonical() -> None:
    """``utils.latex_tables`` delegates to ``obsidiandroid.reporting.latex_tables``."""
    import obsidiandroid.reporting.latex_tables as canon
    from utils import latex_tables as shim

    assert shim.LatexTableSpec is canon.LatexTableSpec
    assert shim.render_tabular is canon.render_tabular


def test_av_detection_tiers_shim_matches_canonical() -> None:
    """``utils.av_detection_tiers`` delegates to ``obsidiandroid.common``."""
    from obsidiandroid.common import av_detection_tiers as canon
    from utils import av_detection_tiers as shim

    assert shim.get_detection_tier is canon.get_detection_tier
    assert shim.DETECTION_TIERS == canon.DETECTION_TIERS


def test_export_vendor_raw_shim_matches_canonical() -> None:
    """``utils.exporting.vendor_raw`` delegates to ``obsidiandroid.common.export_vendor_raw``."""
    from obsidiandroid.common import export_vendor_raw as canon
    from utils.exporting import vendor_raw as shim

    assert shim.is_parquet_supported is canon.is_parquet_supported
    assert shim.export_vendor_raw_artifacts is canon.export_vendor_raw_artifacts


def test_confusion_matrix_exporter_shim_matches_canonical() -> None:
    """``utils.confusion_matrix_exporter`` delegates to ``obsidiandroid.reporting``."""
    import obsidiandroid.reporting.confusion_matrix_exporter as canon
    from utils import confusion_matrix_exporter as shim

    assert shim.export_confusion_matrix_image is canon.export_confusion_matrix_image


def test_export_manager_shim_matches_canonical() -> None:
    """``utils.export_manager`` aliases the canonical reporting module (same module object)."""
    import obsidiandroid.reporting.export_manager as canon
    from utils import export_manager as shim

    assert shim is canon
    assert shim.export_dataframe_to_excel is canon.export_dataframe_to_excel


def test_model_exporter_shim_matches_canonical() -> None:
    """``utils.model_exporter`` re-exports :mod:`obsidiandroid.modeling.model_exporter`."""
    import obsidiandroid.modeling.model_exporter as canon
    from utils import model_exporter as shim

    assert shim.export_model_to_file is canon.export_model_to_file


def test_output_hygiene_shim_matches_canonical() -> None:
    """``utils.output_hygiene`` re-exports :mod:`obsidiandroid.common.output_hygiene`."""
    import obsidiandroid.common.output_hygiene as canon
    from utils import output_hygiene as shim

    assert shim.resolve_stable_output_root_for_mirrors is canon.resolve_stable_output_root_for_mirrors
    assert shim.mirror_csv_text_run_then_global is canon.mirror_csv_text_run_then_global


def test_export_workbook_shim_matches_canonical() -> None:
    """``utils.exporting.workbook`` delegates to ``obsidiandroid.common.export_workbook``."""
    from obsidiandroid.common import export_workbook as canon
    from utils.exporting import workbook as shim

    assert shim.WorkbookLock is canon.WorkbookLock
    assert shim.write_sheet is canon.write_sheet


def test_export_naming_shim_matches_canonical() -> None:
    """``utils.exporting.naming`` delegates to ``obsidiandroid.common.export_naming``."""
    from obsidiandroid.common import export_naming as canon
    from utils.exporting import naming as shim

    assert shim.safe_sheet_name is canon.safe_sheet_name
    assert shim.alias_for_entry is canon.alias_for_entry


def test_prompt_utils_shim_matches_canonical() -> None:
    """``utils.prompt_utils`` delegates to ``obsidiandroid.cli.prompt_utils``."""
    from obsidiandroid.cli import prompt_utils as canon
    from utils import prompt_utils as shim

    assert shim.prompt_yes_no is canon.prompt_yes_no
    assert shim.print_warning is canon.print_warning


def test_observability_package_reexports_logging() -> None:
    """``obsidiandroid.observability`` re-exports ``get_logger`` / ``log_event``."""
    import obsidiandroid.observability as obs
    import obsidiandroid.observability.logging as olog

    assert obs.get_logger is olog.get_logger
    assert obs.log_event is olog.log_event


def test_logging_package_shim_matches_canonical() -> None:
    """``utils.logging`` re-exports ``get_logger`` / ``log_event`` from observability."""
    import obsidiandroid.observability.logging as canon
    from utils import logging as shim

    assert shim.get_logger is canon.get_logger
    assert shim.log_event is canon.log_event


def test_logging_logger_module_shim_matches_canonical() -> None:
    """``utils.logging.logger`` delegates to ``obsidiandroid.observability.logging.logger``."""
    import obsidiandroid.observability.logging.logger as canon
    from utils.logging import logger as shim

    assert shim.get_logger is canon.get_logger
    assert shim.close_all_loggers is canon.close_all_loggers


def test_logging_runtime_module_shim_matches_canonical() -> None:
    """``utils.logging.runtime`` delegates to ``obsidiandroid.observability.logging.runtime``."""
    import obsidiandroid.observability.logging.runtime as canon
    from utils.logging import runtime as shim

    assert shim.start_runtime_logging is canon.start_runtime_logging
    assert shim.stop_runtime_logging is canon.stop_runtime_logging


def test_thin_compat_shim_trees_follow_policy() -> None:
    """Legacy shim dirs stay star-import / bootstrap only (see check_import_surface)."""
    from pathlib import Path

    from scripts.dev.check_import_surface import collect_thin_compat_shim_violations

    repo_root = Path(__file__).resolve().parents[1]
    errs = collect_thin_compat_shim_violations(repo_root)
    assert errs == [], "thin compat shim violations:\n" + "\n".join(errs)


def test_python_sources_have_no_utf8_bom_prefix() -> None:
    """BOM-prefixed ``*.py`` files break ast.parse and CI shim checks (see check_import_surface)."""
    from pathlib import Path

    from scripts.dev.check_import_surface import collect_utf8_bom_python_sources

    repo_root = Path(__file__).resolve().parents[1]
    bad = collect_utf8_bom_python_sources(repo_root)
    assert not bad, "UTF-8 BOM at start of:\n" + "\n".join(bad)


def test_diagnostics_facade_modules_match_analysis_diagnostics() -> None:
    """``obsidiandroid.diagnostics`` re-exports the same module objects as ``analysis.diagnostics``."""
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
