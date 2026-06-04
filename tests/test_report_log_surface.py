"""Tests for log surface inventory diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.diagnostics import report_log_surface as report_mod
from scripts.diagnostics import report_run_log_issues as issues_mod


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


def test_build_report_surfaces_warning_and_alert_counts(tmp_path: Path) -> None:
    run_id = "20260519T225430Z__797f14"
    console_log = tmp_path / f"pipeline_runtime_console_{run_id}.log"
    console_log.write_text(
        "\n".join(
            [
                "[WARNING] [COHORT_LOCK] Locked cohort drift for profile demo",
                "[WARNING] [SMOTE] Synthetic oversampling is enabled in evidence/paper mode",
                "[INFO] [SMOTE] Applied with k_neighbors=5; new size: 2664",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    pipeline_log = tmp_path / "pipeline_orchestration.log"
    pipeline_log.write_text(
        "\n".join(
            [
                "event='stage_timing' duration_sec=294.99 stage='ablation'",
                "event='stage_timing' duration_sec=43.82 stage='permission_trends'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    authority_log = tmp_path / "label_authority_alerts.log"
    authority_log.write_text(
        "\n".join(
            [
                "event='label_authority_bucket_alert'",
                "event='raw_authority_conflict'",
                "event='raw_authority_conflict'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    temporal_log = tmp_path / "temporal_readiness_alerts.log"
    temporal_log.write_text(
        "\n".join(
            [
                "event='low_authority_coverage_year'",
                "event='temporal_split_caveat'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = issues_mod.build_report(
        run_id=run_id,
        console_log=console_log,
        pipeline_log=pipeline_log,
        machine_learning_log=tmp_path / "machine_learning.log",
        authority_log=authority_log,
        temporal_log=temporal_log,
        error_log=tmp_path / "error.log",
    )
    assert "Locked cohort drift" in report
    assert "Synthetic oversampling is enabled" in report
    assert "| `ablation` | 294.99 |" in report
    assert "| `raw_authority_conflict` | 2 |" in report
    assert "| `temporal_split_caveat` | 1 |" in report
    assert "`error.log` is not present" in report


def test_main_writes_latest_run_report(monkeypatch, tmp_path: Path) -> None:
    run_id = "20260519T225430Z__797f14"
    output_diag = tmp_path / "output" / "diagnostics"
    output_diag.mkdir(parents=True, exist_ok=True)
    (output_diag / "latest_run_pointer.json").write_text(
        json.dumps({"run_id": run_id, "run_root": str(tmp_path / "output" / "runs" / run_id)}),
        encoding="utf-8",
    )
    logs_root = tmp_path / "logs"
    runtime_dir = logs_root / "runtime" / run_id
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / f"pipeline_runtime_console_{run_id}.log").write_text(
        "[WARNING] [COHORT_LOCK] Locked cohort drift for profile demo\n",
        encoding="utf-8",
    )
    (runtime_dir / "pipeline_orchestration.log").write_text(
        "\n".join(
            [
                "event='stage_timing' duration_sec=10.0 stage='samples'",
                "event='cohort_lock_drift'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (runtime_dir / "machine_learning.log").write_text(
        "\n".join(
            [
                "event='smote_enabled_evidence_mode'",
                "event='temporal_profile_non_temporal_split'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (logs_root / "label_authority_alerts.log").write_text("event='raw_authority_conflict'\n", encoding="utf-8")
    (logs_root / "temporal_readiness_alerts.log").write_text(
        "event='temporal_split_caveat'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(issues_mod, "diagnostics_root", lambda: output_diag)
    monkeypatch.setattr(issues_mod, "project_logs_root", lambda: logs_root)
    out_path = tmp_path / "out.md"

    monkeypatch.setattr("sys.argv", ["report_run_log_issues.py", "--md-out", str(out_path)])
    exit_code = issues_mod.main()

    assert exit_code == 0
    text = out_path.read_text(encoding="utf-8")
    assert run_id in text
    assert "smote_enabled_evidence_mode" in text
    assert "cohort_lock_drift" in text
    assert "raw_authority_conflict" in text
    assert "temporal_split_caveat" in text
