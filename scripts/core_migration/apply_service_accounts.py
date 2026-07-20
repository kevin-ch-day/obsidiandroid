#!/usr/bin/env python3
"""Create narrowly scoped local Core service accounts after explicit approval."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import secrets
import stat
from typing import Any

import mysql.connector


HOST = "localhost"
CORE = "obsidiandroid_core_prod"
EREBUS = "erebus_threat_intel_prod"
ROLES = {
    "core_migrator": "obsidiandroid_core_migrator",
    "core_writer": "obsidiandroid_core_writer",
    "core_auditor": "obsidiandroid_core_auditor",
    "erebus_reader": "obsidiandroid_erebus_reader",
}
CORE_EVIDENCE_TABLES = (
    "core_profile", "core_source_snapshot", "core_run", "core_run_sample", "core_artifact", "core_quality_finding",
)
EREBUS_SURFACES = (
    "analysis_run", "analysis_snapshot", "analysis_snapshot_sample", "analysis_artifact", "snapshot_label_conflict",
)


def _connect(option_file: Path, *, user: str | None = None, password: str | None = None, database: str | None = None):
    kwargs: dict[str, Any] = {"option_files": str(option_file), "autocommit": False}
    if user is not None:
        kwargs["user"] = user
        kwargs.pop("option_files", None)
        kwargs["host"] = "localhost"
        kwargs["password"] = password
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def _account(role: str) -> str:
    return f"'{ROLES[role]}'@'{HOST}'"


def grant_plan() -> tuple[str, ...]:
    """Return exact non-secret grants, deliberately avoiding database wildcards."""
    statements = [
        f"GRANT CREATE, ALTER, INDEX, REFERENCES ON `{CORE}`.* TO {_account('core_migrator')}",
        f"GRANT SELECT, INSERT ON `{CORE}`.`core_schema_migration` TO {_account('core_migrator')}",
        f"GRANT SELECT ON `{CORE}`.`core_run` TO {_account('core_writer')}",
    ]
    statements.extend(f"GRANT INSERT ON `{CORE}`.`{table}` TO {_account('core_writer')}" for table in CORE_EVIDENCE_TABLES)
    statements.extend(f"GRANT SELECT ON `{CORE}`.`{table}` TO {_account('core_auditor')}" for table in ("core_schema_migration", *CORE_EVIDENCE_TABLES))
    statements.extend(f"GRANT SELECT ON `{EREBUS}`.`{table}` TO {_account('erebus_reader')}" for table in EREBUS_SURFACES)
    return tuple(statements)


def _write_secret(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = "".join(f"{key}={value}\n" for key, value in values.items())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _assert_absent(cursor) -> None:
    for name in ROLES.values():
        cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE User=%s AND Host=%s", (name, HOST))
        if int(cursor.fetchone()[0]):
            raise RuntimeError(f"Refusing to alter existing account {name!r}@{HOST!r}")


def _create_accounts(cursor, passwords: dict[str, str]) -> None:
    for role, name in ROLES.items():
        lock = " ACCOUNT LOCK" if role == "core_migrator" else ""
        cursor.execute(f"CREATE USER '{name}'@'{HOST}' IDENTIFIED BY %s{lock}", (passwords[role],))


def _plugin_inventory(cursor) -> dict[str, str]:
    result: dict[str, str] = {}
    for role, name in ROLES.items():
        cursor.execute("SELECT plugin FROM mysql.user WHERE User=%s AND Host=%s", (name, HOST))
        row = cursor.fetchone()
        result[role] = str(row[0]) if row else "missing"
    return result


def _write_credential_references(secret_root: Path, passwords: dict[str, str], repo_root: Path) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for role, name in ROLES.items():
        path = secret_root / f"{role}.env"
        values = {
            "OBSIDIANDROID_DB_HOST": "localhost",
            "OBSIDIANDROID_DB_PORT": "3306",
            "OBSIDIANDROID_DB_USER": name,
            "OBSIDIANDROID_DB_PASSWORD": passwords[role],
        }
        if role == "core_writer":
            values = {
                "OBSIDIANDROID_CORE_DB_HOST": "localhost",
                "OBSIDIANDROID_CORE_DB_PORT": "3306",
                "OBSIDIANDROID_CORE_DB_USER": name,
                "OBSIDIANDROID_CORE_DB_PASSWORD": passwords[role],
                "OBSIDIANDROID_CORE_DB_NAME": CORE,
                "OBSIDIANDROID_CORE_PERSISTENCE_ENABLED": "false",
            }
        elif role == "core_auditor":
            values["OBSIDIANDROID_DB_NAME"] = CORE
        elif role == "erebus_reader":
            values["OBSIDIANDROID_DB_NAME"] = EREBUS
        _write_secret(path, values)
        records[role] = {"logical_name": f"obsidiandroid/{role}", "path": str(path), "mode": "0600", "owner": "secadmin"}
    reference = repo_root / ".env.local"
    if reference.exists():
        existing = reference.read_text(encoding="utf-8")
        if "OBSIDIANDROID_CORE_CREDENTIAL_FILE=" not in existing:
            raise RuntimeError("Refusing to modify an existing local environment file without a Core credential reference")
    else:
        _write_secret(reference, {"OBSIDIANDROID_CORE_CREDENTIAL_FILE": str(secret_root / "core_writer.env")})
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--secret-root", type=Path, default=Path.home() / ".config" / "obsidiandroid" / "core-accounts")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not args.option_file.is_file():
        raise SystemExit("Refusing: protected MariaDB administrator option file is unavailable")
    plan = {"host": HOST, "roles": ROLES, "authentication_plugin": "mysql_native_password", "migrator_locked": True, "grants": list(grant_plan())}
    if not args.apply:
        print(json.dumps({"dry_run": True, "plan": plan}, indent=2, sort_keys=True))
        return 0
    passwords = {role: secrets.token_urlsafe(32) for role in ROLES}
    connection = _connect(args.option_file)
    cursor = connection.cursor()
    created: list[str] = []
    try:
        _assert_absent(cursor)
        _write_credential_references(args.secret_root, passwords, Path.cwd())
        _create_accounts(cursor, passwords)
        for statement in grant_plan():
            cursor.execute(statement)
        connection.commit()
        created = list(ROLES)
        receipt = {
            "receipt_version": "core-service-account-grants-v1",
            "applied_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "host": HOST,
            "created_roles": created,
            "authentication_plugins": _plugin_inventory(cursor),
            "migrator_locked": True,
            "grant_statements": list(grant_plan()),
            "credential_references": _write_credential_references(args.secret_root, passwords, Path.cwd()),
            "persistence_enabled": False,
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("APPLIED roles=" + ",".join(created) + " host=" + HOST)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
