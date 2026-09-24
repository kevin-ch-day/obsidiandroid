"""Read-only comparison with the reviewed MariaDB operational schema contract."""

from __future__ import annotations

from importlib.resources import files
import json
import re

from .composition import digest
from obsidiandroid.core_migration.executor import CoreMigrationError
from obsidiandroid.core_migration.migration_checksums import MIGRATION_CHECKSUMS

OBJECTS = (
    "core_assessment_artifact",
    "core_assessment_revision",
    "v_core_assessment_current",
)
_SQL_TOKEN = re.compile(
    r"'(?:''|\\.|[^'\\])*'|`(?:``|[^`])*`|[A-Za-z_][A-Za-z_0-9]*|\d+|<=>|<>|<=|>=|[^\s]"
)


_SQL_WORDS = frozenset(
    """
select from into where not exists and or is null coalesce max begin end declare default
if then for update signal sqlstate set message_text new old char bigint unsigned
json_unquote json_extract json_valid json_contains_path nullif cast as regexp binary
""".split()
)


def normalize_sql(value: str, database: str) -> str:
    """Normalize formatting/own-schema qualification, preserving string literals."""
    tokens = _SQL_TOKEN.findall(value or "")
    result = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.strip("`") == database and tokens[i : i + 2][-1:] == ["."]:
            result.append("$self")
        elif token.startswith("'"):
            result.append(token)
        elif token.startswith("`"):
            # MariaDB table names can be case-sensitive on Linux. Never fold
            # identifiers into a different physical table while normalizing SQL.
            result.append(token[1:-1].replace("``", "`"))
        else:
            result.append(token.lower() if token.lower() in _SQL_WORDS else token)
        i += 1
    return " ".join(result)


def schema_snapshot(connection) -> dict:
    """Inspect only assessment objects; perform no DDL, repair, or data mutation."""
    with connection.cursor() as cur:
        cur.execute("SELECT DATABASE()")
        database = cur.fetchone()[0]
        if not database:
            raise CoreMigrationError(
                "Assessment schema inspection requires a selected database"
            )
        cur.execute(
            "SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s",
            (database,),
        )
        default_collation = cur.fetchone()[0]
        names = ",".join(["%s"] * len(OBJECTS))
        queries = {
            "objects": f"SELECT TABLE_NAME,TABLE_TYPE,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({names}) ORDER BY TABLE_NAME",
            "columns": f"SELECT TABLE_NAME,COLUMN_NAME,ORDINAL_POSITION,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,COLLATION_NAME,EXTRA,GENERATION_EXPRESSION FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({names}) ORDER BY TABLE_NAME,ORDINAL_POSITION",
            "indexes": f"SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART,INDEX_TYPE,COLLATION FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({names}) ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX",
            "checks": f"SELECT TABLE_NAME,CONSTRAINT_NAME,CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=%s AND TABLE_NAME IN ({names}) ORDER BY TABLE_NAME,CONSTRAINT_NAME",
            "foreign_keys": f"SELECT k.TABLE_NAME,k.CONSTRAINT_NAME,k.COLUMN_NAME,k.ORDINAL_POSITION,k.REFERENCED_TABLE_SCHEMA,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.UPDATE_RULE,r.DELETE_RULE FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME WHERE k.TABLE_SCHEMA=%s AND k.TABLE_NAME IN ({names}) ORDER BY k.TABLE_NAME,k.CONSTRAINT_NAME,k.ORDINAL_POSITION",
            "triggers": f"SELECT EVENT_OBJECT_TABLE,TRIGGER_NAME,ACTION_TIMING,EVENT_MANIPULATION,ACTION_ORIENTATION,ACTION_STATEMENT,SQL_MODE FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_TABLE IN ({names}) ORDER BY EVENT_OBJECT_TABLE,TRIGGER_NAME",
            "views": f"SELECT TABLE_NAME,VIEW_DEFINITION,CHECK_OPTION,SECURITY_TYPE,IS_UPDATABLE FROM information_schema.VIEWS WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({names}) ORDER BY TABLE_NAME",
        }
        snapshot = {}
        for section, sql in queries.items():
            cur.execute(sql, (database, *OBJECTS))
            keys = [item[0] for item in cur.description]
            rows = []
            for values in cur.fetchall():
                row = dict(zip(keys, values))
                for key in (
                    "CHECK_CLAUSE",
                    "GENERATION_EXPRESSION",
                    "ACTION_STATEMENT",
                    "VIEW_DEFINITION",
                ):
                    if key in row and row[key] is not None:
                        row[key] = normalize_sql(row[key], database)
                # 0006 deliberately leaves only this generated string column's
                # collation to the schema default; explicit SHA/JSON collations
                # must still match exactly. A changed column collation is drift.
                if (
                    row.get("COLUMN_NAME") == "processing_status"
                    and row.get("COLLATION_NAME") == default_collation
                ):
                    row["COLLATION_NAME"] = "$database_default"
                if row.get("REFERENCED_TABLE_SCHEMA") == database:
                    row["REFERENCED_TABLE_SCHEMA"] = "$self"
                rows.append(row)
            snapshot[section] = rows
        return snapshot


def schema_report(connection) -> dict:
    """Report structural drift, including definitions hidden behind unchanged names."""
    contract = json.loads(
        files("obsidiandroid.assessment")
        .joinpath("schema_contract_v1.json")
        .read_text()
    )
    if contract["migration_checksum"] != MIGRATION_CHECKSUMS["0006"]:
        raise CoreMigrationError(
            "Assessment schema contract/migration checksum mismatch"
        )
    actual = schema_snapshot(connection)
    expected = contract["schema"]
    differences = []
    for section in sorted(expected):
        if actual.get(section) != expected[section]:
            differences.append(
                {
                    "section": section,
                    "expected": expected[section],
                    "observed": actual.get(section),
                }
            )
    return {
        "status": "drift" if differences else "ready",
        "migration_version": "0006",
        "migration_checksum": contract["migration_checksum"],
        "expected_schema_sha256": digest(expected),
        "observed_schema_sha256": digest(actual),
        "differences": differences,
    }


def validate_schema(connection):
    """Reject missing, altered, extra, or wrongly bound assessment structures."""
    report = schema_report(connection)
    if report["status"] != "ready":
        sections = ", ".join(item["section"] for item in report["differences"])
        raise CoreMigrationError(f"Assessment schema drift detected: {sections}")
    return report
