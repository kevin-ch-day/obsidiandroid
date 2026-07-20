"""Tests for the write-free first-wave core migration planner."""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.core_migration import dry_run_evidence_migration as planner


def test_plan_is_deterministic_and_validates_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "runs" / "fixture" / "evidence.csv"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("sample_id\n1\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    kwargs = {
        "run": {"run_id": planner.FIXTURE_RUN_ID, "profile_id": "android_malware_all_current"},
        "snapshots": [{"run_id": planner.FIXTURE_RUN_ID}],
        "samples": [{"sample_id": 1, "sha256": "a" * 64}],
        "artifacts": [{"artifact_key": "evidence", "artifact_path": str(artifact), "artifact_sha256": digest}],
        "conflicts": [],
    }
    first = planner.build_plan(**kwargs)
    second = planner.build_plan(**kwargs)

    assert first["dry_run"] is True
    assert first["plan_sha256"] == second["plan_sha256"]
    assert first["artifacts"][0]["hash_validation_status"] == "validated"
    assert first["proposed_destination_rows"]["core_run_sample"] == 1
    assert first["fixture_classification"]["publication_status"] == "NOT_APPLICABLE"


def test_missing_artifact_is_metadata_only() -> None:
    plan = planner.build_plan(
        run={"run_id": "r1"}, snapshots=[], samples=[],
        artifacts=[{"artifact_key": "gone", "artifact_path": "/missing/file", "artifact_sha256": "a" * 64}], conflicts=[],
    )
    assert plan["artifacts"][0]["availability_status"] == "missing"
    assert plan["artifacts"][0]["hash_validation_status"] == "unavailable"


def test_mutable_latest_artifact_is_not_immutable_evidence(tmp_path: Path) -> None:
    artifact = tmp_path / "evidence.latest.csv"
    artifact.write_text("mutable\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    classified = planner.classify_artifact(str(artifact), digest)

    assert classified["file_exists"] is True
    assert classified["availability_status"] == "mutable_pointer_only"
    assert classified["hash_validation_status"] == "not_applicable"
    assert classified["evidence_status"] == "mutable_pointer_only"
