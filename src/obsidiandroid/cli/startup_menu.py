"""Interactive startup menu for pipeline execution modes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Callable, Dict, List


from config import app_config
from obsidiandroid.common.repo_paths import repo_operator_script
from obsidiandroid.modeling import pipeline_core
from .ui import display as du
from .ui import menu as mu
import obsidiandroid.cli.profile_manager as profile_manager
from .menu.profile_preflight import resolve_and_validate_profile
from .menu import diagnostics_banners
from .menu import startup_menu_actions
from . import startup_menu_diagnostics as _diagnostics_menu
from . import startup_menu_research as _research_menu
from . import startup_menu_review as _review_menu

vendor_diagnostics = _diagnostics_menu.vendor_diagnostics

from .startup_menu_health import run_health_check as _run_health_check
from .startup_menu_run_context import (
    latest_run_context_status as _latest_run_context_status,
    latest_run_has_provenance as _latest_run_has_provenance,
    print_availability_block as _print_availability_block,
    print_startup_context as _print_startup_context,
    read_json_object as _read_json_object,
    read_latest_run_id as _read_latest_run_id,
    read_locked_publication_run_id as _read_locked_publication_run_id,
    read_run_summary as _read_run_summary,
    resolve_latest_manifest_payload as _resolve_latest_manifest_payload,
)

from .startup_menu_run_overview import (
    show_latest_run_snapshot as _show_latest_run_snapshot,
    show_profile_tuning_snapshot as _show_profile_tuning_snapshot,
    show_recent_runs_overview as _show_recent_runs_overview,
    show_session_and_output_details as _show_session_and_output_details,
)
from .startup_menu_structural import (
    print_structural_analysis_banner as _print_structural_analysis_banner,
    print_structural_result_card as _print_structural_result_card,
    prompt_structural_analysis_action as _prompt_structural_analysis_action,
    warn_if_no_latest_run_context as _warn_if_no_latest_run_context,
)

from .startup_menu_prompts import prompt_run_id as _prompt_run_id
from .startup_menu_warehouse_scripts import (
    run_backfill_results_warehouse as _run_backfill_results_warehouse,
    run_claim_artifact_map_scaffold as _run_claim_artifact_map_scaffold,
    run_evidence_lock_checker as _run_evidence_lock_checker,
    run_publication_structural_diagnostics as _run_publication_structural_diagnostics,
    run_results_warehouse_status as _run_results_warehouse_status,
    run_retrain_from_cached_alignment as _run_retrain_from_cached_alignment,
)



@dataclass(frozen=True)
class _MenuCommand:
    """Descriptor for one operator-facing menu command."""

    label: str
    action: Callable[[], int | None]

def _run_full_pipeline(profile_id: str) -> int:
    """Run the complete pipeline with configured model set."""
    from obsidiandroid.pipeline import run_pipeline

    return run_pipeline(profile_ref=profile_id)


def _run_full_pipeline_with_persistence_choice(profile_id: str) -> int:
    from obsidiandroid.pipeline import run_pipeline
    choice = mu.display_menu(
        ["Run with local files only", "Run with local files + Core database results"],
        title="Save analysis results", exit_label="Cancel run",
        action_hint="Type a row number. 0 = cancel run · Ctrl+C = cancel",
        breadcrumb="Run analysis › Full pipeline › Save results",
        context_lines=[
            ("PROFILE", profile_id),
            ("RUN", "Both choices run the full analysis, including configured model training."),
            ("OUTPUT", "Both save local reports and artifacts; only option 2 enables Core persistence."),
            ("SOURCE", "This choice does not change the profile cohort or Permission Intel source."),
        ],
    )
    if choice == 0:
        return 0
    if choice == 1:
        return _run_full_pipeline(profile_id)
    return run_pipeline(profile_ref=profile_id, analysis_persistence=True)


def _run_single_model(model_key: str, profile_id: str) -> int:
    """Run the full pipeline while training only one selected model."""
    from obsidiandroid.pipeline import run_pipeline

    return run_pipeline(selected_models=[model_key], profile_ref=profile_id)


def _run_vendor_only(profile_id: str) -> int:
    """Run pipeline through vendor metadata extraction and stop before ML."""
    from obsidiandroid.pipeline import run_pipeline

    return run_pipeline(stop_after="vendor_metadata", profile_ref=profile_id)


def _run_to_stage(profile_id: str) -> int:
    """Run pipeline and stop after a selected stage."""
    from obsidiandroid.pipeline import run_pipeline

    stage_map: Dict[str, str] = {
        "Samples only": "samples",
        "AV pipeline only": "av_pipeline",
        "Vendor metadata only": "vendor_metadata",
        "Engine weights only": "engine_weights",
        "Feature matrix only": "feature_matrix",
        "Alignment only": "alignment",
        "Training only": "training",
        "Ablation only": "ablation",
        "Permission trends only": "permission_trends",
        "Label resolution only": "label_resolution",
    }
    choice = mu.display_menu(
        list(stage_map.keys()),
        title="Pipeline cutoff stage",
        exit_label="Back",
        breadcrumb="Main menu › Run analysis › Stage stop",
    )
    if choice == 0:
        return 0
    stage_names = list(stage_map.keys())
    stage_key = stage_map[stage_names[choice - 1]]
    return run_pipeline(stop_after=stage_key, profile_ref=profile_id)


def _build_model_menu() -> Dict[str, str]:
    """Return model menu mapping."""
    return {
        model.replace("_", " ").title(): model
        for model in pipeline_core.ALL_SUPPORTED_MODELS
    }







def _run_quick_health_check() -> int:
    """Run quick health check for latest run."""
    return _run_health_check(run_id=None)


def _run_health_check_for_selected_run() -> int:
    """Prompt for a run ID and run health check for that run."""
    latest_run_id = _read_latest_run_id()
    selected = _prompt_run_id(default_run_id=latest_run_id)
    if not selected:
        du.print_warning("[MENU] Health check cancelled (no run_id provided).")
        return 1
    return _run_health_check(run_id=selected)


def _run_output_cleanup() -> int:
    """Run output cleanup in dry-run or apply mode."""
    return startup_menu_actions.run_output_cleanup()

def _show_within_cross_type_error_snapshot() -> int:
    """Show latest within-type vs cross-type error summary when available."""
    return startup_menu_actions.show_within_cross_type_error_snapshot()


def _show_model_comparison_snapshot() -> int:
    """Show latest model-comparison snapshot from diagnostics when available."""
    return startup_menu_actions.show_model_comparison_snapshot()


def _handle_confusion_matrix_export() -> int:
    """Handle confusion-matrix export with run context and clear guidance."""
    return startup_menu_actions.handle_confusion_matrix_export()


def _show_disk_usage_summary() -> int:
    """Show compact disk-usage summary for output workspace directories."""
    return startup_menu_actions.show_disk_usage_summary()


def _run_evidence_bundle_series_aggregator() -> int:
    """Aggregate strict reproducibility evidence bundles into a macro-F1 comparison table."""
    return _research_menu.run_evidence_bundle_series_aggregator(read_json_object=_read_json_object)




def _pipeline_run_mode_labels() -> list[str]:
    """Ordered labels for the primary pipeline launcher."""
    return [
        "Full analysis — configured models and reports",
        "Fast development — reduced analysis",
        "Smoke test — basic pipeline checks",
        "Train and evaluate one model",
        "Run through a selected stage",
        "Extract vendor features only",
        "Retrain using cached alignment",
    ]


def _launch_pipeline_actions_menu() -> int:
    """Display run actions and execute selected pipeline path."""
    while True:
        choice = mu.display_menu(
            _pipeline_run_mode_labels(),
            title="Pipeline run mode",
            exit_label="Back",
            breadcrumb="Main menu › Run analysis",
        )
        if choice == 0:
            return 0
        if choice == 1:
            profile_id = resolve_and_validate_profile(prefer_quick=False)
            if not profile_id:
                continue
            if _preview_classification(profile_id):
                return _run_full_pipeline_with_persistence_choice(profile_id)
            continue
        if choice == 2:
            if _preview_classification("dev_fast"):
                return _run_full_pipeline("dev_fast")
            continue
        if choice == 3:
            if _preview_classification("dev_smoke"):
                return _run_full_pipeline("dev_smoke")
            continue
        if choice == 4:
            profile_id = resolve_and_validate_profile(prefer_quick=False)
            if not profile_id:
                continue
            model_menu = _build_model_menu()
            model_choice = mu.display_menu(
                list(model_menu.keys()),
                title="Single model",
                exit_label="Back",
                breadcrumb="Main menu › Run analysis › Single model",
            )
            if model_choice == 0:
                continue
            model_names = list(model_menu.keys())
            model_key = model_menu[model_names[model_choice - 1]]
            if _preview_classification(profile_id):
                return _run_single_model(model_key, profile_id)
            continue
        if choice == 5:
            profile_id = resolve_and_validate_profile(prefer_quick=False)
            if not profile_id:
                continue
            if _preview_classification(profile_id):
                return _run_to_stage(profile_id)
            continue
        if choice == 6:
            profile_id = resolve_and_validate_profile(prefer_quick=False)
            if not profile_id:
                continue
            return _run_vendor_only(profile_id)
        if choice == 7:
            du.print_warning("Cached retraining uses the saved alignment population and evidence, not live explorer counts.")
            du.print_info("Source preflight: not established here; cache and training checks remain authoritative. This action trains models and writes result artifacts.")
            if mu.display_menu(["Run cached retraining with existing checks"], title="Cached retraining", exit_label="Cancel"):
                return _run_retrain_from_cached_alignment()
        du.print_warning("[MENU] Invalid choice received.")


def _launch_reuse_results_menu() -> None:
    """Display reuse actions for existing artifacts and warehouse tables."""
    while True:
        reuse = [
            "Backfill Results Warehouse from Existing Artifacts",
            "Check Results Warehouse Table Status",
        ]
        choice = mu.display_menu(
            reuse,
            title="Reuse existing results",
            exit_label="Back",
            breadcrumb="Main menu › Tools › Reuse",
        )
        if choice == 0:
            return
        if choice == 1:
            _run_backfill_results_warehouse()
            continue
        if choice == 2:
            _run_results_warehouse_status()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_structural_analysis_menu() -> None:
    """Display structural analysis and publication-figure workflows."""
    _warn_if_no_latest_run_context(area="Structural Analysis")
    show_context = True
    while True:
        context = _latest_run_context_status()
        has_latest_run = bool(context.get("has_latest_run", False))
        has_struct_bundle = bool(context.get("has_structural_bundle", False))
        has_publication_exports = bool(context.get("has_publication_exports", False))

        unavailable_reasons: dict[int, str] = {}
        if not has_latest_run:
            unavailable_reasons = {
                1: "no latest run",
                2: "no latest run",
                3: "no latest run",
                4: "no latest run",
                5: "no latest run",
            }
        elif not has_struct_bundle:
            unavailable_reasons[1] = "missing structural bundle"
            unavailable_reasons[2] = "missing structural bundle"
            unavailable_reasons[3] = "missing structural bundle"
            unavailable_reasons[4] = "missing structural bundle"
            unavailable_reasons[5] = "missing structural bundle"

        base_options: List[str] = [
            "Type-Level Analysis -> type heatmap + summary report",
            "Family-Level Analysis -> family visuals + diagnostics",
            "Banker-Specific Analysis -> banker trend artifacts",
            "Publication-Ready Exports -> presentation-ready figure set",
            "Export Structural Report -> full artifact pack",
        ]
        options: List[str] = []
        for idx, label in enumerate(base_options, start=1):
            reason = unavailable_reasons.get(idx, "").strip()
            if reason:
                options.append(f"{label} (Unavailable: {reason})")
            else:
                options.append(label)
        if show_context:
            _print_structural_analysis_banner()
            _print_availability_block(
                rows=[
                    ("Structural Bundle", "Yes" if has_struct_bundle else "No"),
                    ("Publication Exports", "Yes" if has_publication_exports else "No"),
                    (
                        "Locked Evidence Run",
                        "Yes" if bool(context.get("has_locked_publication_run", False)) else "No",
                    ),
                ]
            )
            show_context = False
        choice = _prompt_structural_analysis_action(options)
        if choice == "0":
            return
        if choice == "I":
            _print_structural_analysis_banner()
            continue
        selected_idx = int(choice)
        blocked_reason = unavailable_reasons.get(selected_idx, "").strip()
        if blocked_reason:
            du.print_warning(f"[MENU] Action unavailable: {blocked_reason}.")
            continue
        if choice == "1":
            setattr(app_config, "ANALYSIS_SCOPE", "type")
            result = _run_publication_structural_diagnostics()
            _print_structural_result_card(
                action="Type-Level Structural Analysis",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "2":
            setattr(app_config, "ANALYSIS_SCOPE", "family")
            result = _run_publication_structural_diagnostics()
            _print_structural_result_card(
                action="Family-Level Structural Analysis",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "3":
            setattr(app_config, "ANALYSIS_SCOPE", "banker")
            result = _run_publication_structural_diagnostics()
            _print_structural_result_card(
                action="Banker-Specific Structural Analysis",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "4":
            setattr(app_config, "EVIDENCE_MODE_ENABLED", True)
            setattr(app_config, "EVIDENCE_MODE_LOCKED_VALUE", True)
            setattr(app_config, "PAPER_MODE_ENABLED", True)
            setattr(app_config, "PAPER_MODE_LOCKED_VALUE", True)
            setattr(app_config, "FIGURE_MODE", "paper")
            result = _run_publication_structural_diagnostics()
            _print_structural_result_card(
                action="Publication-Ready Exports",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "5":
            setattr(app_config, "ANALYSIS_SCOPE", "all")
            if bool(getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", True))):
                setattr(app_config, "FIGURE_MODE", "paper")
            else:
                setattr(app_config, "FIGURE_MODE", "analysis")
            result = _run_publication_structural_diagnostics()
            _print_structural_result_card(
                action="Export Structural Report",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_model_evaluation_menu() -> None:
    """Display model evaluation and validation workflows."""
    _warn_if_no_latest_run_context(area="Model Evaluation")
    while True:
        context = _latest_run_context_status()
        has_latest_run = bool(context.get("has_latest_run", False))
        unavailable_reasons: dict[int, str] = {}
        if not has_latest_run:
            unavailable_reasons = {
                1: "no latest run",
                2: "no latest run",
                3: "no latest run",
            }

        base_options: List[str] = [
            "Within vs Cross-Type Errors",
            "Model Comparison",
            "Export Confusion Matrix",
        ]
        model_rows: List[str] = []
        for idx, label in enumerate(base_options, start=1):
            reason = unavailable_reasons.get(idx, "").strip()
            model_rows.append(f"{label} (Unavailable)" if reason else label)
        _print_availability_block(
            rows=[
                ("Latest Run", str(context.get("latest_run_id", "")) or "No"),
                ("Run-Scoped Provenance", "Yes" if _latest_run_has_provenance() else "No"),
            ]
        )
        choice = mu.display_menu(
            model_rows,
            title="Model evaluation",
            exit_label="Back",
            breadcrumb="Main menu › Research › Models",
        )
        if choice == 0:
            return
        blocked_reason = unavailable_reasons.get(int(choice), "").strip()
        if blocked_reason:
            du.print_warning(f"[MENU] Action unavailable: {blocked_reason}.")
            continue
        if choice == 1:
            _show_within_cross_type_error_snapshot()
            continue
        if choice == 2:
            _show_model_comparison_snapshot()
            continue
        if choice == 3:
            _handle_confusion_matrix_export()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _run_research_validity_review_menu() -> int:
    """Aggregate dataset/modality/skeptic diagnostics into one markdown+json review."""
    return _research_menu.run_research_validity_review_menu(read_latest_run_id=_read_latest_run_id)


def _launch_compare_runs_menu() -> None:
    """Run-to-run comparison without requiring evidence mode or experiment contracts."""
    _research_menu.launch_compare_runs_menu(
        read_latest_run_id=_read_latest_run_id,
        read_run_summary=_read_run_summary,
        read_json_object=_read_json_object,
    )


def _run_evidence_readiness_menu_action() -> int:
    """Explain evidence gates and write readiness summary under global diagnostics."""
    return _research_menu.run_evidence_readiness_menu_action(
        read_latest_run_id=_read_latest_run_id,
        read_locked_publication_run_id=_read_locked_publication_run_id,
        run_evidence_lock_checker=_run_evidence_lock_checker,
    )


def _launch_reproducibility_menu() -> None:
    """Reproducibility, research validity, run comparison, and evidence readiness."""
    _research_menu.launch_reproducibility_menu(
        read_latest_run_id=_read_latest_run_id,
        read_locked_publication_run_id=_read_locked_publication_run_id,
        read_run_summary=_read_run_summary,
        read_json_object=_read_json_object,
        run_health_check_for_selected_run=_run_health_check_for_selected_run,
        run_research_validity_review_action=_run_research_validity_review_menu,
        launch_evidence_readiness_hub_action=_launch_evidence_readiness_hub,
    )


def _launch_evidence_readiness_hub() -> None:
    """Evidence readiness exports, cohort lock checks, and bundle aggregation."""
    _research_menu.launch_evidence_readiness_hub(
        run_evidence_readiness_action=_run_evidence_readiness_menu_action,
        run_evidence_lock_checker=_run_evidence_lock_checker,
        run_evidence_bundle_series_aggregator_action=_run_evidence_bundle_series_aggregator,
    )


def _run_family_label_taxonomy_audit_script() -> int:
    """Invoke scripts/family_label_taxonomy_audit.py for cohort taxonomy audit."""
    return _diagnostics_menu.run_family_label_taxonomy_audit_script(
        read_latest_run_id=_read_latest_run_id,
        resolve_latest_manifest_payload=_resolve_latest_manifest_payload,
        resolve_and_validate_profile=resolve_and_validate_profile,
        load_profile=profile_manager.load_profile,
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _run_android_missing_resolution_triage_script() -> int:
    """Invoke the Android missing-resolution triage diagnostics script."""
    return _diagnostics_menu.run_android_missing_resolution_triage_script(
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _run_vt_false_positive_review_triage_script() -> int:
    """Invoke the suppression-aware VT false-positive triage diagnostics script."""
    return _diagnostics_menu.run_vt_false_positive_review_triage_script(
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _run_policy_held_token_risk_script() -> int:
    """Invoke the policy-held token-risk diagnostics script."""
    return _diagnostics_menu.run_policy_held_token_risk_script(
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _run_backlog_debt_operator_summary_script() -> int:
    """Invoke the consolidated backlog/debt operator summary script."""
    return _diagnostics_menu.run_backlog_debt_operator_summary_script(
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _run_blank_resolved_family_triage_script() -> int:
    """Invoke the blank-resolved family triage diagnostics script."""
    return _diagnostics_menu.run_blank_resolved_family_triage_script(
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _run_profile_family_mapping_debt_script() -> int:
    """Invoke the profile family-mapping debt diagnostics script."""
    return _diagnostics_menu.run_profile_family_mapping_debt_script(
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _run_missing_primary_label_triage_script() -> int:
    """Invoke the missing-primary label triage diagnostics script."""
    return _diagnostics_menu.run_missing_primary_label_triage_script(
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _run_vendor_verdict_debt_script() -> int:
    """Invoke the vendor verdict debt diagnostics script."""
    return _diagnostics_menu.run_vendor_verdict_debt_script(
        operator_script_resolver=repo_operator_script,
        subprocess_run=subprocess.run,
    )


def _assess_backlog_triage_health() -> dict[str, object]:
    """Assess backlog triage export freshness against live debt signals."""
    from obsidiandroid.common.backlog_semantics import (
        assess_backlog_triage_health,
        read_android_missing_resolution_snapshot,
        read_blank_resolved_triage_snapshot,
        read_false_positive_triage_snapshot,
        read_missing_primary_triage_snapshot,
        read_policy_held_token_risk_snapshot,
        read_profile_family_mapping_debt_snapshot,
    )
    from obsidiandroid.common.output_paths import output_root as canonical_output_root
    from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot

    output_root = canonical_output_root()
    try:
        readiness = get_cohort_readiness_snapshot()
    except Exception:
        readiness = {"taxonomy_signals": {}}
    return assess_backlog_triage_health(
        readiness=readiness,
        android_missing_triage=read_android_missing_resolution_snapshot(output_root=output_root),
        fp_triage=read_false_positive_triage_snapshot(output_root=output_root),
        missing_primary_triage=read_missing_primary_triage_snapshot(output_root=output_root),
        policy_held_triage=read_policy_held_token_risk_snapshot(output_root=output_root),
        profile_mapping_debt=read_profile_family_mapping_debt_snapshot(output_root=output_root),
        blank_resolved_triage=read_blank_resolved_triage_snapshot(output_root=output_root),
    )


def _refresh_backlog_triage_exports() -> int:
    """Refresh backlog triage exports in one operator action."""
    return _diagnostics_menu.refresh_backlog_triage_exports(
        run_android_missing_resolution_triage_action=_run_android_missing_resolution_triage_script,
        run_vt_false_positive_review_triage_action=_run_vt_false_positive_review_triage_script,
        run_policy_held_token_risk_action=_run_policy_held_token_risk_script,
        run_missing_primary_label_triage_action=_run_missing_primary_label_triage_script,
        run_profile_family_mapping_debt_action=_run_profile_family_mapping_debt_script,
        run_blank_resolved_family_triage_action=_run_blank_resolved_family_triage_script,
        run_backlog_debt_operator_summary_action=_run_backlog_debt_operator_summary_script,
    )


def _refresh_stale_backlog_triage_exports() -> int:
    """Refresh only stale or mismatched backlog triage exports."""
    return _diagnostics_menu.refresh_stale_backlog_triage_exports(
        assess_backlog_triage_health_action=_assess_backlog_triage_health,
        run_android_missing_resolution_triage_action=_run_android_missing_resolution_triage_script,
        run_vt_false_positive_review_triage_action=_run_vt_false_positive_review_triage_script,
        run_policy_held_token_risk_action=_run_policy_held_token_risk_script,
        run_missing_primary_label_triage_action=_run_missing_primary_label_triage_script,
        run_profile_family_mapping_debt_action=_run_profile_family_mapping_debt_script,
        run_blank_resolved_family_triage_action=_run_blank_resolved_family_triage_script,
        run_backlog_debt_operator_summary_action=_run_backlog_debt_operator_summary_script,
    )


def _open_run_science_index() -> int:
    """Print the authoritative run science index path for the latest run."""
    return _diagnostics_menu.open_run_science_index(read_latest_run_id=_read_latest_run_id)


def _launch_cohort_family_audit_menu() -> None:
    """Family taxonomy, support thresholds, cohort distributions."""
    _diagnostics_menu.launch_cohort_family_audit_menu(
        read_latest_run_id=_read_latest_run_id,
        open_run_science_index_action=_open_run_science_index,
        run_family_label_taxonomy_audit_action=_run_family_label_taxonomy_audit_script,
    )


def _launch_parser_vendor_coverage_menu() -> None:
    """Parser coverage, vendor diagnostics, AV engine scoring from DB."""
    _diagnostics_menu.launch_parser_vendor_coverage_menu()


def _launch_permission_intelligence_coverage_menu() -> None:
    """Permission modality coverage pointers (reads latest run diagnostics)."""
    _diagnostics_menu.launch_permission_intelligence_coverage_menu(
        read_latest_run_id=_read_latest_run_id
    )


def _launch_feature_matrix_modality_menu() -> None:
    """Feature contract / modality / ablation pointers."""
    _diagnostics_menu.launch_feature_matrix_modality_menu(read_latest_run_id=_read_latest_run_id)


def _launch_taxonomy_consistency_review_menu() -> None:
    """Taxonomy consistency summary and mismatch exports."""
    _diagnostics_menu.launch_taxonomy_consistency_review_menu(read_latest_run_id=_read_latest_run_id)


def _launch_family_type_authority_coverage_menu() -> int:
    """Family/type authority coverage from the live Erebus authority view."""
    return _diagnostics_menu.launch_family_type_authority_coverage_menu()


def _launch_data_diagnostics_menu() -> None:
    """Data quality: cohort, parsers, permissions, features, taxonomy, structural exports."""
    _diagnostics_menu.launch_data_diagnostics_menu(
        read_latest_run_id=_read_latest_run_id,
        show_profile_tuning_snapshot=_show_profile_tuning_snapshot,
        open_run_science_index_action=_open_run_science_index,
        launch_family_type_authority_coverage_action=_launch_family_type_authority_coverage_menu,
        launch_taxonomy_consistency_review_action=_launch_taxonomy_consistency_review_menu,
        launch_parser_vendor_coverage_action=_launch_parser_vendor_coverage_menu,
        launch_permission_intelligence_coverage_action=_launch_permission_intelligence_coverage_menu,
        launch_feature_matrix_modality_action=_launch_feature_matrix_modality_menu,
        launch_cohort_family_audit_action=_launch_cohort_family_audit_menu,
        refresh_backlog_triage_exports_action=_refresh_backlog_triage_exports,
        launch_android_missing_resolution_triage_action=_run_android_missing_resolution_triage_script,
        launch_vt_false_positive_review_triage_action=_run_vt_false_positive_review_triage_script,
        launch_missing_primary_label_triage_action=_run_missing_primary_label_triage_script,
        launch_blank_resolved_family_triage_action=_run_blank_resolved_family_triage_script,
        launch_policy_held_token_risk_action=_run_policy_held_token_risk_script,
        launch_profile_family_mapping_debt_action=_run_profile_family_mapping_debt_script,
        launch_vendor_verdict_debt_action=_run_vendor_verdict_debt_script,
    )


def _launch_review_latest_run_menu() -> None:
    """Primary operator decision flow for the latest run."""
    from obsidiandroid.cli.analysis import review_native_runs
    if review_native_runs(latest=True):
        return
    _review_menu.launch_review_latest_run_menu(
        read_latest_run_id=_read_latest_run_id,
        open_run_science_index_action=_open_run_science_index,
        launch_cohort_family_audit_action=_launch_cohort_family_audit_menu,
        launch_parser_vendor_coverage_action=_launch_parser_vendor_coverage_menu,
        launch_permission_intelligence_coverage_action=_launch_permission_intelligence_coverage_menu,
        launch_feature_matrix_modality_action=_launch_feature_matrix_modality_menu,
        launch_taxonomy_consistency_review_action=_launch_taxonomy_consistency_review_menu,
        launch_run_overview_action=_launch_run_overview_menu,
        launch_compare_runs_action=_launch_compare_runs_menu,
        launch_data_diagnostics_action=_launch_data_diagnostics_menu,
        launch_reproducibility_action=_launch_reproducibility_menu,
        refresh_stale_backlog_triage_exports_action=_refresh_stale_backlog_triage_exports,
    )


def _show_research_report_key_artifact_paths() -> None:
    """Consolidated paths: index/Q1–Q3/validity audits for the latest run."""
    _research_menu.show_research_report_key_artifact_paths(read_latest_run_id=_read_latest_run_id)


def _show_cache_pointer_guidance() -> None:
    """Explain latest pointers and where manifests live."""
    du.print_section("Cache / latest pointers")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    du.print_stat("run_manifest.latest.json", str((output_root / "diagnostics" / "run_manifest.latest.json").resolve()))
    du.print_stat("promoted latest_run.txt", str((output_root / "promoted" / "latest_run.txt").resolve()))
    print("[RUN] Canonical manifests: obsidiandroid/output/runs/<run_id>/run_manifest.json")
    print("")


def _show_repair_migration_info() -> None:
    """Point operators at migration/repair entrypoints (no destructive actions here)."""
    du.print_section("Repair / migration helpers")
    print("[ACTION] Targeted repair scripts: obsidiandroid/scripts/ (see docs/STRUCTURE_MIGRATION_PLAN.md)")
    print("[ACTION] Profile-validated reruns: Run Analysis menu")
    print("")


def _launch_developer_utilities_menu() -> None:
    """Lightweight developer reminders (non-interactive CI stays on the CLI)."""
    while True:
        opts = [
            "Print suggested CI command (make ci)",
            "Import / package surface check (info)",
        ]
        choice = mu.display_menu(
            opts,
            title="Developer utilities",
            exit_label="Back",
            breadcrumb="Main menu › Tools › Developer",
        )
        if choice == 0:
            return
        if choice == 1:
            print("[ACTION] CI check: make ci")
            continue
        if choice == 2:
            print("[ACTION] Import surface check: python scripts/dev/check_import_surface.py")
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_run_overview_menu() -> None:
    """Display run overview and snapshot workflows."""
    while True:
        run_status = [
            "Current Run Summary",
            "Recent Run History",
            "Session and Output Details",
            "Full Run Folder History (Advanced)",
        ]
        choice = mu.display_menu(
            run_status,
            title="Run status and history",
            exit_label="Back",
            breadcrumb="Main menu › Run status",
        )
        if choice == 0:
            return
        if choice == 1:
            from obsidiandroid.cli.analysis import review_native_runs
            if not review_native_runs(latest=True):
                _show_latest_run_snapshot()
            continue
        if choice == 2:
            from obsidiandroid.cli.analysis import review_native_runs
            if not review_native_runs():
                _show_recent_runs_overview()
            continue
        if choice == 3:
            _show_session_and_output_details()
            continue
        if choice == 4:
            _show_recent_runs_overview(include_noncanonical=True)
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_research_reports_menu() -> None:
    """Interpretation artifacts: figures, models, evidence index, claims."""
    _research_menu.launch_research_reports_menu(
        launch_structural_analysis_menu=_launch_structural_analysis_menu,
        launch_model_evaluation_menu=_launch_model_evaluation_menu,
        show_research_report_key_artifact_paths_action=_show_research_report_key_artifact_paths,
        run_claim_artifact_map_scaffold=_run_claim_artifact_map_scaffold,
    )


def _launch_operations_menu() -> None:
    """Operational maintenance: outputs, reuse, cleanup, pointers — not research diagnostics."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    locked = _read_locked_publication_run_id()
    while True:
        diagnostics_banners.print_tools_maintenance_banner(
            output_root=output_root,
            latest_run_id=_read_latest_run_id(),
            locked_run_id=locked,
        )
        operations = [
            "Smart Output Cleanup",
            "Show Disk Usage Summary",
            "Reuse Existing Results",
            "Cache / latest pointer (guidance)",
            "Repair / migration helpers (info)",
            "Developer utilities",
            "Clear screen",
        ]
        choice = mu.display_menu(
            operations,
            title="Tools and maintenance",
            exit_label="Back",
            breadcrumb="Main menu › Tools",
        )
        if choice == 0:
            return
        if choice == 1:
            _run_output_cleanup()
            continue
        if choice == 2:
            _show_disk_usage_summary()
            continue
        if choice == 3:
            _launch_reuse_results_menu()
            continue
        if choice == 4:
            _show_cache_pointer_guidance()
            continue
        if choice == 5:
            _show_repair_migration_info()
            continue
        if choice == 6:
            _launch_developer_utilities_menu()
            continue
        if choice == 7:
            du.clear_console()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_explorer_menu() -> int:
    from .data_explorer import launch_data_explorer
    return launch_data_explorer()


