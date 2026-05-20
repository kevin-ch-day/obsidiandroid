"""Tests for the dry-run output retention audit."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.tools import output_retention_audit as ora


def _write_manifest(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_parse_run_record_reads_manifest_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "output" / "runs" / "20260519T182900Z__b22294"
    _write_manifest(
        run_dir,
        {
            "run_id": "20260519T182900Z__b22294",
            "profile_id": "malicious_temporal_stability_locked",
            "run_status": "complete",
            "publication_ready_status": "PASS",
            "evidence_mode": True,
            "timestamp_utc": "2026-05-19T18:29:00.573052+00:00",
            "profile_params": {
                "description": "Cohort-locked multi-type malicious corpus contract anchored to a preserved baseline run.",
            },
        },
    )

    record = ora.parse_run_record(run_dir)

    assert record.run_id == "20260519T182900Z__b22294"
    assert record.profile_id == "malicious_temporal_stability_locked"
    assert record.status_bucket == "complete/pass"
    assert record.mode == "evidence/publication"
    assert record.timestamp_utc is not None


def test_classify_runs_protects_latest_and_promoted_and_evidence_pass(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    runs_dir = output_dir / "runs"
    diagnostics_dir = output_dir / "diagnostics"
    promoted_dir = output_dir / "promoted"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    promoted_dir.mkdir(parents=True, exist_ok=True)

    run_latest = runs_dir / "20260519T071502Z__c09270"
    _write_manifest(
        run_latest,
        {
            "run_id": "20260519T071502Z__c09270",
            "profile_id": "malicious_temporal_stability_locked",
            "run_status": "complete",
            "publication_ready_status": "PASS",
            "evidence_mode": True,
            "timestamp_utc": "2026-05-19T07:15:02.442806+00:00",
        },
    )
    run_older = runs_dir / "20260519T070012Z__0e798e"
    _write_manifest(
        run_older,
        {
            "run_id": "20260519T070012Z__0e798e",
            "profile_id": "malicious_temporal_stability_locked",
            "run_status": "complete",
            "publication_ready_status": "PASS",
            "evidence_mode": True,
            "timestamp_utc": "2026-05-19T07:00:12.429390+00:00",
        },
    )
    (diagnostics_dir / "latest_run_pointer.json").write_text(
        json.dumps({"run_id": "20260519T071502Z__c09270"}),
        encoding="utf-8",
    )
    (promoted_dir / "latest_run_manifest.json").write_text(
        json.dumps({"run_id": "20260519T071502Z__c09270"}),
        encoding="utf-8",
    )

    audit = ora.audit_output_retention(
        output_dir,
        policy=ora.RetentionPolicy(recent_days=0, keep_last_full_per_profile=0, keep_last_dev_runs_total=0),
        now_utc=ora._parse_iso_utc("2026-05-30T00:00:00+00:00"),
    )

    classes = {record.run_id: record.retention_class for record in audit.run_records}
    assert classes["20260519T071502Z__c09270"] == "protected"
    assert classes["20260519T070012Z__0e798e"] == "protected"


def test_classify_runs_marks_old_dev_smoke_complete_as_disposable(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    run_dir = output_dir / "runs" / "20260515T203118Z__cbe82d"
    _write_manifest(
        run_dir,
        {
            "run_id": "20260515T203118Z__cbe82d",
            "run_status": "complete",
            "evidence_mode": False,
            "timestamp_utc": "2026-05-15T20:31:18.752751+00:00",
            "profile_params": {
                "description": "Ultra-fast smoke profile for rapid CLI and pipeline sanity checks.",
            },
        },
    )

    audit = ora.audit_output_retention(
        output_dir,
        policy=ora.RetentionPolicy(recent_days=1, keep_last_full_per_profile=0, keep_last_dev_runs_total=0),
        now_utc=ora._parse_iso_utc("2026-05-19T00:00:00+00:00"),
    )

    assert audit.run_records[0].retention_class == "disposable"
    assert "older dev/smoke run outside default keep window" in audit.run_records[0].reasons


def test_missing_metadata_is_unknown_not_disposable(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    run_dir = output_dir / "runs" / "r1"
    run_dir.mkdir(parents=True, exist_ok=True)

    audit = ora.audit_output_retention(output_dir, now_utc=ora._parse_iso_utc("2026-05-19T00:00:00+00:00"))

    assert audit.run_records[0].retention_class == "unknown"
    assert "missing metadata" in audit.run_records[0].reasons


def test_main_dry_run_does_not_delete_files(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "output"
    diagnostics_dir = output_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / "runs" / "20260515T203118Z__cbe82d"
    _write_manifest(
        run_dir,
        {
            "run_id": "20260515T203118Z__cbe82d",
            "run_status": "complete",
            "evidence_mode": False,
            "timestamp_utc": "2026-05-15T20:31:18.752751+00:00",
            "profile_params": {
                "description": "Ultra-fast smoke profile for rapid CLI and pipeline sanity checks.",
            },
        },
    )
    payload_path = run_dir / "payload.txt"
    payload_path.write_text("x", encoding="utf-8")

    rc = ora.main(
        [
            "--output-dir",
            str(output_dir),
            "--recent-days",
            "1",
            "--keep-last-full-per-profile",
            "0",
            "--keep-last-dev-runs-total",
            "0",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "Output Retention Audit (dry-run)" in out
    assert "Disposable candidates" in out
    assert payload_path.exists()

