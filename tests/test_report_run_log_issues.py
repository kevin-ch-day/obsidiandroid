from __future__ import annotations

import json
from pathlib import Path

from scripts.diagnostics import report_run_log_issues as report_mod


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
    report = report_mod.build_report(
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

    monkeypatch.setattr(report_mod, "diagnostics_root", lambda: output_diag)
    monkeypatch.setattr(report_mod, "project_logs_root", lambda: logs_root)
    out_path = tmp_path / "out.md"

    monkeypatch.setattr("sys.argv", ["report_run_log_issues.py", "--md-out", str(out_path)])
    exit_code = report_mod.main()

    assert exit_code == 0
    text = out_path.read_text(encoding="utf-8")
    assert run_id in text
    assert "smote_enabled_evidence_mode" in text
    assert "cohort_lock_drift" in text
    assert "raw_authority_conflict" in text
    assert "temporal_split_caveat" in text
