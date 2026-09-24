"""Apply the additive assessment migration through the existing Core executor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from obsidiandroid.core_migration.executor import (
    CoreMigrationError,
    apply_migrations,
    validate_target_name,
)
from obsidiandroid.core_migration.migration_checksums import (
    MIGRATION_CHECKSUMS,
    validate_applied_version_order,
    verify_repository_migration_checksums,
)

from .schema import validate_schema


def migrate(
    *,
    database,
    connection_factory,
    migrations_dir,
    receipt_path,
    apply=False,
    allow_production=False,
):
    """Require existing Core foundation; never provision, rename, or repair it."""
    validate_target_name(database, allow_production=allow_production)
    receipt_path = Path(receipt_path)
    if receipt_path.exists():
        raise CoreMigrationError("Migration receipt already exists; choose a new path")
    verify_repository_migration_checksums(
        Path(migrations_dir), ("0001", "0002", "0003", "0006")
    )
    conn = connection_factory(database)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE()")
            if cur.fetchone()[0] != database:
                raise CoreMigrationError(
                    "Migration connection selected unexpected database"
                )
            cur.execute(
                "SELECT migration_version,migration_checksum,execution_status FROM core_schema_migration"
            )
            ledger = {row[0]: row[1:] for row in cur.fetchall()}
            validate_applied_version_order(ledger)
            for version in ("0001", "0002", "0003"):
                if ledger.get(version) != (MIGRATION_CHECKSUMS[version], "applied"):
                    raise CoreMigrationError(
                        f"Assessment migration requires verified Core {version}"
                    )
        if "0006" in ledger:
            validate_schema(conn)
    finally:
        conn.close()
    result = apply_migrations(
        target_database=database,
        migrations_dir=Path(migrations_dir),
        connection_factory=connection_factory,
        dry_run=not apply,
        allow_production=allow_production,
        receipt_path=Path(receipt_path),
        selected_versions=("0006",),
        executor_id="operational-assessment-v1",
    )
    if apply:
        conn = None
        try:
            conn = connection_factory(database)
            result["schema_validation"] = validate_schema(conn)
        except Exception:
            result["status"] = "validation_failed"
            result["partial_ddl_review_required"] = True
            raise
        finally:
            receipt_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            if conn is not None:
                conn.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--option-file", type=Path, required=True)
    parser.add_argument(
        "--migrations-dir", type=Path, default=Path("database/core_migrations")
    )
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Separate production authorization required",
    )
    args = parser.parse_args(argv)
    import mysql.connector

    def factory(database):
        return mysql.connector.connect(
            option_files=str(args.option_file),
            database=database,
            autocommit=False,
            connection_timeout=5,
        )

    try:
        result = migrate(
            database=args.database,
            connection_factory=factory,
            migrations_dir=args.migrations_dir,
            receipt_path=args.receipt,
            apply=args.apply,
            allow_production=args.allow_production,
        )
    except (ValueError, OSError, CoreMigrationError, mysql.connector.Error) as exc:
        # Connector/config errors can include sensitive connection details.
        print(
            f"Assessment migration unavailable: {type(exc).__name__} "
            f"errno={getattr(exc, 'errno', None)}; inspect target and receipt",
            file=sys.stderr,
        )
        return 2

    print(f"{result['status']}: {args.database}; receipt={args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
