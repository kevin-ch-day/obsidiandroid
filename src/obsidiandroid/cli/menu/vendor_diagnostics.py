"""Vendor parser diagnostics for startup menu actions."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import json

import pandas as pd

from analysis.vendor_processing import vendor_parser_map
from analysis.vendor_processing.generic_label_parser import parse_generic_classification
from database import db_engine
from model.parsing.parsed_label_metadata import ParsedLabelMetadata
from .workbook_loader import load_enriched_matrix_for_menu
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir
from ..ui import display as du
from ..ui import menu as mu


def _diagnostics_dir() -> Path:
    """Resolve diagnostics directory under configured output root."""
    return resolve_diagnostics_dir()


def _read_csv(path: Path) -> pd.DataFrame:
    """Read CSV if it exists, otherwise return empty DataFrame."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _read_latest_manifest() -> dict[str, Any]:
    """Load latest run manifest payload when present."""
    path = _diagnostics_dir() / "run_manifest.latest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parser_diagnostics_state() -> dict[str, object]:
    """Return current parser-diagnostics capability state."""
    coverage_csv = _diagnostics_dir() / "vendor_parser_coverage.latest.csv"
    candidates_csv = _diagnostics_dir() / "vendor_parser_coverage_candidates.latest.csv"
    scores_csv = _diagnostics_dir() / "vendor_gate_top10_pre_gate.latest.csv"
    try:
        workbook_df = load_enriched_matrix_for_menu(emit_warnings=False)
    except TypeError:
        workbook_df = load_enriched_matrix_for_menu()
    workbook_ready = isinstance(workbook_df, pd.DataFrame)
    csv_ready = coverage_csv.exists()
    return {
        "workbook_ready": workbook_ready,
        "csv_ready": csv_ready,
        "coverage_csv_path": coverage_csv,
        "candidates_csv_path": candidates_csv,
        "scores_csv_path": scores_csv,
    }


def print_parser_diagnostics_state() -> None:
    """Print a compact operator-facing state block for parser diagnostics."""
    state = _parser_diagnostics_state()
    du.print_subheader("Parser Diagnostics State")
    du.print_stat(
        "Workbook-backed coverage",
        "Available" if state["workbook_ready"] else "Unavailable",
    )
    du.print_stat(
        "CSV snapshot coverage",
        "Available" if state["csv_ready"] else "Unavailable",
    )
    du.print_stat(
        "Single-vendor drill-down",
        "Available" if state["workbook_ready"] else "Blocked",
    )
    if not state["workbook_ready"]:
        du.print_note("Single-vendor diagnostics need a run completed through Vendor metadata.")
    if state["csv_ready"] and not state["workbook_ready"]:
        du.print_info("Coverage and snapshot views can still run from the latest diagnostics CSV exports.")
    print("")


def _print_workbook_missing_guidance() -> None:
    """Print concise workbook-missing guidance with next step."""
    du.print_subheader("Workbook Required")
    du.print_stat("Current capability", "Coverage and snapshots only")
    du.print_stat("Blocked action", "Single-vendor parser drill-down")
    du.print_stat("Next step", "Run pipeline through Vendor metadata")
    print("")


def _print_manifest_vendor_context() -> None:
    """Print last-run vendor constraint context from manifest."""
    manifest = _read_latest_manifest()
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


def _print_parser_coverage_snapshot() -> None:
    """Print parser coverage summary from latest exported diagnostics."""
    coverage_path = _diagnostics_dir() / "vendor_parser_coverage.latest.csv"
    coverage_df = _read_csv(coverage_path)
    if coverage_df.empty:
        du.print_warning("[MENU] Parser coverage snapshot not found. Run a full pipeline/vendor parse first.")
        return

    rows_total = int(len(coverage_df))
    mapped_count = int(pd.to_numeric(coverage_df.get("parser_mapped", 0), errors="coerce").fillna(0).sum())
    unmapped_count = max(0, rows_total - mapped_count)
    mapped_cov_mean = float(
        pd.to_numeric(
            coverage_df.loc[coverage_df["parser_mapped"] == 1, "coverage_pct"],
            errors="coerce",
        ).fillna(0.0).mean()
    ) if mapped_count else 0.0
    unmapped_cov_mean = float(
        pd.to_numeric(
            coverage_df.loc[coverage_df["parser_mapped"] == 0, "coverage_pct"],
            errors="coerce",
        ).fillna(0.0).mean()
    ) if unmapped_count else 0.0
    du.print_section("Parser Coverage Quality")
    du.print_stat("Vendor Columns Observed", rows_total)
    du.print_stat("Mapped Columns", mapped_count)
    du.print_stat("Unmapped Columns", unmapped_count)
    du.print_stat("Mapped Avg Coverage %", f"{mapped_cov_mean:.2f}")
    du.print_stat("Unmapped Avg Coverage %", f"{unmapped_cov_mean:.2f}")

    top_unmapped = coverage_df[coverage_df["parser_mapped"] == 0].copy()
    if not top_unmapped.empty:
        top_unmapped["coverage_pct"] = pd.to_numeric(top_unmapped["coverage_pct"], errors="coerce").fillna(0.0)
        du.print_table(
            top_unmapped.sort_values("coverage_pct", ascending=False).head(10),
            title="Top unmapped vendor columns by coverage",
            show_index=False,
        )


