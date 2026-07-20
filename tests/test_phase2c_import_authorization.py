"""Production Core import must require a separately supplied Phase 2C record."""

from __future__ import annotations

import pytest

from obsidiandroid.core_migration.authorization import Phase2CImportAuthorization
from obsidiandroid.core_migration.importer import execute_import_plan
from obsidiandroid.core_migration.mapping import CoreImportError, build_import_plan


def _plan() -> dict:
    return build_import_plan(
        run={"run_id": "fixture-run", "profile_id": "fixture-profile", "created_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64},
        snapshots=[{"run_id": "fixture-run", "extracted_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64, "snapshot_row_count": 1}],
        samples=[{"run_id": "fixture-run", "sha256": "b" * 64, "sample_id": 1}],
        artifacts=[],
        conflicts=[],
    )


def test_production_import_is_rejected_without_an_explicit_authorization() -> None:
    with pytest.raises(CoreImportError, match="explicit Phase 2C authorization"):
        execute_import_plan(target_database="obsidiandroid_core_prod", plan=_plan(), connection_factory=None)


def test_authorization_must_match_the_exact_plan_before_connection() -> None:
    plan = _plan()
    authorization = Phase2CImportAuthorization(
        authorization_id="review-1",
        approved_by="reviewer",
        target_database="obsidiandroid_core_prod",
        source_run_id="fixture-run",
        plan_sha256="0" * 64,
    )
    with pytest.raises(CoreImportError, match="hash does not match"):
        execute_import_plan(
            target_database="obsidiandroid_core_prod",
            plan=plan,
            connection_factory=lambda _target: (_ for _ in ()).throw(AssertionError("must not connect")),
            production_authorization=authorization,
        )


def test_mutated_plan_is_rejected_before_authorization_or_connection() -> None:
    plan = _plan()
    plan["destination_rows"]["core_run"][0]["run_slot"] = "mutated-after-review"
    with pytest.raises(CoreImportError, match="SHA-256 does not match"):
        execute_import_plan(target_database="obsidiandroid_core_prod", plan=plan, connection_factory=None)


def test_authorization_is_rejected_for_a_disposable_target() -> None:
    plan = _plan()
    authorization = Phase2CImportAuthorization(
        authorization_id="review-1",
        approved_by="reviewer",
        target_database="obsidiandroid_core_prod",
        source_run_id="fixture-run",
        plan_sha256=plan["plan_sha256"],
    )
    with pytest.raises(CoreImportError, match="cannot be used for a disposable"):
        execute_import_plan(
            target_database="od_core_phase2b_validate_20260719T211000Z",
            plan=plan,
            connection_factory=None,
            production_authorization=authorization,
        )
