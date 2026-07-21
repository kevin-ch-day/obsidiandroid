"""Phase-aware Core audit contract tests."""

from __future__ import annotations

from obsidiandroid.core_migration.audit_contracts import CONTRACTS, evaluate_contract
from obsidiandroid.core_migration.migration_checksums import (
    CORE_FOUNDATION_TABLES,
    CORE_RESULT_TABLES_FINAL,
    CORE_RESULT_TABLES_TEMPORARY,
    MIGRATION_CHECKSUMS,
    PHASE2C_FIXTURE_COUNTS,
    PHASE2C_FIXTURE_RUN_ID,
)


def test_partial_0004_contract_accepts_incident_shape() -> None:
    result = evaluate_contract(
        contract_name="phase2d_partial_0004",
        actual_tables=set(CORE_FOUNDATION_TABLES) | set(CORE_RESULT_TABLES_TEMPORARY),
        applied_migrations={
            "0001": MIGRATION_CHECKSUMS["0001"],
            "0002": MIGRATION_CHECKSUMS["0002"],
            "0003": MIGRATION_CHECKSUMS["0003"],
        },
        fixture_run_ids=[PHASE2C_FIXTURE_RUN_ID],
        fixture_table_counts=dict(PHASE2C_FIXTURE_COUNTS),
        result_row_counts={table: 0 for table in CORE_RESULT_TABLES_TEMPORARY},
        has_result_grants=False,
        persistence_enabled=False,
    )
    assert result["contract_ok"] is True


def test_schema_complete_rejects_temporary_names() -> None:
    result = evaluate_contract(
        contract_name="phase2d_schema_complete",
        actual_tables=set(CORE_FOUNDATION_TABLES) | set(CORE_RESULT_TABLES_FINAL) | {"core_label_contract"},
        applied_migrations=dict(MIGRATION_CHECKSUMS),
        fixture_run_ids=[PHASE2C_FIXTURE_RUN_ID],
        fixture_table_counts=dict(PHASE2C_FIXTURE_COUNTS),
        result_row_counts={table: 0 for table in CORE_RESULT_TABLES_FINAL},
        has_result_grants=False,
        persistence_enabled=False,
    )
    assert result["contract_ok"] is False
    assert result["checks"]["temporary_names_ok"] is False


def test_all_contracts_are_registered() -> None:
    assert set(CONTRACTS) == {
        "phase2c_fixture",
        "phase2d_partial_0004",
        "phase2d_schema_complete",
        "phase2d_grants_complete",
        "phase2d_runtime_validation",
    }
