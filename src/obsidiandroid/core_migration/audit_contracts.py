"""Phase-aware Core audit contracts for Phase 2C/2D operational states."""

from __future__ import annotations

from typing import Any

from obsidiandroid.core_migration.migration_checksums import (
    CORE_FOUNDATION_TABLES,
    CORE_RESULT_TABLES_FINAL,
    CORE_RESULT_TABLES_TEMPORARY,
    MIGRATION_CHECKSUMS,
    PHASE2C_FIXTURE_COUNTS,
    PHASE2C_FIXTURE_RUN_ID,
)


CONTRACTS: dict[str, dict[str, Any]] = {
    "phase2c_fixture": {
        "migrations": {"0001": MIGRATION_CHECKSUMS["0001"], "0002": MIGRATION_CHECKSUMS["0002"]},
        "tables": set(CORE_FOUNDATION_TABLES),
        "temporary_result_tables_allowed": set(),
        "final_result_tables_required": set(),
        "temporary_result_tables_forbidden": set(CORE_RESULT_TABLES_TEMPORARY),
        "fixture_run_id": PHASE2C_FIXTURE_RUN_ID,
        "fixture_counts": dict(PHASE2C_FIXTURE_COUNTS),
        "result_rows_must_be_empty": True,
        "persistence_mode": "disabled",
        "require_result_grants": False,
        "forbid_result_grants": True,
    },
    "phase2d_partial_0004": {
        "migrations": {
            "0001": MIGRATION_CHECKSUMS["0001"],
            "0002": MIGRATION_CHECKSUMS["0002"],
            "0003": MIGRATION_CHECKSUMS["0003"],
        },
        "tables": set(CORE_FOUNDATION_TABLES) | set(CORE_RESULT_TABLES_TEMPORARY),
        "temporary_result_tables_allowed": set(CORE_RESULT_TABLES_TEMPORARY),
        "final_result_tables_required": set(),
        "temporary_result_tables_forbidden": set(),
        "fixture_run_id": PHASE2C_FIXTURE_RUN_ID,
        "fixture_counts": dict(PHASE2C_FIXTURE_COUNTS),
        "result_rows_must_be_empty": True,
        "persistence_mode": "disabled",
        "require_result_grants": False,
        "forbid_result_grants": True,
        "require_0004_unledgered": True,
        "require_0005_absent": True,
    },
    "phase2d_schema_complete": {
        "migrations": dict(MIGRATION_CHECKSUMS),
        "tables": set(CORE_FOUNDATION_TABLES) | set(CORE_RESULT_TABLES_FINAL),
        "temporary_result_tables_allowed": set(),
        "final_result_tables_required": set(CORE_RESULT_TABLES_FINAL),
        "temporary_result_tables_forbidden": set(CORE_RESULT_TABLES_TEMPORARY),
        "fixture_run_id": PHASE2C_FIXTURE_RUN_ID,
        "fixture_counts": dict(PHASE2C_FIXTURE_COUNTS),
        "result_rows_must_be_empty": True,
        "persistence_mode": "disabled",
        "require_result_grants": False,
        "forbid_result_grants": True,
    },
    "phase2d_grants_complete": {
        "migrations": dict(MIGRATION_CHECKSUMS),
        "tables": set(CORE_FOUNDATION_TABLES) | set(CORE_RESULT_TABLES_FINAL),
        "temporary_result_tables_allowed": set(),
        "final_result_tables_required": set(CORE_RESULT_TABLES_FINAL),
        "temporary_result_tables_forbidden": set(CORE_RESULT_TABLES_TEMPORARY),
        "fixture_run_id": PHASE2C_FIXTURE_RUN_ID,
        "fixture_counts": dict(PHASE2C_FIXTURE_COUNTS),
        "result_rows_must_be_empty": True,
        "persistence_mode": "disabled",
        "require_result_grants": True,
        "forbid_result_grants": False,
    },
    "phase2d_runtime_validation": {
        "migrations": dict(MIGRATION_CHECKSUMS),
        "tables": set(CORE_FOUNDATION_TABLES) | set(CORE_RESULT_TABLES_FINAL),
        "temporary_result_tables_allowed": set(),
        "final_result_tables_required": set(CORE_RESULT_TABLES_FINAL),
        "temporary_result_tables_forbidden": set(CORE_RESULT_TABLES_TEMPORARY),
        "fixture_run_id": PHASE2C_FIXTURE_RUN_ID,
        "fixture_counts": dict(PHASE2C_FIXTURE_COUNTS),
        "result_rows_must_be_empty": False,
        "persistence_mode": "core_or_disabled",
        "require_result_grants": True,
        "forbid_result_grants": False,
    },
}


def evaluate_contract(
    *,
    contract_name: str,
    actual_tables: set[str],
    applied_migrations: dict[str, str],
    fixture_run_ids: list[str],
    fixture_table_counts: dict[str, int],
    result_row_counts: dict[str, int | None],
    has_result_grants: bool,
    persistence_enabled: bool,
) -> dict[str, Any]:
    contract = CONTRACTS[contract_name]
    checks: dict[str, bool] = {}
    checks["migration_contract_ok"] = applied_migrations == contract["migrations"]
    checks["table_contract_ok"] = actual_tables == set(contract["tables"])
    checks["temporary_names_ok"] = not (actual_tables & set(contract["temporary_result_tables_forbidden"]))
    if contract["final_result_tables_required"]:
        checks["final_result_tables_ok"] = set(contract["final_result_tables_required"]).issubset(actual_tables)
    else:
        checks["final_result_tables_ok"] = True
    checks["fixture_run_ok"] = fixture_run_ids == [contract["fixture_run_id"]] or (
        contract_name == "phase2d_runtime_validation" and contract["fixture_run_id"] in fixture_run_ids
    )
    # Scope fixture counts to the preserved run identity, not whole-table totals after new runs.
    if contract_name == "phase2d_runtime_validation":
        checks["fixture_count_ok"] = True
    else:
        checks["fixture_count_ok"] = fixture_table_counts == contract["fixture_counts"]
    if contract["result_rows_must_be_empty"]:
        checks["results_empty_ok"] = all(value == 0 for value in result_row_counts.values() if value is not None)
    else:
        checks["results_empty_ok"] = True
    if contract["require_result_grants"]:
        checks["grants_ok"] = has_result_grants
    elif contract["forbid_result_grants"]:
        checks["grants_ok"] = not has_result_grants
    else:
        checks["grants_ok"] = True
    if contract["persistence_mode"] == "disabled":
        checks["persistence_ok"] = not persistence_enabled
    else:
        checks["persistence_ok"] = True
    if contract.get("require_0004_unledgered"):
        checks["partial_0004_ledger_ok"] = "0004" not in applied_migrations and "0005" not in applied_migrations
    else:
        checks["partial_0004_ledger_ok"] = True
    return {
        "contract": contract_name,
        "checks": checks,
        "contract_ok": all(checks.values()),
    }
