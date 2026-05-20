"""Tests for structured logging usage audit script."""

from __future__ import annotations

from pathlib import Path

from scripts.diagnostics import report_logging_engine_usage as report_mod


def test_write_logging_engine_usage_report_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    """Usage audit should emit markdown and CSV artifacts."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(report_mod, "diagnostics_root", lambda: diagnostics_dir)

    md_path, csv_path = report_mod.write_logging_engine_usage_report()
    assert md_path.exists()
    assert csv_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "Logging Engine Usage Audit" in text
    assert "failure-like event calls without explicit `level`" in text
