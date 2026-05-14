"""Interactive startup menu for pipeline execution modes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Callable, Dict, List

import pandas as pd

from config import app_config
from obsidiandroid.evaluation import engine_scoring_summary
from obsidiandroid.modeling import pipeline_core
from .ui import display as du
from .ui import menu as mu
from .menu.profile_preflight import resolve_and_validate_profile
from .menu.vendor_diagnostics import (
    print_compact_vendor_coverage_snapshot,
    run_single_vendor_parser_check,
    validate_parser_columns_from_latest_export,
)
from .menu import diagnostics_banners
from .menu import startup_menu_actions
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.repo_paths import repo_operator_script
from obsidiandroid.diagnostics import reproducibility_workbench as repro_workbench

from .startup_menu_health import run_health_check as _run_health_check
from .startup_menu_run_context import (
    candidate_sort_key as _candidate_sort_key,
    discover_latest_run_id_from_runs as _discover_latest_run_id_from_runs,
    format_run_status_display as _format_run_status_display,
    format_stage_label as _format_stage_label,
    has_structural_bundle as _has_structural_bundle,
    latest_run_context_status as _latest_run_context_status,
    latest_run_has_provenance as _latest_run_has_provenance,
    latest_run_paper_mode_enabled as _latest_run_paper_mode_enabled,
    paper_exports_available as _paper_exports_available,
    parse_run_timestamp_from_id as _parse_run_timestamp_from_id,
    parse_run_timestamp_from_manifest as _parse_run_timestamp_from_manifest,
    print_availability_block as _print_availability_block,
    print_startup_context as _print_startup_context,
    read_json_object as _read_json_object,
    read_latest_run_id as _read_latest_run_id,
    read_latest_run_manifest as _read_latest_run_manifest,
    read_locked_paper_run_id as _read_locked_paper_run_id,
    read_run_progress_summary as _read_run_progress_summary,
    read_run_summary as _read_run_summary,
    read_top_model_snapshot as _read_top_model_snapshot,
    resolve_latest_manifest_payload as _resolve_latest_manifest_payload,
    resolve_manifest_for_run_id as _resolve_manifest_for_run_id,
    resolve_pipeline_timings_path as _resolve_pipeline_timings_path,
    resolve_run_root_for_manifest as _resolve_run_root_for_manifest,
    status_text as _status_text,
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
    run_paper2_freeze_checker as _run_paper2_freeze_checker,
    run_paper_structural_diagnostics as _run_paper_structural_diagnostics,
    run_results_warehouse_status as _run_results_warehouse_status,
    run_retrain_from_cached_alignment as _run_retrain_from_cached_alignment,
)



@dataclass(frozen=True)
class _MenuCommand:
    """Descriptor for one operator-facing menu command."""

    label: str
    action: Callable[[], int | None]


def _first_existing_path(candidates: list[Path]) -> Path | None:
    """Return the first path that exists as a regular file, or ``None``."""
    for path in candidates:
        if path.is_file():
            return path
    return None


def _governed_cohort_n_for_q2(*, rdiag: Path, gdiag: Path, q2: Dict) -> int | None:
    """Resolve governed-cohort denominator for Q2 display (payload, Q1 JSON, or infer)."""
    from obsidiandroid.common.json_io import read_json_dict

    def _as_nonneg_int(val: object) -> int | None:
        if isinstance(val, bool):
            return None
        if isinstance(val, int) and val >= 0:
            return val
        if isinstance(val, float) and val >= 0 and val == int(val):
            return int(val)
        return None

    n = _as_nonneg_int(q2.get("governed_cohort_n"))
    if n is not None:
        return n
    q1 = read_json_dict(rdiag / "dataset_foundation_summary.json") or read_json_dict(
        gdiag / "dataset_foundation_summary.json"
    )
    gs = q1.get("governed_samples") if isinstance(q1, dict) else None
    n = _as_nonneg_int(gs)
    if n is not None:
        return n
    try:
        pn = int(q2.get("permission_signal_n") or 0)
        pp = float(q2.get("permission_signal_pct") or 0)
    except (TypeError, ValueError):
        return None
    if pn > 0 and pp > 0:
        return int(round(pn * 100.0 / pp))
    return None


def _run_full_pipeline(profile_id: str) -> int:
    """Run the complete pipeline with configured model set."""
    from main import run_pipeline

    return run_pipeline(profile_ref=profile_id)


def _run_single_model(model_key: str, profile_id: str) -> int:
    """Run the full pipeline while training only one selected model."""
    from main import run_pipeline

    return run_pipeline(selected_models=[model_key], profile_ref=profile_id)


def _run_vendor_only(profile_id: str) -> int:
    """Run pipeline through vendor metadata extraction and stop before ML."""
    from main import run_pipeline

    return run_pipeline(stop_after="vendor_metadata", profile_ref=profile_id)


def _run_engine_summary_only() -> int:
    """Generate engine scoring summary directly from DB and print top rows."""
    du.print_section("Engine Scoring Summary (DB Only)")
    summary_df = engine_scoring_summary.build_av_engine_scoring_summary_from_db()
    if summary_df is None or summary_df.empty:
        du.print_error("[MENU] Engine scoring summary returned no rows.")
        return 1

    du.print_success(f"[MENU] Engine summary rows: {len(summary_df)}")
    return 0


def _run_to_stage(profile_id: str) -> int:
    """Run pipeline and stop after a selected stage."""
    from main import run_pipeline

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


def _show_contract_snapshot_viewer() -> int:
    """Show latest experiment contract highlights for quick reproducibility review."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    path = output_root / "diagnostics" / "experiment_contract_snapshot.latest.json"
    if not path.exists():
        du.print_warning(f"[MENU] Missing latest experiment contract: {path}")
        return 1
    payload = _read_json_object(path)
    if not payload:
        du.print_warning("[MENU] Latest experiment contract is unreadable.")
        return 1
    model_contract = payload.get("model_contract", {}) if isinstance(payload.get("model_contract"), dict) else {}
    split_contract = payload.get("split_contract", {}) if isinstance(payload.get("split_contract"), dict) else {}
    series = payload.get("experiment_series", {}) if isinstance(payload.get("experiment_series"), dict) else {}
    du.print_section("Contract Snapshot Viewer")
    du.print_stat("Run ID", payload.get("run_id", "n/a"))
    du.print_stat("Profile ID", payload.get("profile_id", "n/a"))
    du.print_stat("Split Hash", split_contract.get("split_hash", "n/a"))
    du.print_stat("Model Config Hash", model_contract.get("model_config_hash", "n/a"))
    du.print_stat(
        "No Retuning Across Perturbations",
        model_contract.get("no_model_retuning_across_perturbations", "n/a"),
    )
    du.print_stat("Series ID", series.get("series_id", "n/a"))
    return 0


