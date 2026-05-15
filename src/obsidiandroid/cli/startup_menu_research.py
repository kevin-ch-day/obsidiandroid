"""Research-report and reproducibility menu orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from config import app_config
from obsidiandroid.diagnostics import reproducibility_workbench as repro_workbench

from .menu.operator_state import build_operator_state
from .startup_menu_prompts import prompt_run_id
from .ui import display as du
from .ui import menu as mu


def show_contract_snapshot_viewer(*, read_json_object: Callable[[Path], dict]) -> int:
    """Show latest experiment contract highlights for quick reproducibility review."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    path = output_root / "diagnostics" / "experiment_contract_snapshot.latest.json"
    if not path.exists():
        du.print_warning(f"[MENU] Missing latest experiment contract: {path}")
        return 1
    payload = read_json_object(path)
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


def show_experiment_series_comparison(*, read_json_object: Callable[[Path], dict]) -> int:
    """Show latest and previous series hashes to explain run-to-run drift quickly."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    path = output_root / "diagnostics" / "experiment_contract_snapshot.latest.json"
    payload = read_json_object(path)
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


def run_evidence_bundle_series_aggregator(*, read_json_object: Callable[[Path], dict]) -> int:
    """Aggregate strict reproducibility evidence bundles into a macro-F1 comparison table."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    runs_root = output_root / "runs"
    if not runs_root.exists():
        du.print_warning("[MENU] No runs directory found.")
        return 1

    rows: list[dict[str, object]] = []
    for run_dir in sorted([p for p in runs_root.iterdir() if p.is_dir()]):
        pack_dir = run_dir / "evidence_bundle"
        if not pack_dir.exists():
            pack_dir = run_dir / "paper2_pack"
        readiness_path = pack_dir / "evidence_readiness.json"
        manifest_path = pack_dir / "manifest.json"
        metrics_path = pack_dir / "model_metrics.json"
        if not readiness_path.exists() or not manifest_path.exists() or not metrics_path.exists():
            continue
        readiness = read_json_object(readiness_path)
        if not readiness or str(readiness.get("status", "")).lower() != "ready":
            continue
        manifest = read_json_object(manifest_path)
        metrics = read_json_object(metrics_path)
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


def run_research_validity_review_menu(
    *,
    read_latest_run_id: Callable[[], str | None],
) -> int:
    """Aggregate dataset/modality/skeptic diagnostics into one markdown+json review."""
    du.print_section("Research Validity Review")
    latest_run_id = read_latest_run_id()
    selected = prompt_run_id(default_run_id=latest_run_id)
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


def launch_compare_runs_menu(
    *,
    read_latest_run_id: Callable[[], str | None],
    read_run_summary: Callable[[Path], dict],
    read_json_object: Callable[[Path], dict],
) -> None:
    """Run-to-run comparison without requiring evidence mode or experiment contracts."""

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
            latest = read_latest_run_id() or ""
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
            latest_rid = read_latest_run_id() or ""
            latest_profile = ""
            if latest_rid:
                latest_profile = str(read_run_summary(output_root / "runs" / latest_rid).get("profile_id") or "").strip()
            hint = f" [{latest_profile}]" if latest_profile else ""
            try:
                query = input(f"Profile substring (match on run_summary profile_id){hint}: ").strip()
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
                summary = read_run_summary(output_root / "runs" / rid)
                pid = str(summary.get("profile_id") or "").strip()
                if query.lower() in pid.lower():
                    matches.append(rid)
                if len(matches) >= 24:
                    break
            _compare_runs_write_summary(matches)
            continue
        if choice == 4:
            snap_path = output_root / "diagnostics" / "experiment_contract_snapshot.latest.json"
            payload = read_json_object(snap_path)
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


def run_evidence_readiness_menu_action(
    *,
    read_latest_run_id: Callable[[], str | None],
    read_locked_paper_run_id: Callable[[], str | None],
    paper2_freeze_checker: Callable[[], int],
) -> int:
    """Explain evidence gates and write readiness summary under global diagnostics."""
    del paper2_freeze_checker  # kept for future parity-friendly expansion
    du.print_section("Evidence Readiness")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    shared = build_operator_state(output_base=output_root, run_id=read_latest_run_id())
    latest_run_id = str(shared.get("latest_run_id", "") or "")
    locked = read_locked_paper_run_id()
    evidence_mode = bool(shared.get("evidence_mode", False))
    exports = bool(shared.get("has_paper_exports", False))
    try:
        repro_workbench.write_evidence_paper_readiness(
            output_root=output_root,
            latest_run_id=latest_run_id or None,
            locked_run_id=locked,
            latest_evidence_mode=evidence_mode,
            latest_paper_exports=exports,
            print_fn=print,
        )
    except Exception as exc:
        du.print_error(f"[MENU] Evidence readiness export failed: {exc}")
        return 1
    print("")
    du.print_stat("Latest run evidence mode", "Yes" if evidence_mode else "No")
    du.print_stat("Publication exports (latest)", "Yes" if exports else "No")
    du.print_stat("Locked evidence run", locked or "(none)")
    print("")
    du.print_info("[MENU] Strict bundle checks: Reproducibility › Evidence Readiness › Cohort Lock Checker.")
    return 0


