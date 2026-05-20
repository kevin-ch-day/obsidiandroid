"""Tests for log surface inventory diagnostics."""

from __future__ import annotations

from pathlib import Path

from scripts.diagnostics import report_log_surface as report_mod


def test_collect_log_surface_includes_rolling_and_runtime_logs(monkeypatch, tmp_path: Path) -> None:
    """Inventory should include active rolling logs and runtime tee logs."""
    logs_root = tmp_path / "logs"
    diagnostics_root = tmp_path / "output" / "diagnostics"
    (logs_root / "pipeline_orchestration.log").write_text("ok\n", encoding="utf-8")
    (logs_root / "label_authority_alerts.log").write_text("warn\n", encoding="utf-8")
    runtime = logs_root / "runtime" / "r1"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "pipeline_runtime_console_r1.log").write_text("hello\n", encoding="utf-8")
    (runtime / "ml.log").write_text("legacy\n", encoding="utf-8")

    monkeypatch.setattr(report_mod, "project_logs_root", lambda: logs_root)
    monkeypatch.setattr(report_mod, "diagnostics_root", lambda: diagnostics_root)

    items = report_mod.collect_log_surface()
    surfaces = {(item.surface, item.path.name) for item in items}
    assert ("rolling_category_log", "pipeline_orchestration.log") in surfaces
    assert ("rolling_category_log", "label_authority_alerts.log") in surfaces
    assert ("runtime_tee_log", "pipeline_runtime_console_r1.log") in surfaces
    assert ("runtime_legacy_category_log", "ml.log") in surfaces


def test_write_log_surface_report_writes_markdown_and_csv(monkeypatch, tmp_path: Path) -> None:
    """Report writer should emit inventory artifacts under diagnostics root."""
    logs_root = tmp_path / "logs"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    logs_root.mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (logs_root / "database_access.log").write_text("db\n", encoding="utf-8")

    monkeypatch.setattr(report_mod, "project_logs_root", lambda: logs_root)
    monkeypatch.setattr(report_mod, "diagnostics_root", lambda: diagnostics_dir)

    md_path, csv_path = report_mod.write_log_surface_report()
    assert md_path.exists()
    assert csv_path.exists()
    assert "database_access.log" in md_path.read_text(encoding="utf-8")


def test_write_log_surface_report_includes_targeted_alert_logs(monkeypatch, tmp_path: Path) -> None:
    """Inventory report should recognize label-authority and temporal-readiness alert logs."""
    logs_root = tmp_path / "logs"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    logs_root.mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (logs_root / "label_authority_alerts.log").write_text("warn\n", encoding="utf-8")
    (logs_root / "temporal_readiness_alerts.log").write_text("warn\n", encoding="utf-8")

    monkeypatch.setattr(report_mod, "project_logs_root", lambda: logs_root)
    monkeypatch.setattr(report_mod, "diagnostics_root", lambda: diagnostics_dir)

    md_path, _ = report_mod.write_log_surface_report()
    text = md_path.read_text(encoding="utf-8")
    assert "label_authority_alerts.log" in text
    assert "temporal_readiness_alerts.log" in text
