#!/usr/bin/env python3
"""Provision only the reviewed empty ObsidianDroid Core schema.

This command is deliberately separate from imports and the normal application
pipeline.  It requires an explicit production acknowledgement, refuses a
nonempty target, and writes a credential-free receipt.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.executor import apply_migrations


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "database" / "core_migrations"
TARGET = "obsidiandroid_core_prod"


def _connect(option_file: Path, database: str | None = None):
    kwargs: dict[str, Any] = {"option_files": str(option_file), "autocommit": False}
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def _assert_empty_target(option_file: Path) -> None:
    connection = _connect(option_file)
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (TARGET,))
        if int(cursor.fetchone()[0]) != 1:
            raise RuntimeError(f"Required Core target {TARGET!r} does not exist")
        checks = (
            ("base tables", "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'"),
            ("views", "SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA = %s"),
            ("triggers", "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = %s"),
            ("routines", "SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = %s"),
            ("events", "SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA = %s"),
        )
        for name, sql in checks:
            cursor.execute(sql, (TARGET,))
            if int(cursor.fetchone()[0]) != 0:
                raise RuntimeError(f"Refusing production provisioning: Core target already contains {name}")
    finally:
        cursor.close()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-production-schema", action="store_true")
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not args.approve_production_schema:
        raise SystemExit("Refusing: pass --approve-production-schema after separate approval")
    if not args.option_file.is_file():
        raise SystemExit("Refusing: protected local MariaDB option file is unavailable")
    _assert_empty_target(args.option_file)
    factory = lambda database: _connect(args.option_file, database)
    result = apply_migrations(
        target_database=TARGET,
        migrations_dir=MIGRATIONS,
        connection_factory=factory,
        allow_production=True,
        dry_run=False,
        executor_id="obsidiandroid-core-production-migrator",
        receipt_path=args.receipt,
    )
    print(f"PROVISIONED {TARGET}: migrations={','.join(result['applied'])} receipt={args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
