"""Phase 2C plans are rebuilt only from verified frozen extracts."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from obsidiandroid.core_migration.mapping import CoreImportError
from scripts.core_migration import build_phase2c_import_plan
from scripts.core_migration.build_phase2c_import_plan import build_plan_from_package
from scripts.core_migration.create_phase2c_source_extract import _write_package


def _rows() -> dict[str, list[dict]]:
    return {
        "analysis_run": [{"run_id": "20260718T032717Z__a8cf01", "profile_id": "fixture-profile", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64}],
        "analysis_snapshot": [{"run_id": "20260718T032717Z__a8cf01", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64, "snapshot_row_count": 1}],
        "analysis_snapshot_sample": [{"run_id": "20260718T032717Z__a8cf01", "sha256": "b" * 64, "sample_id": 1}],
        "analysis_artifact": [{"run_id": "20260718T032717Z__a8cf01", "artifact_key": "fixture", "artifact_path": "/fixture/artifact.csv"}],
        "snapshot_label_conflict": [],
    }


def test_phase2c_plan_binds_verified_extract_and_exact_migration_hashes(tmp_path: Path) -> None:
    package = tmp_path / "extract"
    manifest = _write_package(
        output_dir=package,
        run_id="20260718T032717Z__a8cf01",
        observed_at_utc="2026-07-19T12:00:00Z",
        source_rows=_rows(),
    )
    plan = build_plan_from_package(package, repository_commit="c" * 40)
    assert plan["phase2c_execution_contract"]["source_extract_manifest_sha256"] == manifest["extract_manifest_sha256"]
    assert plan["expected_counts"]["core_run_sample"] == 1
    assert plan["destination_reconciliation"]["core_artifact"]["row_count"] == 1


def test_phase2c_plan_rejects_a_tampered_extract_before_mapping(tmp_path: Path) -> None:
    package = tmp_path / "extract"
    _write_package(
        output_dir=package,
        run_id="20260718T032717Z__a8cf01",
        observed_at_utc="2026-07-19T12:00:00Z",
        source_rows=_rows(),
    )
    payload = package / "extracts" / "analysis_run.jsonl.gz"
    payload.write_bytes(payload.read_bytes() + b"tampered")
    with pytest.raises(CoreImportError, match="hash mismatch"):
        build_plan_from_package(package, repository_commit="c" * 40)


def test_phase2c_plan_help_does_not_evaluate_the_clean_tree_gate(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["build_phase2c_import_plan.py", "--help"])
    monkeypatch.setattr(
        build_phase2c_import_plan,
        "_repository_commit",
        lambda: pytest.fail("--help must not inspect repository state"),
    )
    with pytest.raises(SystemExit) as exited:
        build_phase2c_import_plan.main()
    assert exited.value.code == 0