def _print_onboarding_candidates() -> None:
    """Print parser onboarding candidate vendors from latest export."""
    candidates_path = _diagnostics_dir() / "vendor_parser_coverage_candidates.latest.csv"
    candidates_df = _read_csv(candidates_path)
    du.print_section("Parser Onboarding Candidates")
    if candidates_df.empty:
        du.print_info("[MENU] No high-coverage unmapped candidate vendors in latest snapshot.")
        return
    du.print_table(
        candidates_df.head(12),
        title="High-priority parser onboarding candidates",
        show_index=False,
    )


def _print_pre_gate_vendor_scores() -> None:
    """Print top leakage-safe vendor scores prior to parser gate selection."""
    scores_path = _diagnostics_dir() / "vendor_gate_top10_pre_gate.latest.csv"
    scores_df = _read_csv(scores_path)
    if scores_df.empty:
        du.print_warning("[MENU] Pre-gate vendor score table not found for latest run.")
        return
    du.print_table(
        scores_df.head(10),
        title="Top 10 vendors by pre-gate leakage-safe score",
        show_index=False,
    )


def _coerce_parsed_output(parsed: Any) -> dict[str, Any]:
    """Normalize parser output to dictionary shape."""
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
        coverage_df = _read_csv(_diagnostics_dir() / "vendor_parser_coverage.latest.csv")
        if coverage_df.empty:
            _print_workbook_missing_guidance()
            du.print_warning("[MENU] No parser coverage snapshot is available yet.")
            return 1
        du.print_note("[MENU] Workbook unavailable. Falling back to latest diagnostics snapshots.")
        _print_parser_coverage_snapshot()
        _print_onboarding_candidates()
        _print_pre_gate_vendor_scores()
        _print_manifest_vendor_context()
        return 0

    missing = vendor_parser_map.validate_vendor_parser_columns(
        av_columns=list(df.columns),
        verbose=True,
    )
    if missing:
        du.print_warning(f"[MENU] Missing parser columns: {len(missing)}")
    else:
        du.print_success("[MENU] All registered parser vendors were matched.")
    _print_parser_coverage_snapshot()
    _print_onboarding_candidates()
    _print_pre_gate_vendor_scores()
    _print_manifest_vendor_context()
    return 0


def run_single_vendor_parser_check() -> int:
    """Run one parser against latest enriched matrix column and print quality stats."""
    enriched_df = load_enriched_matrix_for_menu(emit_warnings=False)
    if enriched_df is None:
        du.print_section("Vendor Parser Diagnostic")
        print_parser_diagnostics_state()
        _print_workbook_missing_guidance()
        du.print_warning(
            "[MENU] Single-vendor parser diagnostics require the enriched AV matrix workbook."
        )
        du.print_info(
            "[MENU] Coverage and snapshot views remain available from latest diagnostics CSV exports."
        )
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

    resolved_vendor_column = vendor_parser_map.resolve_vendor_column_name(
        vendor_name, list(enriched_df.columns)
    )
    if not resolved_vendor_column:
        du.print_warning(
            f"[MENU] Column '{vendor_name}' missing in enriched matrix; "
            "using generic parser diagnostics is not possible for this run."
        )
        return 1

    series = (
        enriched_df[resolved_vendor_column]
        .dropna()
        .astype(str)
        .str.strip()
    )
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
    known_family = out_df["family"].fillna("").str.lower().isin(
        {"", "unknown", "generic", "trojan", "malware"}
    ).eq(False).sum()
    unknown_pct = round((1.0 - (known_family / sample_total)) * 100.0, 2)

    du.print_section(f"Vendor Parser Diagnostic: {vendor_name}")
    du.print_stat("Parsed Rows", sample_total)
    du.print_stat("Parser Errors", parser_errors)
    du.print_stat("Known Family Rows", int(known_family))
    du.print_stat("Unknown/Generic %", f"{unknown_pct:.2f}%")

    du.print_table(
        out_df.value_counts("threat_class").reset_index(name="count").head(10),
        title=f"{vendor_name} threat_class top values",
        show_index=False,
    )
    du.print_table(
        out_df.value_counts("malware_type").reset_index(name="count").head(10),
        title=f"{vendor_name} malware_type top values",
        show_index=False,
    )
    du.print_table(
        out_df.value_counts("family").reset_index(name="count").head(15),
        title=f"{vendor_name} parsed family top values",
        show_index=False,
    )
    return 0