def launch_evidence_readiness_hub(
    *,
    run_evidence_readiness_action: Callable[[], int],
    run_paper2_freeze_checker: Callable[[], int],
    run_evidence_bundle_series_aggregator_action: Callable[[], int],
) -> None:
    """Evidence readiness exports, cohort lock checks, and bundle aggregation."""
    while True:
        opts = [
            "Evidence Readiness Summary (export JSON/MD)",
            "Cohort Lock Checker",
            "Evidence Bundle Series Aggregator",
        ]
        choice = mu.display_menu(
            opts,
            title="Evidence readiness",
            exit_label="Back",
            breadcrumb="Main menu › Reproducibility & research validity › Evidence",
        )
        if choice == 0:
            return
        if choice == 1:
            run_evidence_readiness_action()
            continue
        if choice == 2:
            run_paper2_freeze_checker()
            continue
        if choice == 3:
            run_evidence_bundle_series_aggregator_action()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def launch_reproducibility_menu(
    *,
    read_latest_run_id: Callable[[], str | None],
    read_locked_paper_run_id: Callable[[], str | None],
    read_run_summary: Callable[[Path], dict],
    read_json_object: Callable[[Path], dict],
    run_health_check_for_selected_run: Callable[[], int],
    run_research_validity_review_action: Callable[[], int],
    launch_evidence_readiness_hub_action: Callable[[], None],
) -> None:
    """Reproducibility, research validity, run comparison, and evidence readiness."""
    while True:
        shared = build_operator_state(run_id=read_latest_run_id())
        locked_run_id = str(read_locked_paper_run_id() or shared.get("locked_run_id", "") or "").strip()
        du.print_info(f"[MENU] Locked evidence run: {locked_run_id if locked_run_id else '(none)'}")
        _print_availability_block(
            rows=[
                ("Locked Evidence Run", locked_run_id if locked_run_id else "No"),
                ("Latest Run Uses Evidence Mode", "Yes" if bool(shared.get("evidence_mode", False)) else "No"),
                ("Latest Run Publication Exports", "Yes" if bool(shared.get("has_paper_exports", False)) else "No"),
                ("Latest Run Provenance", "Yes" if bool(shared.get("latest_run_has_provenance", False)) else "No"),
            ]
        )
        choice = mu.display_menu(
            [
                "Run Health & Artifact Check",
                "Research Validity Review",
                "Compare Runs / Experiment Series",
                "Evidence Readiness",
            ],
            title="Reproducibility & research validity",
            exit_label="Back",
            breadcrumb="Main menu › Reproducibility & research validity",
        )
        if choice == 0:
            return
        if choice == 1:
            run_health_check_for_selected_run()
            continue
        if choice == 2:
            run_research_validity_review_action()
            continue
        if choice == 3:
            launch_compare_runs_menu(
                read_latest_run_id=read_latest_run_id,
                read_run_summary=read_run_summary,
                read_json_object=read_json_object,
            )
            continue
        if choice == 4:
            launch_evidence_readiness_hub_action()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def show_research_report_key_artifact_paths(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """Consolidated paths: index/Q1–Q3/validity audits for the latest run."""
    du.print_section("Key research artifacts (latest run)")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    rid = read_latest_run_id()
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


def launch_research_reports_menu(
    *,
    launch_structural_analysis_menu: Callable[[], None],
    launch_model_evaluation_menu: Callable[[], None],
    show_research_report_key_artifact_paths_action: Callable[[], None],
    run_claim_artifact_map_scaffold: Callable[[], int],
) -> None:
    """Interpretation artifacts: figures, models, evidence index, claims."""
    while True:
        choice = mu.display_menu(
            [
                "Structural Analysis",
                "Model Evaluation",
                "Open key research artifact paths (index, Q1–Q3, validity)",
                "Claim Artifact Map (generate scaffold)",
            ],
            title="Research reports",
            exit_label="Back",
            breadcrumb="Main menu › Research Reports",
        )
        if choice == 0:
            return
        if choice == 1:
            launch_structural_analysis_menu()
            continue
        if choice == 2:
            launch_model_evaluation_menu()
            continue
        if choice == 3:
            show_research_report_key_artifact_paths_action()
            continue
        if choice == 4:
            run_claim_artifact_map_scaffold()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _print_availability_block(*, rows: list[tuple[str, str]]) -> None:
    """Small local availability table for reproducibility menus."""
    for label, value in rows:
        du.print_stat(label, value)


__all__ = [
    "launch_evidence_readiness_hub",
    "launch_reproducibility_menu",
    "launch_research_reports_menu",
    "run_evidence_bundle_series_aggregator",
    "run_evidence_readiness_menu_action",
    "run_research_validity_review_menu",
    "show_contract_snapshot_viewer",
    "show_experiment_series_comparison",
    "show_research_report_key_artifact_paths",
]
