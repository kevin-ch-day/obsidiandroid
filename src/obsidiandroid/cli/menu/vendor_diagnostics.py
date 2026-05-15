"""Compatibility facade for vendor parser diagnostics menu helpers."""

from __future__ import annotations

from .vendor_diagnostics_actions import (
    run_single_vendor_parser_check,
    validate_parser_columns_from_latest_export,
)
from .vendor_diagnostics_views import (
    print_compact_vendor_coverage_snapshot,
    print_parser_diagnostics_state,
    print_parser_export_paths,
    print_parser_onboarding_candidates,
    print_selected_vendors_for_latest_run,
    print_top_unmapped_vendors,
    print_workbook_requirements,
)
from .vendor_parser_state import (
    get_parser_summary_state,
    resolve_vendor_gate_pre_gate_csv,
    resolve_vendor_parser_coverage_candidates_csv,
    resolve_vendor_parser_coverage_csv,
    resolve_vendor_strengths_weaknesses_csv,
    resolve_vendor_stress_test_csv,
)

__all__ = [
    "get_parser_summary_state",
    "print_compact_vendor_coverage_snapshot",
    "print_parser_diagnostics_state",
    "print_parser_export_paths",
    "print_parser_onboarding_candidates",
    "print_selected_vendors_for_latest_run",
    "print_top_unmapped_vendors",
    "print_workbook_requirements",
    "resolve_vendor_gate_pre_gate_csv",
    "resolve_vendor_parser_coverage_candidates_csv",
    "resolve_vendor_parser_coverage_csv",
    "resolve_vendor_strengths_weaknesses_csv",
    "resolve_vendor_stress_test_csv",
    "run_single_vendor_parser_check",
    "validate_parser_columns_from_latest_export",
]
