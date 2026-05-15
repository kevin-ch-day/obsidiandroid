"""Parser diagnostics actions for operator-facing menus."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.vendors.parsing import vendor_parser_map
from obsidiandroid.vendors import ParsedLabelMetadata, parse_generic_classification

from .vendor_parser_state import get_parser_summary_state, read_csv, resolve_vendor_gate_pre_gate_csv, resolve_vendor_parser_coverage_candidates_csv, resolve_vendor_parser_coverage_csv
from .vendor_diagnostics_views import print_parser_diagnostics_state
from .workbook_loader import load_enriched_matrix_for_menu
from ..ui import display as du
from ..ui import menu as mu


def _print_workbook_missing_guidance(*, csv_ready: bool = False) -> None:
    du.print_subheader("Workbook Required")
    du.print_stat("CSV snapshots", "Available" if csv_ready else "Unavailable")
    du.print_stat("Workbook drill-down", "Unavailable")
    du.print_stat("Blocked action", "Single-vendor parser drill-down")
    du.print_stat("Next step", "Generate workbook-backed enriched matrix export")
    print("")


def _print_parser_coverage_snapshot() -> None:
    resolved = resolve_vendor_parser_coverage_csv()
    coverage_path = resolved if resolved is not None else Path()
    coverage_df = read_csv(coverage_path)
    if coverage_df.empty:
        du.print_warning("[MENU] Parser coverage snapshot not found. Run a full pipeline/vendor parse first.")
        return
    rows_total = int(len(coverage_df))
    mapped_count = int(pd.to_numeric(coverage_df.get("parser_mapped", 0), errors="coerce").fillna(0).sum())
    unmapped_count = max(0, rows_total - mapped_count)
    mapped_cov_mean = float(
        pd.to_numeric(coverage_df.loc[coverage_df["parser_mapped"] == 1, "coverage_pct"], errors="coerce").fillna(0.0).mean()
    ) if mapped_count else 0.0
    unmapped_cov_mean = float(
        pd.to_numeric(coverage_df.loc[coverage_df["parser_mapped"] == 0, "coverage_pct"], errors="coerce").fillna(0.0).mean()
    ) if unmapped_count else 0.0
    du.print_section("Parser Coverage Quality")
    du.print_stat("Vendor Columns Observed", rows_total)
    du.print_stat("Mapped Columns", mapped_count)
    du.print_stat("Unmapped Columns", unmapped_count)
    du.print_stat("Mapped Avg Coverage %", f"{mapped_cov_mean:.2f}")
    du.print_stat("Unmapped Avg Coverage %", f"{unmapped_cov_mean:.2f}")


def _print_onboarding_candidates() -> None:
    resolved = resolve_vendor_parser_coverage_candidates_csv()
    candidates_path = resolved if resolved is not None else Path()
    candidates_df = read_csv(candidates_path)
    du.print_section("Parser Onboarding Candidates")
    if candidates_df.empty:
        du.print_info("[MENU] No high-coverage unmapped candidate vendors in latest snapshot.")
        return
    du.print_table(candidates_df.head(12), title="High-priority parser onboarding candidates", show_index=False)


def _print_pre_gate_vendor_scores() -> None:
    resolved = resolve_vendor_gate_pre_gate_csv()
    scores_path = resolved if resolved is not None else Path()
    scores_df = read_csv(scores_path)
    if scores_df.empty:
        du.print_warning("[MENU] Pre-gate vendor score table not found for latest run.")
        return
    du.print_table(scores_df.head(10), title="Top 10 vendors by pre-gate leakage-safe score", show_index=False)


def _coerce_parsed_output(parsed: Any) -> dict[str, Any]:
    if isinstance(parsed, ParsedLabelMetadata):
        return parsed.to_dict()
    if isinstance(parsed, dict):
        try:
            return ParsedLabelMetadata.from_dict(parsed).to_dict()
        except Exception:
            return {
                "family": str(parsed.get("family", "unknown")).strip().lower(),
                "malware_type": str(parsed.get("malware_type", "unknown")).strip().lower(),
                "threat_class": str(parsed.get("threat_class", "unknown")).strip().lower(),
                "platform": str(parsed.get("platform", "unknown")).strip().lower(),
                "variant": str(parsed.get("variant", "unknown")).strip().lower(),
            }
    return {
        "family": "unknown",
        "malware_type": "unknown",
        "threat_class": "unknown",
        "platform": "unknown",
        "variant": "unknown",
    }


def validate_parser_columns_from_latest_export() -> int:
    """Validate parser map coverage using latest AV export columns if available."""
    du.print_section("Vendor Parser Coverage Check")
    print_parser_diagnostics_state()
    df = load_enriched_matrix_for_menu()
    if df is None:
        cov_path = resolve_vendor_parser_coverage_csv()
        coverage_df = read_csv(cov_path) if cov_path is not None else pd.DataFrame()
        if coverage_df.empty:
            _print_workbook_missing_guidance(csv_ready=False)
            du.print_warning("[MENU] No parser coverage snapshot is available yet.")
            return 1
        du.print_note("[MENU] Workbook unavailable. Falling back to latest diagnostics snapshots.")
        _print_parser_coverage_snapshot()
        _print_onboarding_candidates()
        _print_pre_gate_vendor_scores()
        return 0
    missing = vendor_parser_map.validate_vendor_parser_columns(av_columns=list(df.columns), verbose=True)
    if missing:
        du.print_warning(f"[MENU] Missing parser columns: {len(missing)}")
    else:
        du.print_success("[MENU] All registered parser vendors were matched.")
    _print_parser_coverage_snapshot()
    _print_onboarding_candidates()
    _print_pre_gate_vendor_scores()
    return 0


def run_single_vendor_parser_check() -> int:
    """Run one parser against latest enriched matrix column and print quality stats."""
    enriched_df = load_enriched_matrix_for_menu(emit_warnings=False)
    if enriched_df is None:
        du.print_section("Vendor parser drill-down")
        state = get_parser_summary_state()
        du.print_stat("Parser health", str(state.get("status", "unknown")))
        du.print_stat("Workbook drill-down", "Unavailable")
        du.print_stat("CSV snapshots", "Available" if bool(state.get("csv_ready")) else "Unavailable")
        du.print_stat(
            "Onboarding queue",
            state.get("onboarding_candidate_count") if state.get("onboarding_candidate_count") is not None else "n/a",
        )
        if state.get("top_candidates_preview"):
            du.print_info(
                "Open first: parser onboarding candidates for "
                + ", ".join(str(v) for v in state["top_candidates_preview"])
            )
        du.print_warning("Workbook drill-down unavailable. Single-vendor parser debugging requires the workbook-backed enriched matrix.")
        du.print_info("Coverage and snapshot views remain available from latest diagnostics CSV exports.")
        return 1

    parser_map = vendor_parser_map.get_vendor_parser_map()
    vendors = sorted(parser_map.keys())
    selection = mu.display_menu(vendors, title="Select Vendor Parser to Evaluate")
    if selection == 0:
        return 0

    vendor_name = vendors[selection - 1]
    parser_meta = parser_map.get(vendor_name, {})
    parser_fn = parser_meta.get("func")
    if not callable(parser_fn):
        du.print_error(f"[MENU] Parser function not found for vendor '{vendor_name}'.")
        return 1

    resolved_vendor_column = vendor_parser_map.resolve_vendor_column_name(vendor_name, list(enriched_df.columns))
    if not resolved_vendor_column:
        du.print_warning(
            f"[MENU] Column '{vendor_name}' missing in enriched matrix; "
            "using generic parser diagnostics is not possible for this run."
        )
        return 1

    series = enriched_df[resolved_vendor_column].dropna().astype(str).str.strip()
    series = series[series != ""]
    if series.empty:
        du.print_warning(f"[MENU] No labels available for vendor '{vendor_name}'.")
        return 1

    parsed_rows: list[dict[str, Any]] = []
    parser_errors = 0
    for label in series:
        try:
            parsed = parser_fn(label, None)
        except TypeError:
            parsed = parser_fn(label)
        except Exception:
            parser_errors += 1
            try:
                parsed = parse_generic_classification(label, None)
            except Exception:
                continue
        parsed_rows.append(_coerce_parsed_output(parsed))

    if not parsed_rows:
        du.print_error(f"[MENU] Parser produced no usable rows for '{vendor_name}'.")
        return 1

    out_df = pd.DataFrame(parsed_rows)
    sample_total = len(out_df)
    known_family = out_df["family"].fillna("").str.lower().isin({"", "unknown", "generic", "trojan", "malware"}).eq(False).sum()
    unknown_pct = round((1.0 - (known_family / sample_total)) * 100.0, 2)

    du.print_section(f"Vendor Parser Diagnostic: {vendor_name}")
    du.print_stat("Parsed Rows", sample_total)
    du.print_stat("Parser Errors", parser_errors)
    du.print_stat("Known Family Rows", int(known_family))
    du.print_stat("Unknown/Generic %", f"{unknown_pct:.2f}%")
    du.print_table(out_df.value_counts("threat_class").reset_index(name="count").head(10), title=f"{vendor_name} threat_class top values", show_index=False)
    du.print_table(out_df.value_counts("malware_type").reset_index(name="count").head(10), title=f"{vendor_name} malware_type top values", show_index=False)
    du.print_table(out_df.value_counts("family").reset_index(name="count").head(15), title=f"{vendor_name} parsed family top values", show_index=False)
    return 0


__all__ = [
    "run_single_vendor_parser_check",
    "validate_parser_columns_from_latest_export",
]
