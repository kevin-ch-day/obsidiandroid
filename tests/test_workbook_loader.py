"""Tests for consolidated workbook loader path resolution."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config

from obsidiandroid.cli.menu import workbook_loader


def test_load_enriched_matrix_for_menu_reads_reports_workbook(monkeypatch, tmp_path: Path) -> None:
    """Workbook loader should search the configured reports root, not only ./output."""
    output_root = tmp_path / "output"
    reports_dir = output_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "CONSOLIDATED_EXCEL_FILENAME", "obsidiandroid_outputs.xlsx", raising=False)

    workbook_path = reports_dir / "obsidiandroid_outputs.xlsx"
    manifest_df = pd.DataFrame(
        {
            "sheet_alias": ["av_enriched"],
            "logical_name": ["av_pipeline_outputs__enriched_latest"],
        }
    )
    enriched_df = pd.DataFrame({"sample_id": [1], "vendor_a": ["Trojan"]})
    with pd.ExcelWriter(workbook_path) as writer:
        manifest_df.to_excel(writer, sheet_name="__manifest__", index=False)
        enriched_df.to_excel(writer, sheet_name="av_enriched", index=False)

    loaded = workbook_loader.load_enriched_matrix_for_menu()

    assert loaded is not None
    assert loaded.shape == (1, 2)
    assert loaded.iloc[0]["sample_id"] == 1


def test_load_enriched_matrix_for_menu_warns_once_for_same_missing_sheet(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Workbook loader should suppress duplicate warnings for the same manifest issue."""
    output_root = tmp_path / "output"
    reports_dir = output_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "CONSOLIDATED_EXCEL_FILENAME", "obsidiandroid_outputs.xlsx", raising=False)
    monkeypatch.setattr(workbook_loader, "_LAST_WORKBOOK_LOAD_ISSUE", None, raising=False)

    workbook_path = reports_dir / "obsidiandroid_outputs.xlsx"
    manifest_df = pd.DataFrame(
        {
            "sheet_alias": ["summary"],
            "logical_name": ["run_summary_latest"],
        }
    )
    with pd.ExcelWriter(workbook_path) as writer:
        manifest_df.to_excel(writer, sheet_name="__manifest__", index=False)

    warnings: list[str] = []
    monkeypatch.setattr(workbook_loader.du, "print_warning", lambda message: warnings.append(str(message)))

    first = workbook_loader.load_enriched_matrix_for_menu()
    second = workbook_loader.load_enriched_matrix_for_menu()

    assert first is None
    assert second is None
    assert len(warnings) == 1


def test_load_enriched_matrix_for_menu_prefers_newest_run_workbook_over_stale_pointer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Workbook loader should prefer the newest run-scoped workbook over a stale promoted pointer."""
    output_root = tmp_path / "output"
    runs_dir = output_root / "runs"
    old_run = runs_dir / "20260307T213823Z__b74bdb"
    new_run = runs_dir / "20260321T134027Z__f39e96"
    old_run.mkdir(parents=True, exist_ok=True)
    new_run.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "CONSOLIDATED_EXCEL_FILENAME", "obsidiandroid_outputs.xlsx", raising=False)

    promoted_dir = output_root / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    (promoted_dir / "latest_run.txt").write_text("20260307T213823Z__b74bdb", encoding="utf-8")
    (old_run / "run_manifest.json").write_text("{}", encoding="utf-8")
    (new_run / "run_manifest.json").write_text("{}", encoding="utf-8")

    manifest_df = pd.DataFrame(
        {
            "sheet_alias": ["av_enriched"],
            "logical_name": ["av_pipeline_outputs__enriched_latest"],
        }
    )
    enriched_df = pd.DataFrame({"sample_id": [7], "vendor_a": ["Trojan"]})
    with pd.ExcelWriter(new_run / "obsidiandroid_outputs.xlsx") as writer:
        manifest_df.to_excel(writer, sheet_name="__manifest__", index=False)
        enriched_df.to_excel(writer, sheet_name="av_enriched", index=False)

    loaded = workbook_loader.load_enriched_matrix_for_menu()

    assert loaded is not None
    assert loaded.iloc[0]["sample_id"] == 7
