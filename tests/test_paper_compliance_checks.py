"""Tests for paper-mode compliance row builder."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.pipeline.manifest import paper_compliance_checks

build_paper_compliance_checks = paper_compliance_checks.build_paper_compliance_checks


def test_compliance_checks_skipped_when_paper_mode_off(tmp_path: Path) -> None:
    checks = build_paper_compliance_checks(
        paper_mode=False,
        split_hash="",
        split_audit_path="",
        duplicate_report_path="",
        duplicate_count=0,
        invalid_sha_count=0,
        vendor_gate_debug_path="",
        run_paths_manifest_path="",
        experiment_registry_path=str(tmp_path / "missing.json"),
        taxonomy_summary_path="",
        taxonomy_type_rows_evaluated=0,
    )
    assert len(checks) == 8
    assert all(c["status"] == "skipped" for c in checks)


def test_split_hash_required_when_paper_mode_on(tmp_path: Path) -> None:
    checks = build_paper_compliance_checks(
        paper_mode=True,
        split_hash="",
        split_audit_path="",
        duplicate_report_path="",
        duplicate_count=0,
        invalid_sha_count=0,
        vendor_gate_debug_path="",
        run_paths_manifest_path="",
        experiment_registry_path=str(tmp_path / "reg.json"),
        taxonomy_summary_path="",
        taxonomy_type_rows_evaluated=0,
    )
    first = checks[0]
    assert first["check_id"] == "split_hash_present"
    assert first["status"] == "fail"
