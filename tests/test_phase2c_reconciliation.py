"""Read-only Phase 2C destination reconciliation checks."""

from __future__ import annotations

from datetime import datetime
import pytest

from obsidiandroid.core_migration.mapping import CoreImportError, build_import_plan, destination_reconciliation_contract
from obsidiandroid.core_migration.reconciliation import reconcile_destination_rows


def _plan() -> dict:
    return build_import_plan(
        run={"run_id": "fixture-run", "profile_id": "fixture-profile", "created_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64},
        snapshots=[{"run_id": "fixture-run", "extracted_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64, "snapshot_row_count": 1}],
        samples=[{"run_id": "fixture-run", "sha256": "b" * 64, "sample_id": 1}],
        artifacts=[],
        conflicts=[],
    )


def _observed_from_plan(plan: dict) -> dict[str, list[dict]]:
    observed: dict[str, list[dict]] = {}
    for table, contract in plan["destination_reconciliation"].items():
        observed[table] = [
            {column: row.get(column) for column in contract["columns"]}
            for row in plan["destination_rows"][table]
        ]
    return observed


def test_reconciliation_accepts_exact_projected_destination_rows() -> None:
    plan = _plan()
    result = reconcile_destination_rows(plan=plan, observed_rows=_observed_from_plan(plan))
    assert result["all_match"] is True


def test_reconciliation_detects_same_count_but_changed_content() -> None:
    plan = _plan()
    observed = _observed_from_plan(plan)
    observed["core_run_sample"][0]["observed_family"] = "tampered-family"
    result = reconcile_destination_rows(plan=plan, observed_rows=observed)
    assert result["all_match"] is False
    assert result["tables"]["core_run_sample"]["actual"]["row_count"] == 1
    assert result["tables"]["core_run_sample"]["matches"] is False


def test_reconciliation_rejects_an_incomplete_auditor_projection() -> None:
    plan = _plan()
    observed = _observed_from_plan(plan)
    del observed["core_run"][0]["source_record_hash"]
    with pytest.raises(CoreImportError, match="omitted required columns"):
        reconcile_destination_rows(plan=plan, observed_rows=observed)


def test_reconciliation_normalizes_json_datetime_and_tinyint_storage_forms() -> None:
    plan = _plan()
    observed = _observed_from_plan(plan)
    snapshot = observed["core_source_snapshot"][0]
    snapshot["source_catalogs_json"] = '{"approved_surfaces":["analysis_run"]}'
    plan["destination_rows"]["core_source_snapshot"][0]["source_catalogs_json"] = {"approved_surfaces": ["analysis_run"]}
    plan["destination_reconciliation"] = destination_reconciliation_contract(plan["destination_rows"])
    snapshot["extracted_at_utc"] = datetime(2026, 7, 19, 12, 0, 0)
    plan["destination_rows"]["core_source_snapshot"][0]["extracted_at_utc"] = "2026-07-19T12:00:00.000000Z"
    plan["destination_reconciliation"] = destination_reconciliation_contract(plan["destination_rows"])
    assert reconcile_destination_rows(plan=plan, observed_rows=observed)["all_match"] is True
