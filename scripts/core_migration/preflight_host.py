#!/usr/bin/env python3
"""Read-only workstation and MariaDB capability gate for an ObsidianDroid move.

The command deliberately performs no schema, account, source-extract, Core,
or pipeline operation. It checks only the explicitly supplied MariaDB server
and local runtime prerequisites, then emits a credential-free JSON report for
the migration review record.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import sys
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

MIN_MARIADB = (10, 11)
SUPPORTED_PYTHON = ((3, 11), (3, 14))


def _canonical_hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _parse_version(value: str) -> tuple[int, int] | None:
    parts = str(value).split("-", 1)[0].split(".")
    try:
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return None


def _runtime_inventory() -> dict[str, Any]:
    python = (sys.version_info.major, sys.version_info.minor)
    return {
        "python": f"{python[0]}.{python[1]}.{sys.version_info.micro}",
        "python_supported": SUPPORTED_PYTHON[0] <= python <= SUPPORTED_PYTHON[1],
        "platform": platform.platform(),
        "required_commands": {name: bool(shutil.which(name)) for name in ("mariadb", "mariadb-dump", "sha256sum")},
    }


def _database_inventory(option_file: Path) -> dict[str, Any]:
    connection = mysql.connector.connect(option_files=str(option_file), autocommit=False)
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT @@version, @@version_comment, @@character_set_server, @@collation_server, "
            "@@time_zone, @@system_time_zone, @@lower_case_table_names, @@have_ssl, "
            "@@require_secure_transport, @@local_infile, @@event_scheduler"
        )
        row = cursor.fetchone()
        if not row or len(row) != 11:
            raise RuntimeError("MariaDB server did not return the complete capability inventory")
        return {
            "version": str(row[0]), "version_comment": str(row[1]), "character_set_server": str(row[2]),
            "collation_server": str(row[3]), "time_zone": str(row[4]), "system_time_zone": str(row[5]),
            "lower_case_table_names": int(row[6]), "have_ssl": str(row[7]),
            "require_secure_transport": bool(row[8]), "local_infile": bool(row[9]), "event_scheduler": str(row[10]),
        }
    finally:
        cursor.close()
        connection.close()


def evaluate(*, runtime: dict[str, Any], database: dict[str, Any], deployment_mode: str) -> dict[str, Any]:
    """Classify evidence without making an environment change."""
    checks: dict[str, bool] = {}
    version = _parse_version(database["version"])
    checks["mariadb_family"] = "mariadb" in database["version_comment"].casefold() or "mariadb" in database["version"].casefold()
    checks["mariadb_version"] = version is not None and version >= MIN_MARIADB
    checks["python_version"] = bool(runtime["python_supported"])
    checks["required_commands"] = all(runtime["required_commands"].values())
    checks["case_sensitive_identifiers"] = database["lower_case_table_names"] == 0
    checks["source_connection_utf8"] = database["character_set_server"].casefold() in {"utf8mb4", "latin1"}
    checks["event_scheduler_disabled"] = database["event_scheduler"].casefold() == "off"
    checks["tls_required_for_remote"] = deployment_mode == "local" or (
        database["have_ssl"].casefold() not in {"disabled", "no"} and database["require_secure_transport"]
    )
    checks["local_infile_disabled_for_remote"] = deployment_mode == "local" or not database["local_infile"]
    return {
        "report_version": "obsidiandroid-host-preflight-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "deployment_mode": deployment_mode,
        "runtime": runtime,
        "database": database,
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "BLOCKED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option-file", type=Path, required=True)
    parser.add_argument("--deployment-mode", choices=("local", "remote"), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.option_file.is_file() or args.option_file.stat().st_mode & 0o077:
        raise SystemExit("Read-only host preflight requires a private MariaDB option file (0600)")
    report = evaluate(runtime=_runtime_inventory(), database=_database_inventory(args.option_file), deployment_mode=args.deployment_mode)
    report["report_sha256"] = _canonical_hash(report)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
