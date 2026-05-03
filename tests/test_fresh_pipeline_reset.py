"""Tests for destructive output reset helper."""

from __future__ import annotations

from pathlib import Path

from scripts import fresh_pipeline_reset as fpr


def test_wipe_preserves_main_workbook(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    (root / "diagnostics").mkdir()
    log = root / "diagnostics" / "pipeline_events.jsonl"
    log.write_text("{}", encoding="utf-8")
    wb = root / "obsidiandroid_outputs.xlsx"
    wb.write_bytes(b"x")

    fpr.wipe_output_directory(root, apply=True, purge_workbooks=False)

    assert not log.exists()
    assert wb.is_file()


def test_wipe_optional_workbook_purge(tmp_path: Path) -> None:
    root = tmp_path / "out2"
    root.mkdir()
    (root / "runs").mkdir()
    wb = root / "obsidiandroid_outputs.xlsx"
    wb.write_bytes(b"x")

    fpr.wipe_output_directory(root, apply=True, purge_workbooks=True)

    assert not wb.exists()
    runs = fpr._subdir_map(root)["runs"]
    assert runs.is_dir()
    assert not any(runs.iterdir())
