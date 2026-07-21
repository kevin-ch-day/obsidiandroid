#!/usr/bin/env python3
"""Read-only phase-aware audit of the ObsidianDroid Core schema and grants."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.audit_contracts import CONTRACTS, evaluate_contract
from obsidiandroid.core_migration.authorization import mariadb_server_attestation
from obsidiandroid.core_migration.migration_checksums import (
    CORE_RESULT_TABLES_FINAL,
    CORE_RESULT_TABLES_TEMPORARY,
    PHASE2C_FIXTURE_COUNTS,
    PHASE2C_FIXTURE_RUN_ID,
    PRODUCTION_CORE,
)


TARGET = PRODUCTION_CORE
EXPECTED_ACCOUNTS = {
    "obsidiandroid_core_migrator": {"host": "localhost", "plugin": "mysql_native_password", "locked": True},
    "obsidiandroid_core_writer": {"host": "localhost", "plugin": "mysql_native_password", "locked": False},
    "obsidiandroid_core_auditor": {"host": "localhost", "plugin": "mysql_native_password", "locked": False},
    "obsidiandroid_erebus_reader": {"host": "localhost", "plugin": "mysql_native_password", "locked": False},
}
APPROVED_RUNTIME_ACCOUNTS = {
    "obsidiandroid_pipeline_reader": {"host": "localhost", "plugin": "mysql_native_password", "locked": False},
}


def _connect(option_file: Path):
    return mysql.connector.connect(option_files=str(option_file), autocommit=False)


def _audit_hash(result: dict[str, Any]) -> str:
    return sha256(json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _rows(cursor, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def account_contract(actual_accounts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    expected = {**EXPECTED_ACCOUNTS, **APPROVED_RUNTIME_ACCOUNTS}
    return {
        "account_set_ok": set(actual_accounts) == set(expected),
        "per_account": {
            user: actual_accounts.get(user) == specification
            for user, specification in sorted(expected.items())
        },
        "phase2_service_accounts": sorted(EXPECTED_ACCOUNTS),
        "approved_runtime_accounts": sorted(APPROVED_RUNTIME_ACCOUNTS),
        "unexpected_accounts": sorted(set(actual_accounts) - set(expected)),
    }


def audit(option_file: Path, *, contract_name: str = "phase2d_schema_complete") -> dict[str, Any]:
    """Return only inventory and privilege metadata; never issue DDL or DML."""
    if contract_name not in CONTRACTS:
        raise RuntimeError(f"Unknown Core audit contract: {contract_name}")
    connection = _connect(option_file)
    cursor = connection.cursor()
    try:
        tables = _rows(
            cursor,
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
            (TARGET,),
        )
        cursor.execute("SELECT @@hostname, @@port, @@server_id, @@version, @@version_comment")
        server_values = cursor.fetchone()
        if not server_values or len(server_values) != 5:
            raise RuntimeError("MariaDB server did not return a complete Core attestation")
        server_attestation = {
            "attestation_version": "mariadb-server-attestation-v1",
            "hostname": str(server_values[0]),
            "port": int(server_values[1]),
            "server_id": int(server_values[2]),
            "version": str(server_values[3]),
            "version_comment": str(server_values[4]),
        }
        server_attestation["sha256"] = mariadb_server_attestation(
            hostname=server_attestation["hostname"],
            port=server_attestation["port"],
            server_id=server_attestation["server_id"],
            version=server_attestation["version"],
            version_comment=server_attestation["version_comment"],
        )
        migrations = _rows(
            cursor,
            f"SELECT migration_version, migration_checksum, execution_status "
            f"FROM `{TARGET}`.core_schema_migration ORDER BY migration_version",
        )
        cursor.execute(f"SELECT run_id FROM `{TARGET}`.core_run ORDER BY run_id")
        fixture_run_ids = [str(row[0]) for row in cursor.fetchall()]
        # Fixture-scoped counts for the preserved Phase 2C run only.
        fixture_counts: dict[str, int] = {}
        if PHASE2C_FIXTURE_RUN_ID in fixture_run_ids:
            cursor.execute(
                f"SELECT COUNT(*) FROM `{TARGET}`.core_run WHERE run_id=%s",
                (PHASE2C_FIXTURE_RUN_ID,),
            )
            fixture_counts["core_run"] = int(cursor.fetchone()[0])
            cursor.execute(f"SELECT COUNT(*) FROM `{TARGET}`.core_profile")
            fixture_counts["core_profile"] = int(cursor.fetchone()[0])
            cursor.execute(f"SELECT COUNT(*) FROM `{TARGET}`.core_source_snapshot")
            fixture_counts["core_source_snapshot"] = int(cursor.fetchone()[0])
            cursor.execute(
                f"SELECT COUNT(*) FROM `{TARGET}`.core_run_sample WHERE run_id=%s",
                (PHASE2C_FIXTURE_RUN_ID,),
            )
            fixture_counts["core_run_sample"] = int(cursor.fetchone()[0])
            cursor.execute(
                f"SELECT COUNT(*) FROM `{TARGET}`.core_artifact WHERE run_id=%s",
                (PHASE2C_FIXTURE_RUN_ID,),
            )
            fixture_counts["core_artifact"] = int(cursor.fetchone()[0])
            cursor.execute(
                f"SELECT COUNT(*) FROM `{TARGET}`.core_quality_finding WHERE run_id=%s",
                (PHASE2C_FIXTURE_RUN_ID,),
            )
            fixture_counts["core_quality_finding"] = int(cursor.fetchone()[0])
        else:
            fixture_counts = {table: -1 for table in PHASE2C_FIXTURE_COUNTS}

        result_counts: dict[str, int | None] = {}
        for table in sorted(set(CORE_RESULT_TABLES_FINAL) | set(CORE_RESULT_TABLES_TEMPORARY)):
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND TABLE_TYPE='BASE TABLE'",
                (TARGET, table),
            )
            if int(cursor.fetchone()[0]) != 1:
                result_counts[table] = None
                continue
            cursor.execute(f"SELECT COUNT(*) FROM `{TARGET}`.`{table}`")
            result_counts[table] = int(cursor.fetchone()[0])

        users = _rows(
            cursor,
            "SELECT u.User, u.Host, u.plugin, JSON_EXTRACT(p.Priv, '$.account_locked') "
            "FROM mysql.user u JOIN mysql.global_priv p ON p.User=u.User AND p.Host=u.Host "
            "WHERE u.User LIKE 'obsidiandroid\\_%' ESCAPE '\\\\' ORDER BY u.User, u.Host",
        )
        grants = _rows(
            cursor,
            "SELECT GRANTEE, TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE "
            "FROM information_schema.TABLE_PRIVILEGES "
            "WHERE GRANTEE LIKE '''obsidiandroid\\_%''%' ESCAPE '\\\\' "
            "ORDER BY GRANTEE, TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE",
        )
        schema_grants = _rows(
            cursor,
            "SELECT GRANTEE, TABLE_SCHEMA, PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES "
            "WHERE GRANTEE LIKE '''obsidiandroid\\_%''%' ESCAPE '\\\\' ORDER BY GRANTEE, TABLE_SCHEMA, PRIVILEGE_TYPE",
        )
        global_grants = _rows(
            cursor,
            "SELECT GRANTEE, PRIVILEGE_TYPE FROM information_schema.USER_PRIVILEGES "
            "WHERE GRANTEE LIKE '''obsidiandroid\\_%''%' ESCAPE '\\\\' ORDER BY GRANTEE, PRIVILEGE_TYPE",
        )
        routine_grants = _rows(
            cursor,
            "SELECT CONCAT(\"'\", User, \"'@'\", Host, \"'\"), Db, Routine_name, Proc_priv "
            "FROM mysql.procs_priv WHERE User LIKE 'obsidiandroid\\_%' ESCAPE '\\\\' "
            "ORDER BY User, Host, Db, Routine_name",
        )
        auxiliary = {}
        for label, sql in {
            "views": "SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA=%s",
            "triggers": "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s",
            "routines": "SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s",
            "events": "SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA=%s",
            "cross_schema_foreign_keys": (
                "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA=%s AND UNIQUE_CONSTRAINT_SCHEMA <> %s"
            ),
        }.items():
            parameters = (TARGET, TARGET) if label == "cross_schema_foreign_keys" else (TARGET,)
            cursor.execute(sql, parameters)
            auxiliary[label] = int(cursor.fetchone()[0])

        recorded = {str(version): str(checksum) for version, checksum, status in migrations if status == "applied"}
        actual_accounts = {
            str(user): {"host": str(host), "plugin": str(plugin), "locked": bool(locked)}
            for user, host, plugin, locked in users
        }
        actual_table_set = {str(row[0]) for row in tables}
        core_identity_grants = [row for row in grants if "core_" in str(row[0])]
        erebus_reader_grants = [row for row in grants if "erebus_reader" in str(row[0])]
        result_grants = [
            row
            for row in grants
            if str(row[1]) == TARGET and str(row[2]) in set(CORE_RESULT_TABLES_FINAL) | set(CORE_RESULT_TABLES_TEMPORARY)
        ]
        approved_table_schemas = {TARGET, "erebus_threat_intel_prod"}
        persistence_enabled = os.environ.get("OBSIDIANDROID_CORE_PERSISTENCE_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        contract_eval = evaluate_contract(
            contract_name=contract_name,
            actual_tables=actual_table_set,
            applied_migrations=recorded,
            fixture_run_ids=fixture_run_ids,
            fixture_table_counts=fixture_counts,
            result_row_counts=result_counts,
            has_result_grants=bool(result_grants),
            persistence_enabled=persistence_enabled,
        )
        result = {
            "target": TARGET,
            "contract": contract_name,
            "server_attestation": server_attestation,
            "expected_tables": sorted(CONTRACTS[contract_name]["tables"]),
            "actual_tables": [str(row[0]) for row in tables],
            "migrations": [{"version": v, "checksum": h, "status": s} for v, h, s in migrations],
            "fixture_run_ids": fixture_run_ids,
            "fixture_counts": fixture_counts,
            "result_counts": result_counts,
            "contract_evaluation": contract_eval,
            "table_contract_ok": contract_eval["checks"]["table_contract_ok"],
            "migration_contract_ok": contract_eval["checks"]["migration_contract_ok"],
            "fixture_contract_ok": contract_eval["checks"]["fixture_count_ok"] and contract_eval["checks"]["fixture_run_ok"],
            "results_empty": all(value == 0 for value in result_counts.values() if value is not None),
            "auxiliary_objects": auxiliary,
            "auxiliary_contract_ok": auxiliary
            == {"views": 0, "triggers": 0, "routines": 0, "events": 0, "cross_schema_foreign_keys": 0},
            "service_accounts": [
                {"user": user, "host": host, "plugin": plugin, "locked": bool(locked)}
                for user, host, plugin, locked in users
            ],
            "account_contract_ok": account_contract(actual_accounts),
            "table_grants": [{"grantee": g, "schema": s, "table": t, "privilege": p} for g, s, t, p in grants],
            "schema_grants": [{"grantee": g, "schema": s, "privilege": p} for g, s, p in schema_grants],
            "global_grants": [{"grantee": g, "privilege": p} for g, p in global_grants],
            "routine_grants": [{"grantee": g, "schema": s, "routine": r, "privilege": p} for g, s, r, p in routine_grants],
            "negative_boundaries": {
                "no_wildcard_hosts": all(str(host) == "localhost" for _, host, _, _ in users),
                "no_core_writer_migration_ledger_privilege": not any(
                    "core_writer" in str(g) and str(t) == "core_schema_migration" for g, _, t, _ in grants
                ),
                "no_core_identity_source_privilege": not any(str(s) != TARGET for g, s, _, _ in core_identity_grants),
                "no_source_reader_core_privilege": not any(str(s) == TARGET for g, s, _, _ in erebus_reader_grants),
                "no_normal_reader_core_privilege": not any(
                    "pipeline_reader" in str(g) and str(s) == TARGET for g, s, _, _ in grants
                ),
                "no_unrelated_table_privileges": all(str(s) in approved_table_schemas for _, s, _, _ in grants),
                "no_phase2a_schema_privileges": not any(str(s).startswith("od_core_phase2") for _, s, _, _ in grants)
                and not any(str(s).startswith("od_core_phase2") for _, s, _ in schema_grants),
                "source_reader_select_only": all(str(p) == "SELECT" for _, _, _, p in erebus_reader_grants),
                "normal_reader_select_only": all(
                    str(p) == "SELECT" for g, _, _, p in grants if "pipeline_reader" in str(g)
                ),
                "no_service_routine_privilege": not routine_grants,
                "no_service_global_privilege": all(str(p) == "USAGE" for _, p in global_grants),
            },
            "persistence_enabled": persistence_enabled,
        }
        result["audit_sha256"] = _audit_hash(result)
        return result
    finally:
        cursor.close()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument(
        "--contract",
        default="phase2d_schema_complete",
        choices=sorted(CONTRACTS),
        help="Phase-aware Core audit contract",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.option_file.is_file():
        raise SystemExit("Read-only audit blocked: protected MariaDB option file is unavailable")
    result = audit(args.option_file, contract_name=args.contract)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
