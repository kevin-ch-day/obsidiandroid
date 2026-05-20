"""Shared readers for run-scoped cohort contract artifacts."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from obsidiandroid.common.cohort_methodology import extract_rescued_unknown_consensus, safe_int
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common import output_hygiene as oh


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    """Load a small UTF-8 CSV into row dicts."""
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def read_first_csv_row(path: Path) -> dict[str, Any]:
    """Return the first row from a UTF-8 CSV as a dict."""
    rows = read_csv_rows(path)
    return rows[0] if rows else {}


def load_cohort_contract_state(*, diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    """Read canonical cohort filter artifacts for one run into a shared structure."""
    summary_path = oh.resolve_analysis_snapshot_filter_summary_path(diagnostics_dir, run_id)
    contract_path = oh.resolve_cohort_filter_contract_path(diagnostics_dir, run_id)
    gate_counts_path = oh.resolve_cohort_gate_counts_path(diagnostics_dir, run_id)
    summary_row = read_first_csv_row(summary_path)
    contract = read_json_dict(contract_path)
    gate_rows = read_csv_rows(gate_counts_path)
    gate_by_name = {
        str(row.get("gate_name", "") or "").strip(): row
        for row in gate_rows
        if isinstance(row, dict) and str(row.get("gate_name", "") or "").strip()
    }
    membership_row = gate_by_name.get("paper_locked_snapshot_membership", {})
    min_mal_row = gate_by_name.get("min_malicious_detections", {})
    membership_mode = str(summary_row.get("mode", "") or "").strip()
    if not membership_mode and membership_row:
        membership_mode = "paper_locked_snapshot_membership"
    cohort_gates = contract.get("cohort_gates") if isinstance(contract.get("cohort_gates"), dict) else {}
    return {
        "cohort_filter_summary_path": summary_path,
        "cohort_filter_summary": summary_row,
        "cohort_filter_contract_path": contract_path,
        "cohort_filter_contract": contract,
        "cohort_gate_counts_path": gate_counts_path,
        "cohort_gate_rows": gate_rows,
        "cohort_membership_mode": membership_mode or "standard_contract_filters",
        "cohort_membership_authority_note": str(membership_row.get("details", "") or "").strip(),
        "min_malicious_detections_threshold": safe_int(cohort_gates.get("min_malicious_detections", 0), 0),
        "min_malicious_detections_rescued_unknown_consensus": extract_rescued_unknown_consensus(
            min_mal_row.get("details")
        ),
    }
