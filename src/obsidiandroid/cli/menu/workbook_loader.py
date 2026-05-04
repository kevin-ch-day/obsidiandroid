"""Workbook loading helpers for startup menu diagnostics."""

from __future__ import annotations

import pandas as pd

from . import run_locator
from ..ui import display as du


_LAST_WORKBOOK_LOAD_ISSUE: str | None = None

def _warn_once(issue_key: str, message: str, *, emit_warnings: bool) -> None:
    """Emit a workbook-loader warning once per distinct issue key."""
    global _LAST_WORKBOOK_LOAD_ISSUE
    if not emit_warnings:
        return
    if _LAST_WORKBOOK_LOAD_ISSUE == issue_key:
        return
    _LAST_WORKBOOK_LOAD_ISSUE = issue_key
    du.print_warning(message)


def load_enriched_matrix_for_menu(*, emit_warnings: bool = True) -> pd.DataFrame | None:
    """Load enriched AV matrix from the consolidated run workbook."""
    candidates = run_locator.candidate_workbook_paths()
    consolidated = next((path for path in candidates if path.exists()), candidates[0])
    if not consolidated.exists():
        _warn_once(
            f"missing_workbook:{consolidated}",
            f"[MENU] Missing consolidated workbook '{consolidated}'. "
            "If running in diagnostics-only mode, parser coverage can still be read "
            "from output/diagnostics/*.latest.csv when available.",
            emit_warnings=emit_warnings,
        )
        return None

    try:
        manifest_df = pd.read_excel(consolidated, sheet_name="__manifest__")
    except Exception as exc:
        _warn_once(
            f"manifest_read_failed:{consolidated}",
            f"[MENU] Failed reading manifest from '{consolidated}': {exc}",
            emit_warnings=emit_warnings,
        )
        return None

    required_cols = {"sheet_alias", "logical_name"}
    if not required_cols.issubset(manifest_df.columns):
        _warn_once(
            f"manifest_columns_missing:{consolidated}",
            "[MENU] Workbook manifest is missing required columns.",
            emit_warnings=emit_warnings,
        )
        return None

    logical = manifest_df["logical_name"].fillna("").astype(str).str.lower()
    mask = logical.str.contains("av_pipeline_outputs") & logical.str.contains("enriched")
    candidates = manifest_df[mask]
    if candidates.empty:
        logical_names = manifest_df["logical_name"].fillna("").astype(str).tolist()
        stage_hint = (
            "Run pipeline to at least 'Vendor metadata' stage so "
            "'av_pipeline_outputs__enriched_*' is exported."
        )
        _warn_once(
            f"enriched_sheet_missing:{consolidated}",
            "[MENU] No enriched matrix sheet mapping found in workbook manifest. "
            f"{stage_hint} Current manifest logical sheets: {len(logical_names)}.",
            emit_warnings=emit_warnings,
        )
        return None

    target_alias = str(candidates.iloc[-1]["sheet_alias"]).strip()
    if not target_alias:
        _warn_once(
            f"empty_sheet_alias:{consolidated}",
            "[MENU] Manifest row for enriched matrix has empty sheet alias.",
            emit_warnings=emit_warnings,
        )
        return None

    try:
        return pd.read_excel(consolidated, sheet_name=target_alias)
    except Exception as exc:
        du.print_error(f"[MENU] Failed reading enriched matrix sheet '{target_alias}': {exc}")
        return None