def _group_menu(title, commands):
    while True:
        choice = mu.display_menu([c.label for c in commands], title=title, exit_label="Back")
        if choice == 0:
            return 0
        result = commands[choice - 1].action()
        if isinstance(result, int) and result:
            du.print_warning(f"Action ended with status {result}; see diagnostics.")


def _launch_results_menu():
    return _group_menu("Saved results and run history", [
        _MenuCommand("Review latest saved run", _launch_review_latest_run_menu),
        _MenuCommand("Run status and history", _launch_run_overview_menu),
        _MenuCommand("Research reports", _launch_research_reports_menu),
    ])


def _launch_checks_menu():
    return _group_menu("Research checks and diagnostics", [
        _MenuCommand("Data diagnostics", _launch_data_diagnostics_menu),
        _MenuCommand("Reproducibility and research validity", _launch_reproducibility_menu),
    ])


def _preview_classification(profile_id):
    """Require fresh source checks and an explicit choice in advanced run modes."""
    from . import profile_manager
    from .classification_overview import show_experiment, check_readiness, show_readiness, can_start
    profile = profile_manager.load_profile(profile_id)
    show_experiment(profile)
    checks = check_readiness(profile)
    show_readiness(checks)
    if not can_start(checks):
        return False
    return mu.confirm_prompt("Continue with this execution mode and its output effects? [y/N]")