def _show_experiment_series_comparison() -> int:
    """Show latest and previous series hashes to explain run-to-run drift quickly."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    path = output_root / "diagnostics" / "experiment_contract_snapshot.latest.json"
    payload = _read_json_object(path)
    if not payload:
        du.print_warning("[MENU] Latest experiment contract snapshot unavailable.")
        return 1
    series = payload.get("experiment_series", {}) if isinstance(payload.get("experiment_series"), dict) else {}
    rows = [
        {"field": "series_id", "value": series.get("series_id", "n/a")},
        {"field": "split_hash", "value": (series.get("series_key") or {}).get("split_hash", "n/a")},
        {"field": "profile_id", "value": (series.get("series_key") or {}).get("profile_id", "n/a")},
        {"field": "previous_run_id", "value": series.get("previous_run_id_in_series", "n/a")},
        {
            "field": "previous_model_config_hash",
            "value": series.get("previous_model_config_hash_in_series", "n/a"),
        },
        {
            "field": "model_config_hash_stable_with_series",
            "value": series.get("model_config_hash_stable_with_series", "n/a"),
        },
    ]
    du.print_table(rows, title="Experiment Series Comparison", show_index=False)
    return 0


def _run_paper2_series_aggregator() -> int:
    """Aggregate strict reproducibility runs into a macro-F1 comparison table."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    runs_root = output_root / "runs"
    if not runs_root.exists():
        du.print_warning("[MENU] No runs directory found.")
        return 1

    rows: list[dict[str, object]] = []
    for run_dir in sorted([p for p in runs_root.iterdir() if p.is_dir()]):
        pack_dir = run_dir / "paper2_pack"
        readiness_path = pack_dir / "evidence_readiness.json"
        manifest_path = pack_dir / "manifest.json"
        metrics_path = pack_dir / "model_metrics.json"
        if not readiness_path.exists() or not manifest_path.exists() or not metrics_path.exists():
            continue
        readiness = _read_json_object(readiness_path)
        if not readiness or str(readiness.get("status", "")).lower() != "ready":
            continue
        manifest = _read_json_object(manifest_path)
        metrics = _read_json_object(metrics_path)
        if not manifest or not metrics:
            continue
        model_summary = metrics.get("model_summary", {}) if isinstance(metrics, dict) else {}
        macro_f1 = model_summary.get("top_macro_f1") if isinstance(model_summary, dict) else None
        rows.append(
            {
                "run_id": str(manifest.get("run_id", "")),
                "experiment_id": str(manifest.get("config_hash", ""))[:12],
                "dataset_hash": str(manifest.get("dataset_hash", "")),
                "engine_list_hash": str(manifest.get("engine_list_hash", "")),
                "macro_f1": float(macro_f1) if macro_f1 is not None else None,
                "effective_k": int(manifest.get("effective_top_k", 0) or 0),
                "requested_k": int(manifest.get("k_requested", 0) or 0),
                "model": str(model_summary.get("top_model", "")) if isinstance(model_summary, dict) else "",
                "window_start_utc": str((((manifest.get("profile_params") or {}).get("cohort_gates") or {}).get("time_window_start_utc", ""))),
                "window_end_utc": str((((manifest.get("profile_params") or {}).get("cohort_gates") or {}).get("time_window_end_utc", ""))),
            }
        )

    if not rows:
        du.print_warning("[MENU] No strict reproducibility runs found for aggregation.")
        return 1

    baseline = rows[0]
    mismatch_fields = [
        "dataset_hash",
        "engine_list_hash",
        "requested_k",
        "effective_k",
        "model",
        "window_start_utc",
        "window_end_utc",
    ]
    mismatched = []
    for row in rows[1:]:
        for field in mismatch_fields:
            if str(row.get(field, "")) != str(baseline.get(field, "")):
                mismatched.append((str(row.get("run_id", "")), field))
                break
    if mismatched:
        du.print_error("[MENU] Aggregation rejected: evidence runs have mismatched experiment contracts.")
        mismatch_preview = [{"run_id": rid, "field": fld} for rid, fld in mismatched[:10]]
        du.print_table(mismatch_preview, title="Contract mismatch preview", show_index=False)
        return 1

    df = pd.DataFrame(rows).sort_values(["macro_f1", "run_id"], ascending=[False, True])
    out_path = output_root / "diagnostics" / "macro_f1_comparison.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    du.print_success(f"[MENU] Strict reproducibility series comparison exported: {out_path}")
    du.print_table(df, title="Strict Reproducibility Macro-F1 Comparison", show_index=False)
    return 0




