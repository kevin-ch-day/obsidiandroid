"""Tests for vendor diagnostics menu fallback behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.cli.menu import vendor_diagnostics


def test_validate_parser_coverage_uses_csv_fallback_when_workbook_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Coverage menu should succeed from latest CSV snapshots without workbook exports."""
    out_dir = tmp_path / "output" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"vendor_column": "a", "coverage_pct": 95.0, "parser_mapped": 1, "is_dynamic_generic": 0},
            {"vendor_column": "b", "coverage_pct": 80.0, "parser_mapped": 0, "is_dynamic_generic": 0},
        ]
    ).to_csv(out_dir / "vendor_parser_coverage.latest.csv", index=False)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vendor_diagnostics, "load_enriched_matrix_for_menu", lambda: None)

    result = vendor_diagnostics.validate_parser_columns_from_latest_export()
    assert result == 0


def test_validate_parser_coverage_fails_when_no_workbook_and_no_csv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Coverage menu should fail cleanly when neither workbook nor CSV snapshots exist."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vendor_diagnostics, "load_enriched_matrix_for_menu", lambda: None)

    result = vendor_diagnostics.validate_parser_columns_from_latest_export()
    assert result == 1


def test_single_vendor_parser_check_reports_missing_enriched_matrix_requirement(
    monkeypatch,
) -> None:
    """Single-vendor diagnostics should explain that enriched matrix exports are required."""
    warnings: list[str] = []
    infos: list[str] = []

    monkeypatch.setattr(
        vendor_diagnostics,
        "load_enriched_matrix_for_menu",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(vendor_diagnostics.du, "print_warning", lambda message: warnings.append(str(message)))
    monkeypatch.setattr(vendor_diagnostics.du, "print_info", lambda message: infos.append(str(message)))

    result = vendor_diagnostics.run_single_vendor_parser_check()

    assert result == 1
    assert any("require the enriched AV matrix workbook" in message for message in warnings)
    assert any("latest diagnostics CSV exports" in message for message in infos)
