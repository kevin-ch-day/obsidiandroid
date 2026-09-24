"""Read-only schema and bounded exact-artifact integrity checks for assessments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .composition import digest, validate_sha256
from .contract import validate_body
from .mariadb_store import MariaDBAssessmentStore, AssessmentPersistenceError
from .inspection import inspect_schema as schema_report
from obsidiandroid.core_migration.executor import CoreMigrationError
from obsidiandroid.core_migration.migration_checksums import MIGRATION_CHECKSUMS


def inspect_database(
    store: MariaDBAssessmentStore,
    *,
    sha256: str | None = None,
    max_revisions: int = 100,
) -> dict:
    """Inspect without writes; a limited history is explicitly reported as partial."""
    sha = validate_sha256(sha256) if sha256 is not None else None
    if type(max_revisions) is not int or not 1 <= max_revisions <= 200:
        raise ValueError("max_revisions must be between 1 and 200")
    with store.connect(read_only=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET SESSION max_statement_time=5")
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
            cur.execute("SELECT DATABASE(),@@tx_read_only,VERSION()")
            database, read_only, version = cur.fetchone()
            if database != store.database or read_only != 1:
                raise ValueError(
                    "Doctor requires the exact target and read-only transaction"
                )
        report = {
            "database": database,
            "server_version": version,
            "read_only": True,
            "scope": "schema_and_bounded_artifact" if sha else "schema_only",
            "schema": schema_report(conn),
            "artifact": None,
        }
        with conn.cursor() as cur:
            cur.execute(
                "SELECT migration_checksum,execution_status FROM core_schema_migration WHERE migration_version='0006'"
            )
            row = cur.fetchone()
            report["migration_ledger_valid"] = row == (
                MIGRATION_CHECKSUMS["0006"],
                "applied",
            )
            report["status"] = (
                "ready"
                if report["schema"]["status"] == "ready"
                and report["migration_ledger_valid"]
                else (
                    "partial"
                    if report["schema"]["status"] == "partial"
                    and report["migration_ledger_valid"]
                    else "failed"
                )
            )
            if report["status"] != "ready" or sha is None:
                return report
            cur.execute(
                "SELECT assessment_id,artifact_sha256,revision,previous_assessment_id,input_digest,assessed_at_utc,result_json FROM core_assessment_revision WHERE artifact_sha256=%s ORDER BY revision LIMIT %s",
                (sha, max_revisions + 1),
            )
            names = [item[0] for item in cur.description]
            records = [dict(zip(names, row)) for row in cur.fetchall()]
            truncated = len(records) > max_revisions
            records = records[:max_revisions]
            problems = []
            cur.execute(
                "SELECT artifact_sha256 FROM core_assessment_artifact WHERE artifact_sha256=%s",
                (sha,),
            )
            artifact_exists = cur.fetchone() is not None
            if artifact_exists != bool(records):
                problems.append({"reason": "artifact/revision mismatch"})
            previous = None
            for index, row in enumerate(records, 1):
                try:
                    record = json.loads(row["result_json"])
                    body = dict(record)
                    for key in (
                        "assessment_id",
                        "revision",
                        "previous_assessment_id",
                        "assessed_at_utc",
                    ):
                        if body.pop(key) != row[key]:
                            raise ValueError("column/payload mismatch")
                    if (
                        body["artifact"]["sha256"] != sha
                        or row["artifact_sha256"] != sha
                    ):
                        raise ValueError("artifact mismatch")
                    validate_body(body, row["assessed_at_utc"])
                    if digest(body) != row["input_digest"]:
                        raise ValueError("input digest mismatch")
                    identity = {
                        k: row[k]
                        for k in (
                            "artifact_sha256",
                            "input_digest",
                            "revision",
                            "previous_assessment_id",
                        )
                    }
                    if digest(identity) != row["assessment_id"]:
                        raise ValueError("assessment identity mismatch")
                    if (
                        row["revision"] != index
                        or row["previous_assessment_id"] != previous
                    ):
                        raise ValueError("broken revision chain")
                except (ValueError, KeyError, TypeError) as exc:
                    # No source values, SQL text, or credentials in diagnostics.
                    problems.append(
                        {"revision": row["revision"], "reason": type(exc).__name__}
                    )
                previous = row["assessment_id"]
            cur.execute(
                "SELECT assessment_id,revision FROM v_core_assessment_current WHERE artifact_sha256=%s",
                (sha,),
            )
            heads = cur.fetchall()
            if not truncated and heads != (
                [(records[-1]["assessment_id"], records[-1]["revision"])]
                if records
                else []
            ):
                problems.append({"reason": "current/history mismatch"})
            if len(heads) > 1:
                problems.append({"reason": "multiple current revisions"})
            report["artifact"] = {
                "sha256": sha,
                "checked_revisions": len(records),
                "complete": not truncated,
                "current_revision": heads[0][1] if len(heads) == 1 else None,
                "problems": problems,
                "status": "failed"
                if problems
                else (
                    "partial" if truncated else ("valid" if records else "not_assessed")
                ),
            }
            if problems:
                report["status"] = "failed"
            elif truncated:
                report["status"] = "partial"
        return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--option-file", type=Path, required=True)
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Explicit target opt-in; inspection remains read-only",
    )
    parser.add_argument("--sha256")
    parser.add_argument("--max-revisions", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    import mysql.connector

    try:
        store = MariaDBAssessmentStore(
            lambda: mysql.connector.connect(
                option_files=str(args.option_file),
                database=args.database,
                autocommit=False,
                connection_timeout=5,
            ),
            database=args.database,
            allow_production=args.allow_production,
        )
        result = inspect_database(
            store, sha256=args.sha256, max_revisions=args.max_revisions
        )
    except (
        ValueError,
        OSError,
        CoreMigrationError,
        AssessmentPersistenceError,
        mysql.connector.Error,
    ) as exc:
        result = {
            "status": "unavailable",
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
        }
    if args.json:
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    else:
        print(
            f"Assessment doctor: {result['status']} ({args.database}); read-only inspection"
        )
        if "schema" in result:
            print(
                f"Schema: {result['schema']['status']}; migration ledger valid: {result['migration_ledger_valid']}"
            )
            for difference in result["schema"]["differences"]:
                print(f"  Definition mismatch: {difference['section']}")
            for item in result["schema"].get("unverified", []):
                print(f"  Incomplete verification: {item['section']}: {item['reason']}")
        if result.get("artifact"):
            artifact = result["artifact"]
            print(
                f"Artifact: {artifact['status']}; checked {artifact['checked_revisions']} revisions; complete: {artifact['complete']}"
            )
        if result.get("error_type"):
            print(
                f"Unavailable: {result['error_type']} errno={result.get('errno')}; verify connection and metadata visibility"
            )

    return (
        0
        if result["status"] == "ready"
        else (3 if result["status"] == "partial" else 2)
    )


if __name__ == "__main__":
    raise SystemExit(main())