def _launch_comparison_menu():
    """Expose existing multi-model and feature-ablation profiles without running them."""
    from .classification_overview import launch_experiment
    profiles = (
        "android_malware_major_families",
        "android_malware_type_taxonomy",
        "dev_ablation_fast",
    )
    while True:
        choice = mu.display_menu([
            "Compare configured models — major families",
            "Compare configured models — malware types",
            "Compare feature sets — development ablations (Random Forest)",
        ], title="Compare models and features", exit_label="Back",
            subtitle="Existing profiles; feature and evidence requirements still apply.",
            action_hint="", selection_prompt="Enter your selection: ")
        if choice == 0:
            return 0
        launch_experiment(profiles[choice - 1],
                          start_analysis=_run_full_pipeline_with_persistence_choice)


def _launch_classification_menu():
    from .classification_overview import launch_experiment
    while True:
        choice = mu.display_menu([
            "Malware-family classification",
            "Malware-type classification",
            "Compare models and features",
            "Other experiments and tests",
        ], title="Run malware classification", exit_label="Back to Main Menu",
            subtitle="Select an analysis. Training starts only after explicit confirmation.",
            action_hint="", selection_prompt="Enter your selection: ")
        if choice == 0:
            return 0
        if choice == 3:
            _launch_comparison_menu()
            continue
        if choice == 4:
            _launch_pipeline_actions_menu()
            continue
        profile_id = ("android_malware_major_families" if choice == 1
                      else "android_malware_type_taxonomy")
        launch_experiment(profile_id, start_analysis=_run_full_pipeline_with_persistence_choice)