def _pipeline_run_mode_labels() -> list[str]:
    """Ordered labels for the primary pipeline launcher."""
    return [
        "Full pipeline",
        "Fast development",
        "Smoke test",
        "Single model only",
        "Stop after a stage",
        "Vendor extraction only",
        "Retrain from cached alignment",
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
            profile_id = resolve_and_validate_profile(prefer_quick=True)
            if not profile_id:
                continue
            return _run_full_pipeline(profile_id)
        if choice == 2:
            return _run_full_pipeline("dev_fast")
        if choice == 3:
            return _run_full_pipeline("dev_smoke")
        if choice == 4:
            profile_id = resolve_and_validate_profile()
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
            return _run_single_model(model_key, profile_id)
        if choice == 5:
            profile_id = resolve_and_validate_profile()
            if not profile_id:
                continue
            return _run_to_stage(profile_id)
        if choice == 6:
            profile_id = resolve_and_validate_profile()
            if not profile_id:
                continue
            return _run_vendor_only(profile_id)
        if choice == 7:
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
        has_paper_exports = bool(context.get("has_paper_exports", False))

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
            "Export Publication Figures -> presentation-ready figure set",
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
                    ("Publication Exports", "Yes" if has_paper_exports else "No"),
                    ("Locked Evidence Run", "Yes" if bool(context.get("has_locked_paper_run", False)) else "No"),
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
            result = _run_paper_structural_diagnostics()
            _print_structural_result_card(
                action="Type-Level Structural Analysis",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "2":
            setattr(app_config, "ANALYSIS_SCOPE", "family")
            result = _run_paper_structural_diagnostics()
            _print_structural_result_card(
                action="Family-Level Structural Analysis",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "3":
            setattr(app_config, "ANALYSIS_SCOPE", "banker")
            result = _run_paper_structural_diagnostics()
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
            result = _run_paper_structural_diagnostics()
            _print_structural_result_card(
                action="Export Publication Figures",
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
            result = _run_paper_structural_diagnostics()
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
    du.print_section("Research Validity Review")
    latest_run_id = _read_latest_run_id()
    selected = _prompt_run_id(default_run_id=latest_run_id)
    if not selected:
        du.print_warning("[MENU] Research validity review cancelled.")
        return 1
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    try:
        _, md_path = repro_workbench.write_research_validity_review(
            output_root=output_root,
            run_id=selected,
            print_fn=print,
        )
    except Exception as exc:
        du.print_error(f"[MENU] Research validity review failed: {exc}")
        return 1
    du.print_success(f"[MENU] Research validity review written to {md_path}")
    return 0


def _compare_runs_write_summary(run_ids: list[str]) -> int:
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    if len(run_ids) < 2:
        du.print_warning("[MENU] Need at least two run IDs to compare.")
        return 1
    repro_workbench.write_run_comparison_summary(
        output_root=output_root,
        run_ids=run_ids,
        print_fn=lambda line: print(line) if line else None,
    )
    return 0


def _launch_compare_runs_menu() -> None:
    """Run-to-run comparison without requiring evidence mode or experiment contracts."""
    while True:
        compare_modes = [
            "Compare latest two runs",
            "Compare selected run IDs (comma-separated)",
            "Compare runs matching profile substring",
            "Experiment contract snapshot + paired comparison",
        ]
        choice = mu.display_menu(
            compare_modes,
            title="Compare runs / experiment series",
            exit_label="Back",
            breadcrumb="Main menu › Reproducibility & research validity › Compare runs",
        )
        if choice == 0:
            return
        output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
        if choice == 1:
            ids = repro_workbench.list_run_ids_newest_first(limit=2)
            _compare_runs_write_summary(ids)
            continue
        if choice == 2:
            latest = _read_latest_run_id() or ""
            try:
                raw = input(f"Enter run IDs (comma-separated) [{latest}]: ").strip()
            except KeyboardInterrupt:
                du.print_warning("[MENU] Cancelled.")
                continue
            raw = raw or latest
            ids = [token.strip() for token in raw.split(",") if token.strip()]
            _compare_runs_write_summary(ids)
            continue
        if choice == 3:
            latest_rid = _read_latest_run_id() or ""
            latest_profile = ""
            if latest_rid:
                latest_profile = str(
                    _read_run_summary(output_root / "runs" / latest_rid).get("profile_id") or ""
                ).strip()
            hint = f" [{latest_profile}]" if latest_profile else ""
            try:
                query = input(
                    f"Profile substring (match on run_summary profile_id){hint}: "
                ).strip()
            except KeyboardInterrupt:
                du.print_warning("[MENU] Cancelled.")
                continue
            if not query and latest_profile:
                query = latest_profile
                du.print_info(f"[MENU] Using latest run profile_id: {query}")
            elif not query:
                du.print_warning("[MENU] No profile substring — enter text or rely on a latest run with profile_id.")
                continue
            matches: list[str] = []
            for rid in repro_workbench.list_run_ids_newest_first():
                summary = _read_run_summary(output_root / "runs" / rid)
                pid = str(summary.get("profile_id") or "").strip()
                if query.lower() in pid.lower():
                    matches.append(rid)
                if len(matches) >= 24:
                    break
            _compare_runs_write_summary(matches)
            continue
        if choice == 4:
            snap_path = output_root / "diagnostics" / "experiment_contract_snapshot.latest.json"
            payload = _read_json_object(snap_path)
            if not payload:
                du.print_info(f"[MENU] No experiment contract snapshot at {snap_path} (normal for many dev runs).")
                du.print_info("[MENU] Falling back to latest-two-run comparison.")
                _compare_runs_write_summary(repro_workbench.list_run_ids_newest_first(limit=2))
                continue
            series = payload.get("experiment_series") if isinstance(payload.get("experiment_series"), dict) else {}
            cur = str(payload.get("run_id") or "").strip()
            prev = str(series.get("previous_run_id_in_series") or "").strip()
            du.print_stat("Snapshot run_id", cur or "n/a")
            du.print_stat("Previous in series", prev or "n/a")
            du.print_stat("Series ID", series.get("series_id", "n/a"))
            ids = [rid for rid in (cur, prev) if rid]
            if len(ids) < 2:
                du.print_warning("[MENU] Snapshot does not reference two distinct run IDs — compare latest two instead.")
                _compare_runs_write_summary(repro_workbench.list_run_ids_newest_first(limit=2))
            else:
                _compare_runs_write_summary(ids)
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _run_evidence_paper_readiness_menu_action() -> int:
    """Explain evidence gates and write readiness summary under global diagnostics."""
    du.print_section("Evidence / Paper Readiness")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    latest_run_id = _read_latest_run_id()
    locked = _read_locked_paper_run_id()
    ev = _latest_run_paper_mode_enabled()
    exports = _paper_exports_available(latest_run_id)
    try:
        repro_workbench.write_evidence_paper_readiness(
            output_root=output_root,
            latest_run_id=latest_run_id,
            locked_run_id=locked,
            latest_evidence_mode=ev,
            latest_paper_exports=exports,
            print_fn=print,
        )
    except Exception as exc:
        du.print_error(f"[MENU] Evidence readiness export failed: {exc}")
        return 1
    print("")
    du.print_stat("Latest run evidence mode", "Yes" if ev else "No")
    du.print_stat("Publication exports (latest)", "Yes" if exports else "No")
    du.print_stat("Locked evidence run", locked or "(none)")
    print("")
    du.print_info("[MENU] Strict bundle checks: Reproducibility › Evidence / Paper Readiness › Evidence Bundle Checker.")
    return 0


def _launch_reproducibility_menu() -> None:
    """Reproducibility, research validity, run comparison, and evidence readiness."""
    while True:
        context = _latest_run_context_status()
        locked_run_id = str(context.get("locked_paper_run_id", "")).strip()
        du.print_info(f"[MENU] Locked evidence run: {locked_run_id if locked_run_id else '(none)'}")
        latest_has_paper_exports = bool(context.get("has_paper_exports", False))
        latest_is_paper = _latest_run_paper_mode_enabled()
        latest_has_provenance = _latest_run_has_provenance()

        base_options: List[str] = [
            "Run Health & Artifact Check",
            "Research Validity Review",
            "Compare Runs / Experiment Series",
            "Evidence / Paper Readiness",
        ]
        _print_availability_block(
            rows=[
                ("Locked Evidence Run", locked_run_id if locked_run_id else "No"),
                ("Latest Run Uses Evidence Mode", "Yes" if latest_is_paper else "No"),
                ("Latest Run Publication Exports", "Yes" if latest_has_paper_exports else "No"),
                ("Latest Run Provenance", "Yes" if latest_has_provenance else "No"),
            ]
        )
        choice = mu.display_menu(
            base_options,
            title="Reproducibility & research validity",
            exit_label="Back",
            breadcrumb="Main menu › Reproducibility & research validity",
        )
        if choice == 0:
            return
        if choice == 1:
            _run_health_check_for_selected_run()
            continue
        if choice == 2:
            _run_research_validity_review_menu()
            continue
        if choice == 3:
            _launch_compare_runs_menu()
            continue
        if choice == 4:
            _launch_evidence_paper_readiness_hub()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_evidence_paper_readiness_hub() -> None:
    """Evidence readiness exports, bundle checker, and strict reproducibility aggregation."""
    while True:
        opts = [
            "Evidence / paper readiness summary (export JSON/MD)",
            "Evidence Bundle Checker",
            "Strict reproducibility series aggregator",
        ]
        choice = mu.display_menu(
            opts,
            title="Evidence / paper readiness",
            exit_label="Back",
            breadcrumb="Main menu › Reproducibility & research validity › Evidence",
        )
        if choice == 0:
            return
        if choice == 1:
            _run_evidence_paper_readiness_menu_action()
            continue
        if choice == 2:
            _run_paper2_freeze_checker()
            continue
        if choice == 3:
            _run_paper2_series_aggregator()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _run_family_label_taxonomy_audit_script() -> int:
    """Invoke scripts/family_label_taxonomy_audit.py for cohort taxonomy audit."""
    script_path = repo_operator_script("family_label_taxonomy_audit.py")
    if not script_path.is_file():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1

    du.print_section("Family label taxonomy audit")
    du.print_info(
        "Loads the labeled cohort from the database using a profile's gates (same path as pipeline samples; no training)."
    )
    du.print_info(
        "Writes taxonomy audit CSV/MD under the diagnostics dir below. "
        "If cohort snapshot export is enabled, analysis_snapshot_*.csv/.meta.txt land in the same directory "
        "(not global output/diagnostics unless you omit --diagnostics-dir and use the default audit folder)."
    )
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    rid = _read_latest_run_id()
    diag_args: list[str] = []
    if rid:
        rdiag = output_root / "runs" / rid / "diagnostics"
        rdiag.mkdir(parents=True, exist_ok=True)
        diag_args = ["--diagnostics-dir", str(rdiag.resolve())]
        du.print_info(
            f"Target diagnostics dir: runs/{rid}/diagnostics/ "
            "(taxonomy audit + cohort snapshot artifacts when snapshot export is on)."
        )
    else:
        du.print_note(
            "No latest run id — the script will use output/diagnostics/taxonomy_audit_<timestamp>/ instead."
        )

    profile_id = resolve_and_validate_profile(
        prefer_quick=True,
        menu_breadcrumb="Main menu › Data Diagnostics › Cohort › Taxonomy audit",
        menu_title="Profile for cohort audit",
        menu_subtitle=(
            "Choose which cohort definition to audit. Blank Enter selects the default highlighted row; 0 = Back."
        ),
    )
    if not profile_id:
        du.print_warning("[MENU] Taxonomy audit cancelled (no profile).")
        return 1
    cmd = [sys.executable, str(script_path), "--profile", profile_id, *diag_args]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    return int(proc.returncode)


def _print_cohort_family_artifact_paths() -> None:
    """List key cohort / family diagnostic paths for the latest run."""
    du.print_section("Cohort / family artifact paths")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    rid = _read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run — nothing to resolve.")
        return
    rdiag = (output_root / "runs" / rid / "diagnostics").resolve()
    gdiag = (output_root / "diagnostics").resolve()

    def stat(label: str, path: Path) -> None:
        du.print_stat(label, "present" if path.is_file() else "missing")

    du.print_stat("Run diagnostics dir", str(rdiag))

    rows: list[tuple[str, Path]] = [
        ("family_label_taxonomy_audit.csv", rdiag / "family_label_taxonomy_audit.csv"),
        ("family_label_taxonomy_audit.md", rdiag / "family_label_taxonomy_audit.md"),
        ("support_threshold_preview.md", rdiag / "support_threshold_preview.md"),
        ("support_threshold_preview.csv", rdiag / "support_threshold_preview.csv"),
        ("family_distribution.csv", rdiag / "family_distribution.csv"),
        ("low_support_families.csv", rdiag / "low_support_families.csv"),
        ("dataset_foundation_summary.md", rdiag / "dataset_foundation_summary.md"),
        ("dataset_foundation_summary.json", rdiag / "dataset_foundation_summary.json"),
        (f"cohort_filter_contract_{rid}.json", rdiag / f"cohort_filter_contract_{rid}.json"),
        (f"cohort_gate_counts_{rid}.csv", rdiag / f"cohort_gate_counts_{rid}.csv"),
        ("cohort_lock_summary.json", rdiag / "cohort_lock_summary.json"),
        ("cohort_membership.csv", rdiag / "cohort_membership.csv"),
        (f"analysis_snapshot_filter_summary_{rid}.csv", rdiag / f"analysis_snapshot_filter_summary_{rid}.csv"),
        (f"analysis_snapshot_{rid}.csv", rdiag / f"analysis_snapshot_{rid}.csv"),
        (f"analysis_snapshot_{rid}.meta.txt", rdiag / f"analysis_snapshot_{rid}.meta.txt"),
        (
            f"analysis_snapshot_label_conflicts_{rid}.csv",
            rdiag / f"analysis_snapshot_label_conflicts_{rid}.csv",
        ),
        ("paper_cohort_sample_ids.csv", rdiag / "paper_cohort_sample_ids.csv"),
        ("dataset_time_contract (resolved)", oh.resolve_dataset_time_contract_path(rdiag, rid)),
        ("family_distribution_2020_present.csv", rdiag / "family_distribution_2020_present.csv"),
        ("family_distribution_by_year.csv", rdiag / "family_distribution_by_year.csv"),
    ]
    for label, path in rows:
        stat(label, path)

    primary_snap = rdiag / f"analysis_snapshot_{rid}.csv"
    primary_filter = rdiag / f"analysis_snapshot_filter_summary_{rid}.csv"
    extra_snaps = sorted(
        p
        for p in rdiag.glob("analysis_snapshot_*.csv")
        if p.is_file() and p not in {primary_snap, primary_filter}
    )
    if extra_snaps:
        du.print_subheader("Other analysis_snapshot_*.csv (adhoc / taxonomy audit)")
        for p in extra_snaps[:10]:
            stat(p.name, p)
        if len(extra_snaps) > 10:
            du.print_note(f"… plus {len(extra_snaps) - 10} more under this diagnostics dir")

    latest_snap = gdiag / "analysis_snapshot.latest.csv"
    latest_meta = gdiag / "analysis_snapshot.latest.meta.txt"
    if latest_snap.is_file() or latest_meta.is_file():
        du.print_subheader("Global diagnostics (operator .latest mirrors)")
        stat(str(gdiag / "analysis_snapshot.latest.csv"), latest_snap)
        stat(str(gdiag / "analysis_snapshot.latest.meta.txt"), latest_meta)

    print("")


def _launch_cohort_family_audit_menu() -> None:
    """Family taxonomy, support thresholds, cohort distributions."""
    while True:
        opts = [
            "Run taxonomy audit (pick profile → writes to latest run diagnostics)",
            "Show cohort / family artifact paths (run + global mirrors)",
        ]
        choice = mu.display_menu(
            opts,
            title="Cohort / family label audit",
            exit_label="Back",
            breadcrumb="Main menu › Data Diagnostics › Cohort",
        )
        if choice == 0:
            return
        if choice == 1:
            _run_family_label_taxonomy_audit_script()
            continue
        if choice == 2:
            _print_cohort_family_artifact_paths()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_parser_vendor_coverage_menu() -> None:
    """Parser coverage, vendor diagnostics, AV engine scoring from DB."""
    while True:
        from .menu import vendor_diagnostics

        vendor_diagnostics.print_parser_diagnostics_state()
        opts = [
            "Validate Parser Coverage",
            "Single Vendor Parser Diagnostic",
            "Vendor coverage CSV snapshot (latest run)",
            "Engine Scoring Summary (database)",
        ]
        choice = mu.display_menu(
            opts,
            title="Parser & vendor coverage",
            exit_label="Back",
            breadcrumb="Main menu › Data Diagnostics › Parser vendor",
        )
        if choice == 0:
            return
        if choice == 1:
            validate_parser_columns_from_latest_export()
            continue
        if choice == 2:
            run_single_vendor_parser_check()
            continue
        if choice == 3:
            print_compact_vendor_coverage_snapshot()
            continue
        if choice == 4:
            _run_engine_summary_only()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_permission_intelligence_coverage_menu() -> None:
    """Permission modality coverage pointers (reads latest run diagnostics)."""
    from obsidiandroid.common.json_io import read_json_dict

    du.print_section("Permission intelligence coverage")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    rid = _read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"

    rows: list[tuple[str, list[Path]]] = [
        ("Permission coverage summary", [rdiag / "permission_coverage_summary.csv", gdiag / "permission_coverage_summary.csv"]),
        ("Dataset foundation (JSON)", [rdiag / "dataset_foundation_summary.json", gdiag / "dataset_foundation_summary.json"]),
        ("Dataset foundation (gates + cohort)", [rdiag / "dataset_foundation_summary.md", gdiag / "dataset_foundation_summary.md"]),
        ("Modality contribution (Markdown)", [rdiag / "modality_contribution_summary.md", gdiag / "modality_contribution_summary.md"]),
        ("Modality contribution (JSON, Q2 metrics)", [rdiag / "modality_contribution_summary.json", gdiag / "modality_contribution_summary.json"]),
        ("Feature-set ablation (CSV)", [rdiag / "feature_set_ablation_summary.csv", gdiag / "feature_set_ablation_summary.csv"]),
        ("Feature-set ablation (Markdown)", [rdiag / "feature_set_ablation_summary.md", gdiag / "feature_set_ablation_summary.md"]),
        ("Vendor feature coverage summary", [rdiag / "vendor_feature_coverage_summary.csv", gdiag / "vendor_feature_coverage_summary.csv"]),
        ("Feature group survival (from column survival)", [rdiag / "feature_group_survival.csv", gdiag / "feature_group_survival.csv"]),
        (
            "Permission feature audit",
            [rdiag / "permission_feature_audit.csv", rdiag / f"permission_feature_audit_{rid}.csv"],
        ),
        ("Vendor leakage safety audit", [rdiag / "vendor_leakage_safety_audit.csv", gdiag / "vendor_leakage_safety_audit.csv"]),
        ("Permission signal quality (CSV)", [rdiag / "permission_signal_quality.csv", gdiag / "permission_signal_quality.csv"]),
        (
            "Permission signal quality (report)",
            [rdiag / "permission_signal_quality_report.md", gdiag / "permission_signal_quality_report.md"],
        ),
    ]
    for label, candidates in rows:
        hit = _first_existing_path(candidates)
        du.print_stat(label, str(hit.resolve()) if hit else "missing")

    q2 = read_json_dict(rdiag / "modality_contribution_summary.json") or read_json_dict(
        gdiag / "modality_contribution_summary.json"
    )
    if isinstance(q2, dict) and q2:
        du.print_subheader("Q2 snapshot (modality contribution)")
        gov_n = _governed_cohort_n_for_q2(rdiag=rdiag, gdiag=gdiag, q2=q2)
        du.print_stat("Governed cohort (denominator)", str(gov_n) if gov_n is not None else "—")
        du.print_stat(
            "Permission signal",
            f"{q2.get('permission_signal_n', '—')} rows ({diagnostics_banners.format_percent_for_menu(q2.get('permission_signal_pct'))})",
        )
        du.print_stat(
            "Vendor merge authority",
            f"{q2.get('vendor_merge_n', '—')} rows ({diagnostics_banners.format_percent_for_menu(q2.get('vendor_merge_pct'))})",
        )
        pcols = q2.get("permission_feature_columns")
        du.print_stat(
            "Permission columns (fused / contract)",
            "—" if pcols is None or pcols == "" else str(pcols),
        )
        du.print_stat(
            "AV engines (observed / included in contract)",
            f"{q2.get('av_engines_observed', '—')} / {q2.get('av_engines_included', '—')}",
        )
        notes = q2.get("interpretation_notes")
        if isinstance(notes, list) and notes:
            du.print_subheader("Q2 interpretation (from JSON)")
            for line in notes[:5]:
                if isinstance(line, str) and line.strip():
                    du.print_note(line.strip())
        du.print_note(
            "Definitions: `permission_signal_pct` = cohort rows with permission-bag signal ÷ governed cohort; "
            "`vendor_merge_pct` = rows with parsed vendor merge authority ÷ the same denominator."
        )
    else:
        du.print_note(
            "No modality_contribution_summary.json found for this run (or global mirror). "
            "Generate Q1–Q3 diagnostics for the run to populate Q2 permission intelligence."
        )

    du.print_info(
        "[MENU] Prefer run paths above; global output/diagnostics/ holds .latest mirrors when hygiene mode omits duplicates inside runs/. "
        "Per-column survival lives under Data Diagnostics → Feature matrix / modality coverage."
    )
    print("")


def _launch_feature_matrix_modality_menu() -> None:
    """Feature contract / modality / ablation pointers."""
    du.print_section("Feature matrix / modality coverage")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    rid = _read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"
    entries: list[tuple[str, list[Path]]] = [
        ("Feature contract", [rdiag / "feature_contract.json", gdiag / "feature_contract.json"]),
        (
            "Modality contribution (JSON)",
            [rdiag / "modality_contribution_summary.json", gdiag / "modality_contribution_summary.json"],
        ),
        (
            "Feature-set ablation summary",
            [rdiag / "feature_set_ablation_summary.csv", gdiag / "feature_set_ablation_summary.csv"],
        ),
        (
            "Feature column survival",
            [
                rdiag / f"feature_column_survival_{rid}.csv",
                rdiag / "feature_column_survival.latest.csv",
                gdiag / "feature_column_survival.latest.csv",
            ],
        ),
        ("Feature group survival", [rdiag / "feature_group_survival.csv", gdiag / "feature_group_survival.csv"]),
    ]
    for label, candidates in entries:
        hit = _first_existing_path(candidates)
        du.print_stat(label, str(hit.resolve()) if hit else "missing")
    print("")


def _launch_taxonomy_consistency_review_menu() -> None:
    """Taxonomy consistency summary and mismatch exports."""
    du.print_section("Taxonomy consistency review")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    rid = _read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"
    rows: list[tuple[str, list[Path]]] = [
        (
            "Taxonomy consistency summary (JSON)",
            [rdiag / f"taxonomy_consistency_summary_{rid}.json", gdiag / "taxonomy_consistency_summary.latest.json"],
        ),
        (
            "Taxonomy mismatches (CSV)",
            [rdiag / f"taxonomy_consistency_mismatches_{rid}.csv", gdiag / "taxonomy_consistency_mismatches.latest.csv"],
        ),
        ("Prediction errors (CSV)", [rdiag / f"prediction_errors_{rid}.csv"]),
    ]
    for label, candidates in rows:
        hit = _first_existing_path(candidates)
        du.print_stat(label, str(hit.resolve()) if hit else "missing")
    du.print_info(
        "[MENU] Prefer run-scoped names; global `*.latest.*` under output/diagnostics/ mirrors when hygiene omits duplicates."
    )
    print("")


def _launch_data_diagnostics_menu() -> None:
    """Data quality: cohort, parsers, permissions, features, taxonomy, structural exports."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    while True:
        diagnostics_banners.print_data_diagnostics_banner(
            output_root=output_root,
            latest_run_id=_read_latest_run_id(),
        )
        data_sections = [
            "Cohort / Family Label Audit",
            "Parser & Vendor Coverage",
            "Permission Intelligence Coverage",
            "Feature Matrix / Modality Coverage",
            "Taxonomy Consistency Review",
            "Pipeline profile tuning (latest manifest)",
        ]
        choice = mu.display_menu(
            data_sections,
            title="Data diagnostics",
            exit_label="Back",
            breadcrumb="Main menu › Data Diagnostics",
        )
        if choice == 0:
            return
        if choice == 1:
            _launch_cohort_family_audit_menu()
            continue
        if choice == 2:
            _launch_parser_vendor_coverage_menu()
            continue
        if choice == 3:
            _launch_permission_intelligence_coverage_menu()
            continue
        if choice == 4:
            _launch_feature_matrix_modality_menu()
            continue
        if choice == 5:
            _launch_taxonomy_consistency_review_menu()
            continue
        if choice == 6:
            _show_profile_tuning_snapshot()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _show_research_report_key_artifact_paths() -> None:
    """Consolidated paths: index/Q1–Q3/validity audits for the latest run."""
    du.print_section("Key research artifacts (latest run)")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    rid = _read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"

    du.print_subheader("Evidence index & dashboard")
    for label, name in (
        ("Diagnostics index (markdown)", "index.md"),
        ("Operator dashboard pointers", "operator_dashboard_snapshot.md"),
    ):
        p = rdiag / name
        du.print_stat(label, str(p.resolve()) if p.is_file() else "missing")

    du.print_subheader("Three-question summaries (Q1–Q3)")
    for label, name in (
        ("Q1 Dataset foundation", "dataset_foundation_summary.md"),
        ("Q2 Modality contribution", "modality_contribution_summary.md"),
        ("Q3 Model / family failure", "model_and_family_failure_summary.md"),
    ):
        p = rdiag / name
        du.print_stat(label, str(p.resolve()) if p.is_file() else "missing")

    du.print_subheader("Research validity & skeptic audits")
    for label, fname in (
        ("Headline score scope", "headline_score_scope.md"),
        ("High-score audit", "high_score_audit.md"),
        ("Leakage-safe score comparison", "leakage_safe_score_comparison.md"),
        ("Research validity review", "research_validity_review.md"),
        ("False attribution audit", "false_attribution_audit.md"),
        ("Split contamination audit", "split_contamination_audit.md"),
    ):
        p = rdiag / fname
        du.print_stat(label, str(p.resolve()) if p.is_file() else "missing")

    du.print_info("[MENU] Prefer `diagnostics/index.md` under this run for the full artifact map.")
    print("")


def _show_cache_pointer_guidance() -> None:
    """Explain latest pointers and where manifests live."""
    du.print_section("Cache / latest pointers")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    du.print_stat("run_manifest.latest.json", str((output_root / "diagnostics" / "run_manifest.latest.json").resolve()))
    du.print_stat("promoted latest_run.txt", str((output_root / "promoted" / "latest_run.txt").resolve()))
    du.print_info("[MENU] Newest canonical manifests live under output/runs/<run_id>/run_manifest.json.")
    print("")


def _show_repair_migration_info() -> None:
    """Point operators at migration/repair entrypoints (no destructive actions here)."""
    du.print_section("Repair / migration helpers")
    du.print_info("[MENU] Use repo scripts under scripts/ for targeted repairs (see docs/STRUCTURE_MIGRATION_PLAN.md).")
    du.print_info("[MENU] Pipeline reruns with profile validation: Run Analysis menu.")
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
            du.print_info("[MENU] From repo root: make ci   (mirrors GitHub Actions)")
            continue
        if choice == 2:
            du.print_info("[MENU] Run: python scripts/dev/check_import_surface.py")
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
            _show_latest_run_snapshot()
            continue
        if choice == 2:
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
    while True:
        research = [
            "Structural Analysis",
            "Model Evaluation",
            "Open key research artifact paths (index, Q1–Q3, validity)",
            "Claim Artifact Map (generate scaffold)",
        ]
        choice = mu.display_menu(
            research,
            title="Research reports",
            exit_label="Back",
            breadcrumb="Main menu › Research Reports",
        )
        if choice == 0:
            return
        if choice == 1:
            _launch_structural_analysis_menu()
            continue
        if choice == 2:
            _launch_model_evaluation_menu()
            continue
        if choice == 3:
            _show_research_report_key_artifact_paths()
            continue
        if choice == 4:
            _run_claim_artifact_map_scaffold()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_operations_menu() -> None:
    """Operational maintenance: outputs, reuse, cleanup, pointers — not research diagnostics."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    locked = _read_locked_paper_run_id()
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
        du.print_warning("[MENU] Invalid choice received.")


def _print_operator_console_summary() -> None:
    """Print a compact operator summary block ahead of the main menu."""
    context = _latest_run_context_status()
    latest_run_id = str(context.get("latest_run_id", "")).strip() or "None yet"
    du.print_section("Workspace Status")
    _print_availability_block(
        rows=[
            ("Latest Run", latest_run_id),
            ("Run Diagnostics", _status_text(_latest_run_has_provenance(), ready="Available", pending="Missing")),
            ("Publication Exports", _status_text(bool(context.get("has_paper_exports", False)), ready="Available", pending="Not built")),
        ]
    )


def _build_main_menu_commands() -> list[_MenuCommand]:
    """Return the redesigned top-level operator menu."""
    return [
        _MenuCommand(label="Run Analysis", action=_launch_pipeline_actions_menu),
        _MenuCommand(label="Run Status and History", action=_launch_run_overview_menu),
        _MenuCommand(label="Research Reports", action=_launch_research_reports_menu),
        _MenuCommand(label="Reproducibility & research validity", action=_launch_reproducibility_menu),
        _MenuCommand(label="Data Diagnostics", action=_launch_data_diagnostics_menu),
        _MenuCommand(label="Tools and Maintenance", action=_launch_operations_menu),
        _MenuCommand(label="Clear Screen", action=lambda: 0),
    ]


def launch_startup_menu() -> int:
    """Run interactive startup menu loop."""
    _print_startup_context()

    while True:
        commands = _build_main_menu_commands()
        choice = mu.display_menu(
            [c.label for c in commands],
            title="Main menu",
            exit_label="Exit",
            breadcrumb="ObsidianDroid · operator console",
        )

        if choice == 0:
            du.print_info("[MENU] Exit requested.")
            return 0

        selected = commands[choice - 1]
        if selected.label == "Clear Screen":
            du.clear_console()
            _print_startup_context()
            continue

        result = selected.action()
        if isinstance(result, int) and result != 0:
            return result
        continue


def main() -> int:
    """Module CLI entrypoint."""
    try:
        return launch_startup_menu()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Interrupted by user (Ctrl+C). Exiting.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
