"""Parser diagnostics views for operator-facing menus."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.database import db_engine

from ..ui import display as du
from .display_mode import mode_max_rows
from .vendor_parser_state import (
    build_parser_onboarding_queue,
    get_parser_summary_state,
    read_csv,
    read_latest_manifest,
    resolve_vendor_gate_pre_gate_csv,
    resolve_vendor_parser_coverage_csv,
    resolve_vendor_stress_test_csv,
)


def print_parser_diagnostics_state(*, mode: str | None = None) -> None:
    """Print a compact operator-facing state block for parser diagnostics."""
    state = get_parser_summary_state(mode=mode)
    du.print_subheader("Parser Diagnostics State")
    du.print_stat("Display mode", str(state.get("display_mode", "compact")))
    du.print_stat("Parser health", str(state.get("status", "unknown")))
    du.print_stat("CSV snapshots", "Available" if state["csv_ready"] else "Unavailable")
    du.print_stat("Workbook drill-down", "Available" if state["workbook_ready"] else "Unavailable")
    du.print_stat("Single-vendor drill-down", "Available" if state["workbook_ready"] else "Blocked")
    if not state["workbook_ready"]:
        du.print_note("Workbook drill-down is optional unless you need single-vendor parser debugging.")
    if state["csv_ready"] and not state["workbook_ready"]:
        du.print_info("CSV snapshots available; workbook drill-down unavailable.")
    if int(state.get("observed_engines", 0) or 0) > 0:
        du.print_subheader("Vendor / engine context")
        du.print_stat("Observed engines", state["observed_engines"])
        du.print_stat("Parser mapped vendors", state["parser_mapped_vendors"])
        du.print_stat("Unmapped vendors", state["unmapped_vendors"])
        du.print_stat("Mapped coverage", f"{state.get('mapped_pct', 0.0)}%")
        du.print_stat(
            "Onboarding queue",
            state["onboarding_candidate_count"] if state["onboarding_candidate_count"] is not None else "n/a",
        )
        queue_df = build_parser_onboarding_queue(limit=None)
        trusted_unmapped_count = int(queue_df["trusted_active"].fillna(False).astype(bool).sum()) if not queue_df.empty else 0
        du.print_stat("Trusted-active unmapped vendors", trusted_unmapped_count)
        du.print_stat(
            "Selected vendors for latest run",
            state["selected_vendors"] if state["selected_vendors"] is not None else "n/a",
        )
        du.print_stat(
            "DB engine scoring universe",
            state["engine_scoring_universe"] if state["engine_scoring_universe"] is not None else "n/a",
        )
        du.print_info(
            "Coverage reflects all observed engines; selected vendors are the narrower leakage-safe subset used by the latest run."
        )
        if state.get("source_run_id"):
            du.print_stat("Source run id", str(state.get("source_run_id")))
        du.print_stat(
            "Coverage snapshot origin",
            "latest run" if bool(state.get("coverage_from_latest_run", False)) else "global/latest mirror or fallback",
        )
        du.print_stat(
            "Selected-vendor snapshot",
            "Present" if bool(state.get("selected_vendor_data_present", False)) else "Missing",
        )
    if state.get("explanation"):
        du.print_info(str(state["explanation"]))
    if state.get("recommended_open_first"):
        du.print_info(f"Open first: {state['recommended_open_first']}")
    if state.get("needs_attention"):
        du.print_note(f"Needs attention: {state['needs_attention']}")
    if state.get("next_tuning_action"):
        du.print_info(f"Tune next: {state['next_tuning_action']}")
    print("")


def print_top_unmapped_vendors(*, limit: int | None = None, mode: str | None = None) -> int:
    """Show top unmapped vendors as a drill-down of the onboarding queue."""
    du.print_section("Top unmapped vendors")
    top_unmapped = build_parser_onboarding_queue(limit=None)
    if top_unmapped.empty:
        du.print_info("[MENU] No unmapped vendors found in the latest CSV snapshot.")
        return 0
    du.print_info("This is a drill-down of the onboarding queue sorted by coverage and priority.")
    row_limit = limit or mode_max_rows(compact=10, detailed=15, debug=25, mode=mode)
    du.print_table(
        top_unmapped[["vendor_column", "coverage_pct", "selected_in_latest_run", "trusted_active"]].head(row_limit),
        title=f"Top {row_limit} unmapped vendors",
        show_index=False,
    )
    return 0


def print_compact_vendor_coverage_snapshot(*, mode: str | None = None) -> int:
    """Print operator-first parser summary from latest coverage artifacts."""
    state = get_parser_summary_state(mode=mode)
    du.print_section("PARSER SUMMARY")
    cov_path = resolve_vendor_parser_coverage_csv()
    if cov_path is None:
        du.print_warning("[MENU] Missing vendor_parser_coverage CSV. Run vendor metadata / pipeline diagnostics export first.")
        return 1
    try:
        coverage_df = pd.read_csv(cov_path)
    except Exception:
        du.print_warning("[MENU] Could not read vendor_parser_coverage CSV.")
        return 1
    if coverage_df.empty:
        du.print_warning("[MENU] Vendor coverage CSV is empty.")
        return 1
    total = int(state.get("observed_engines", len(coverage_df)) or 0)
    mapped = int(state.get("parser_mapped_vendors", 0) or 0)
    unmapped = int(state.get("unmapped_vendors", max(0, total - mapped)) or 0)
    du.print_stat("Parser health", str(state.get("status", "unknown")))
    du.print_stat("Observed vendor columns", total)
    du.print_stat("Mapped parser columns", mapped)
    du.print_stat("Unmapped columns", unmapped)
    du.print_stat("Mapped coverage", f"{state.get('mapped_pct', 0.0)}%")
    du.print_stat("Onboarding queue", int(state.get("onboarding_candidate_count", 0) or 0))
    du.print_stat(
        "Selected vendors for latest run",
        state.get("selected_vendors") if state.get("selected_vendors") is not None else "n/a",
    )
    if state.get("explanation"):
        du.print_info(str(state["explanation"]))
    if state.get("recommended_open_first"):
        du.print_info(f"Open first: {state['recommended_open_first']}")
    if state.get("needs_attention"):
        du.print_note(f"Needs attention: {state['needs_attention']}")
    if state.get("top_candidates_preview"):
        du.print_info(
            "Top onboarding candidates: " + ", ".join(str(v) for v in state["top_candidates_preview"])
        )
    if state.get("top_unmapped_preview"):
        du.print_info(
            "Highest-coverage unmapped vendors: " + ", ".join(str(v) for v in state["top_unmapped_preview"])
        )
    if state.get("top_selected_vendor_preview"):
        du.print_info(
            "Top selected vendors: " + ", ".join(str(v) for v in state["top_selected_vendor_preview"])
        )
    if state.get("next_tuning_action"):
        du.print_info(f"Tune next: {state['next_tuning_action']}")
    if str(state.get("display_mode", "compact")) != "compact":
        du.print_stat("Source file", str(cov_path.resolve()))
        stress_path = resolve_vendor_stress_test_csv()
        if stress_path is not None:
            try:
                stress_df = pd.read_csv(stress_path)
            except Exception:
                stress_df = pd.DataFrame()
            if not stress_df.empty:
                top_row = stress_df.iloc[0].to_dict()
                du.print_info(
                    "[MENU] Best stress profile: "
                    f"unknown_cut={top_row.get('unknown_cut')} "
                    f"mapped_cut={top_row.get('mapped_cut')} "
                    f"generic_cut={top_row.get('generic_cut')} "
                    f"effective_share={top_row.get('effective_inclusion_share')}"
                )
    return 0


def print_parser_onboarding_candidates(*, limit: int | None = None, mode: str | None = None) -> int:
    """Print parser onboarding queue in a compact operator view."""
    candidates_df = build_parser_onboarding_queue(limit=None)
    du.print_section("Parser onboarding queue")
    if candidates_df.empty:
        du.print_info("[MENU] No high-priority parser onboarding candidates in latest CSV snapshots.")
        return 0
    du.print_stat("Candidates in queue", int(len(candidates_df)))
    top_vendor = str(candidates_df.iloc[0].get("vendor_column", "") or "").strip()
    top_cov = candidates_df.iloc[0].get("coverage_pct", "—")
    if top_vendor:
        du.print_info(f"Highest-priority candidate: {top_vendor} ({top_cov}% coverage)")
    du.print_info(
        "Prioritize selected or trusted vendors first, then high-coverage unmapped vendors with stable label behavior."
    )
    row_limit = limit or mode_max_rows(compact=10, detailed=15, debug=20, mode=mode)
    du.print_table(
        candidates_df.head(row_limit),
        title=f"Top {row_limit} parser onboarding candidates",
        show_index=False,
    )
    if row_limit < len(candidates_df):
        du.print_info(
            "Show all path: switch to detailed/debug mode for a larger default view, or use Top unmapped vendors for broader backlog context."
        )
    return 0


def print_selected_vendors_for_latest_run(*, limit: int | None = None, mode: str | None = None) -> int:
    """Print selected-vendor signal quality for the latest run in a compact form."""
    du.print_section("Selected vendor signal quality")
    _print_manifest_vendor_context()
    resolved = resolve_vendor_gate_pre_gate_csv()
    scores_path = resolved if resolved is not None else Path()
    scores_df = read_csv(scores_path)
    if scores_df.empty:
        du.print_info("[MENU] No selected-vendor CSV snapshot is available for the latest run.")
        return 0
    if "Vendor" in scores_df.columns:
        preview = ", ".join(str(v) for v in scores_df.head(3)["Vendor"].tolist())
        if preview:
            du.print_info(f"Start with these selected vendors: {preview}")
    if "Vendor Category" in scores_df.columns:
        categories = scores_df["Vendor Category"].astype(str).value_counts().to_dict()
        preview = ", ".join(f"{k}={v}" for k, v in list(categories.items())[:4])
        if preview:
            du.print_info(f"Selected-vendor signal mix: {preview}")
    if "Family Match Accuracy (%)" in scores_df.columns:
        try:
            fam_match = pd.to_numeric(scores_df["Family Match Accuracy (%)"], errors="coerce")
            mean_score = float(fam_match.mean())
            quality_band = "strong" if mean_score >= 20.0 else "weak"
            du.print_stat("Mean family match accuracy", f"{mean_score:.2f}% ({quality_band} signal)")
            if quality_band == "weak":
                du.print_note("Action: treat selected-vendor family-level claims as provisional; prioritize parser onboarding and label-pattern validation first.")
        except Exception:
            pass
    du.print_info(
        "Why selected differs from parser-mapped: selected vendors are leakage-safe run inputs; parser-mapped is broader parser availability over observed vendors."
    )
    row_limit = limit or mode_max_rows(compact=5, detailed=10, debug=20, mode=mode)
    du.print_table(
        scores_df.head(row_limit),
        title=f"Top {row_limit} selected vendors by signal quality",
        show_index=False,
    )
    return 0


def print_workbook_requirements() -> int:
    """Explain workbook requirements without implying CSV snapshots are missing."""
    state = get_parser_summary_state()
    du.print_section("Workbook requirements")
    _print_workbook_missing_guidance(csv_ready=bool(state.get("csv_ready")))
    if state.get("onboarding_candidate_count"):
        du.print_info(
            f"{int(state['onboarding_candidate_count'])} parser onboarding candidates are still reviewable from CSV snapshots."
        )
    if bool(state.get("csv_ready")):
        du.print_info("[MENU] CSV snapshots available.")
    du.print_info("[MENU] Workbook drill-down is optional unless you need single-vendor parser debugging.")
    return 0


def print_parser_export_paths() -> int:
    """Show operator-facing export paths for parser diagnostics artifacts."""
    state = get_parser_summary_state()
    if str(state.get("display_mode", "compact")) == "compact":
        du.print_note("Export paths are hidden in compact mode. Switch to detailed/debug for raw parser artifact paths.")
        return 0
    du.print_section("Parser export paths")
    du.print_stat("CSV coverage snapshot", str(state.get("coverage_csv_path") or "missing"))
    du.print_stat("Parser onboarding snapshot", str(state.get("candidates_csv_path") or "missing"))
    du.print_stat("Selected-vendor snapshot", str(state.get("scores_csv_path") or "missing"))
    return 0


def _print_workbook_missing_guidance(*, csv_ready: bool = False) -> None:
    """Print concise workbook-missing guidance with next step."""
    du.print_subheader("Workbook Required")
    du.print_stat("CSV snapshots", "Available" if csv_ready else "Unavailable")
    du.print_stat("Workbook drill-down", "Unavailable")
    du.print_stat("Blocked action", "Single-vendor parser drill-down")
    du.print_stat("Next step", "Generate workbook-backed enriched matrix export")
    print("")


def _print_manifest_vendor_context() -> None:
    """Print last-run vendor constraint context from manifest."""
    manifest = read_latest_manifest()
    if not manifest:
        return
    run_id = str(manifest.get("run_id", "unknown"))
    selected_count = manifest.get("selected_vendor_count")
    constrained = bool(manifest.get("vendor_constrained_run_flag", False))
    if selected_count is None:
        try:
            query = """
                SELECT run_id, selected_vendor_count, vendor_constrained_run_flag
                FROM analysis_run
                ORDER BY created_at_utc DESC
                LIMIT 1
            """
            db_df = db_engine.execute_query(query, fetch=True, as_dataframe=True)
            if isinstance(db_df, pd.DataFrame) and not db_df.empty:
                run_id = str(db_df.iloc[0].get("run_id", run_id))
                selected_count = int(db_df.iloc[0].get("selected_vendor_count", 0))
                constrained = bool(int(db_df.iloc[0].get("vendor_constrained_run_flag", 0)))
        except Exception:
            pass
    du.print_section("Latest Run Vendor Context")
    du.print_stat("Run ID", run_id)
    du.print_stat("Selected Vendor Count", selected_count if selected_count is not None else "n/a")
    du.print_stat("Vendor Constrained", constrained)
    if constrained:
        du.print_warning(
            "[MENU] Last run is vendor-constrained; treat vendor-only findings as sensitivity/limitations."
        )


__all__ = [
    "print_compact_vendor_coverage_snapshot",
    "print_parser_diagnostics_state",
    "print_parser_export_paths",
    "print_parser_onboarding_candidates",
    "print_selected_vendors_for_latest_run",
    "print_top_unmapped_vendors",
    "print_workbook_requirements",
]