def _build_main_menu_commands() -> list[_MenuCommand]:
    """Everyday browsing is independent of training and saved run operations."""
    return [
        _MenuCommand("Explore Android data", _launch_explorer_menu),
        _MenuCommand("Run malware classification", _launch_classification_menu),
        _MenuCommand("Review results and run history", _launch_results_menu),
        _MenuCommand("Research checks and diagnostics", _launch_checks_menu),
        _MenuCommand("Tools and maintenance", _launch_operations_menu),
    ]


def launch_startup_menu() -> int:
    """Run interactive startup menu loop."""
    _print_startup_context()

    while True:
        commands = _build_main_menu_commands()
        choice = mu.display_menu(
            [c.label for c in commands],
            title="Main menu",
            exit_label="Exit App",
            action_hint="",
            breadcrumb="ObsidianDroid · operator console",
        )

        if choice == 0:
            du.print_info("[MENU] Exit requested.")
            return 0

        selected = commands[choice - 1]
        result = selected.action()
        if isinstance(result, int) and result != 0:
            return result
        continue


def _parse_args(argv: list[str]) -> None:
    """Validate startup-menu arguments before any interactive work begins."""
    parser = argparse.ArgumentParser(
        prog="obsidiandroid",
        description="Launch the interactive ObsidianDroid operator console.",
    )
    parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Module CLI entrypoint."""
    _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return launch_startup_menu()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Interrupted by user (Ctrl+C). Exiting.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
