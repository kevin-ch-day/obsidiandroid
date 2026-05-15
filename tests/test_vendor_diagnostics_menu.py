"""Tests for vendor diagnostics menu fallback behavior."""

from __future__ import annotations

from pathlib import Path

import json
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
    assert any("Workbook drill-down unavailable" in message for message in warnings)
    assert any("latest diagnostics CSV exports" in message for message in infos)


def test_print_parser_diagnostics_state_reports_csv_vs_workbook_context(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_diag = out_root / "runs" / run_id / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"vendor_column": "a", "coverage_pct": 95.0, "parser_mapped": 1, "is_dynamic_generic": 0},
            {"vendor_column": "b", "coverage_pct": 80.0, "parser_mapped": 0, "is_dynamic_generic": 0},
        ]
    ).to_csv(run_diag / "vendor_parser_coverage.latest.csv", index=False)
    pd.DataFrame([{"engine_name": "a"}, {"engine_name": "b"}]).to_csv(
        run_diag / "engine_scoring_summary.csv",
        index=False,
    )
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (out_root / "diagnostics" / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": run_id, "selected_vendor_count": 1}),
        encoding="utf-8",
    )

    monkeypatch.setattr(vendor_diagnostics.run_locator, "read_latest_run_id", lambda: run_id)
    monkeypatch.setattr(vendor_diagnostics.app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(vendor_diagnostics, "load_enriched_matrix_for_menu", lambda **_kwargs: None)

    vendor_diagnostics.print_parser_diagnostics_state()
    out = capsys.readouterr().out
    assert "CSV coverage" in out
    assert "Workbook-backed enriched matrix" in out
    assert "Single-vendor drill-down requires the workbook-backed enriched matrix." in out
    assert "Observed engines" in out
    assert "Parser mapped vendors" in out
    assert "Selected vendors for latest run" in out
    assert "DB engine scoring universe" in out


def test_single_vendor_parser_check_compact_blocked_message_without_reprinting_full_state(
    monkeypatch,
    capsys,
) -> None:
    """Blocked single-vendor drill-down should show compact workbook guidance only."""
    monkeypatch.setattr(
        vendor_diagnostics,
        "load_enriched_matrix_for_menu",
        lambda **_kwargs: None,
    )

    result = vendor_diagnostics.run_single_vendor_parser_check()
    out = capsys.readouterr().out

    assert result == 1
    assert "Workbook drill-down" in out
    assert "CSV snapshots" in out
    assert "PARSER DIAGNOSTICS STATE" not in out
    assert "WORKBOOK REQUIRED" not in out
