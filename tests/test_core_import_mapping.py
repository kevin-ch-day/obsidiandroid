"""Deterministic, source-free tests for the Core import planning boundary."""

from __future__ import annotations

from hashlib import sha256
import json

import pytest

from obsidiandroid.core_migration.importer import validate_import_plan
from obsidiandroid.core_migration.mapping import CoreImportError, build_import_plan, destination_reconciliation_contract


def _plan() -> dict:
    return build_import_plan(
        run={"run_id": "synthetic-run", "profile_id": "synthetic-profile", "created_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64},
        snapshots=[{"run_id": "synthetic-run", "extracted_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64, "snapshot_row_count": 1}],
        samples=[{"run_id": "synthetic-run", "sha256": "b" * 64, "sample_id": 1, "family_canonical": "synthetic", "type_slug": "test"}],
        artifacts=[{"run_id": "synthetic-run", "artifact_key": "missing", "artifact_path": "/not/a/real/file", "artifact_sha256": "c" * 64}],
        conflicts=[{"run_id": "synthetic-run", "sha256": "b" * 64, "conflict_type": "family", "observed_values": "a|b"}],
    )


def test_plan_is_deterministic_and_orders_parent_before_children() -> None:
    first = _plan()
    second = _plan()
    assert first["plan_sha256"] == second["plan_sha256"]
    assert first["import_order"][:3] == ["core_profile", "core_source_snapshot", "core_run"]
    assert first["expected_counts"] == {"core_profile": 1, "core_source_snapshot": 1, "core_run": 1, "core_run_sample": 1, "core_artifact": 1, "core_quality_finding": 1}
    assert first["destination_rows"]["core_artifact"][0]["availability_status"] == "legacy_path_unresolved"
    assert first["destination_rows"]["core_quality_finding"][0]["resolution_status"] == "open"


def test_child_run_mismatch_and_duplicate_sample_are_rejected() -> None:
    with pytest.raises(CoreImportError, match="does not match"):
        build_import_plan(run={"run_id": "r", "profile_id": "p"}, snapshots=[], samples=[{"run_id": "other", "sha256": "a" * 64}], artifacts=[], conflicts=[])
    with pytest.raises(CoreImportError, match="Duplicate"):
        build_import_plan(run={"run_id": "r", "profile_id": "p"}, snapshots=[], samples=[{"run_id": "r", "sha256": "a" * 64}, {"run_id": "r", "sha256": "a" * 64}], artifacts=[], conflicts=[])


def test_selection_rule_disagreement_and_cross_state_are_rejected() -> None:
    with pytest.raises(CoreImportError, match="selection_rule_version"):
        build_import_plan(
            run={"run_id": "r", "profile_id": "p", "selection_rule_version": "run-v1"},
            snapshots=[{"run_id": "r", "selection_rule_version": "snapshot-v2"}], samples=[], artifacts=[], conflicts=[],
        )
    plan = _plan()
    plan["destination_rows"]["core_run"][0]["run_kind"] = "ledger_only"
    plan["destination_reconciliation"] = destination_reconciliation_contract(plan["destination_rows"])
    canonical = dict(plan)
    canonical.pop("plan_sha256", None)
    plan["plan_sha256"] = sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    with pytest.raises(CoreImportError, match="contradicts run kind"):
        validate_import_plan(plan)


def test_phase2c_execution_contract_requires_frozen_extract_and_migration_identities() -> None:
    with pytest.raises(CoreImportError, match="source_extract_manifest_sha256"):
        build_import_plan(
            run={"run_id": "r", "profile_id": "p"}, snapshots=[], samples=[], artifacts=[], conflicts=[],
            phase2c_execution_contract={
                "source_extract_manifest_sha256": "not-a-hash",
                "repository_commit": "a" * 40,
                "migration_checksums": {"0001": "a" * 64, "0002": "b" * 64},
            },
        )
    with pytest.raises(CoreImportError, match="0001 and 0002"):
        build_import_plan(
            run={"run_id": "r", "profile_id": "p"}, snapshots=[], samples=[], artifacts=[], conflicts=[],
            phase2c_execution_contract={
                "source_extract_manifest_sha256": "a" * 64,
                "repository_commit": "b" * 40,
                "migration_checksums": {"0001": "c" * 64},
            },
        )
