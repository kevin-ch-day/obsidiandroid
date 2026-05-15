"""Parser diagnostics views for operator-facing menus."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.database import db_engine

from ..ui import display as du
from .display_mode import mode_max_rows
from .vendor_parser_state import (
    get_parser_summary_state,
    read_csv,
    read_latest_manifest,
    resolve_vendor_gate_pre_gate_csv,
    resolve_vendor_parser_coverage_candidates_csv,
    resolve_vendor_parser_coverage_csv,
    resolve_vendor_strengths_weaknesses_csv,
    resolve_vendor_stress_test_csv,
)


def print_parser_diagnostics_state(*, mode: str | None = None) -> None:
    """Print a compact operator-facing state block for parser diagnostics."""
    state = get_parser_summary_state(mode=mode)
    du.print_subheader("Parser Diagnostics State")
    du.print_stat("Display mode", str(state.get("display_mode", "compact")))
    du.print_stat("CSV snapshots", "Available" if state["csv_ready"] else "Unavailable")
    du.print_stat("Workbook drill-down", "Available" if state["workbook_ready"] else "Unavailable")
    du.print_stat("Single-vendor drill-down", "Available" if state["workbook_ready"] else "Blocked")
    if not state["workbook_ready"]:
        du.print_note("Single-vendor drill-down requires the workbook-backed enriched matrix.")
    if state["csv_ready"] and not state["workbook_ready"]:
        du.print_info("CSV snapshots available; workbook drill-down unavailable.")
    if int(state.get("observed_engines", 0) or 0) > 0:
        du.print_subheader("Vendor / engine context")
        du.print_stat("Observed engines", state["observed_engines"])
        du.print_stat("Parser mapped vendors", state["parser_mapped_vendors"])
        du.print_stat("Unmapped vendors", state["unmapped_vendors"])
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
    if state.get("recommended_open_first"):
        du.print_info(f"Open first: {state['recommended_open_first']}")
    if state.get("needs_attention"):
        du.print_note(f"Needs attention: {state['needs_attention']}")
    print("")


def print_top_unmapped_vendors(*, limit: int | None = None, mode: str | None = None) -> int:
    """Show a compact top-unmapped-vendors table from CSV snapshots."""
    cov_path = resolve_vendor_parser_coverage_csv()
    coverage_df = read_csv(cov_path) if cov_path is not None else pd.DataFrame()
    du.print_section("Top unmapped vendors")
    if coverage_df.empty:
        du.print_warning("[MENU] CSV snapshots unavailable for top unmapped vendors.")
        return 1
    top_unmapped = coverage_df[coverage_df["parser_mapped"] == 0].copy()
    if top_unmapped.empty:
        du.print_info("[MENU] No unmapped vendors found in the latest CSV snapshot.")
        return 0
    top_unmapped["coverage_pct"] = pd.to_numeric(top_unmapped.get("coverage_pct"), errors="coerce").fillna(0.0)
    row_limit = limit or mode_max_rows(compact=5, detailed=15, debug=25, mode=mode)
    du.print_table(
        top_unmapped.sort_values("coverage_pct", ascending=False).head(row_limit),
        title=f"Top {row_limit} unmapped vendors by coverage",
        show_index=False,
    )
    return 0


def print_compact_vendor_coverage_snapshot(*, mode: str | None = None) -> int:
    """Print compact stats from ``vendor_parser_coverage`` CSV (run-scoped path preferred)."""
    du.print_section("Vendor parser coverage")
    state = get_parser_summary_state(mode=mode)
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
    total = len(coverage_df)
    mapped = int(pd.to_numeric(coverage_df.get("parser_mapped", 0), errors="coerce").fillna(0).sum())
    du.print_stat("Source file", str(cov_path.resolve()))
    du.print_stat("Observed vendor columns", total)
    du.print_stat("Mapped parser columns", mapped)
    du.print_stat("Unmapped columns", max(0, total - mapped))
    if state.get("recommended_open_first"):
        du.print_info(f"Open first: {state['recommended_open_first']}")

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

    strengths_path = resolve_vendor_strengths_weaknesses_csv()
    if strengths_path is not None:
        try:
            strengths_df = pd.read_csv(strengths_path)
        except Exception:
            strengths_df = pd.DataFrame()
        if not strengths_df.empty:
            if "inclusion_status" in strengths_df.columns:
                excluded_mask = strengths_df["inclusion_status"].astype(str).str.lower() == "exclude"
            else:
                excluded_mask = pd.Series([False] * len(strengths_df), index=strengths_df.index)
            excluded = strengths_df[excluded_mask]
            if not excluded.empty:
                row_limit = mode_max_rows(compact=5, detailed=10, debug=20, mode=mode)
                du.print_table(
                    excluded[["vendor", "weakness_tags"]].head(row_limit),
                    title="Top excluded vendors (weakness tags)",
                    show_index=False,
                )
    return 0


def print_parser_onboarding_candidates(*, limit: int | None = None, mode: str | None = None) -> int:
    """Print parser onboarding candidates in a compact operator view."""
    resolved = resolve_vendor_parser_coverage_candidates_csv()
    candidates_path = resolved if resolved is not None else Path()
    candidates_df = read_csv(candidates_path)
    du.print_section("Parser onboarding candidates")
    if candidates_df.empty:
        du.print_info("[MENU] No high-priority parser onboarding candidates in latest CSV snapshots.")
        return 0
    row_limit = limit or mode_max_rows(compact=5, detailed=12, debug=20, mode=mode)
    du.print_table(
        candidates_df.head(row_limit),
        title=f"Top {row_limit} parser onboarding candidates",
        show_index=False,
    )
    return 0


def print_selected_vendors_for_latest_run(*, limit: int | None = None, mode: str | None = None) -> int:
    """Print selected-vendor context for the latest run in a compact form."""
    du.print_section("Selected vendors for latest run")
    _print_manifest_vendor_context()
    resolved = resolve_vendor_gate_pre_gate_csv()
    scores_path = resolved if resolved is not None else Path()
    scores_df = read_csv(scores_path)
    if scores_df.empty:
        du.print_info("[MENU] No selected-vendor CSV snapshot is available for the latest run.")
        return 0
    row_limit = limit or mode_max_rows(compact=5, detailed=10, debug=20, mode=mode)
    du.print_table(
        scores_df.head(row_limit),
        title=f"Top {row_limit} vendors by leakage-safe score",
        show_index=False,
    )
    return 0


def print_workbook_requirements() -> int:
    """Explain workbook requirements without implying CSV snapshots are missing."""
    state = get_parser_summary_state()
    du.print_section("Workbook requirements")
    _print_workbook_missing_guidance(csv_ready=bool(state.get("csv_ready")))
    if bool(state.get("csv_ready")):
        du.print_info("[MENU] CSV snapshots available.")
    du.print_info("[MENU] Single-vendor drill-down requires the workbook-backed enriched matrix.")
    return 0


def print_parser_export_paths() -> int:
    """Show operator-facing export paths for parser diagnostics artifacts."""
    state = get_parser_summary_state()
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
