"""Canonical structural digests for Core DDL equivalence proofs."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any


def _canonical_type(definition: str) -> str:
    text = definition.lower().strip()
    text = text.replace("int(10) unsigned", "int unsigned")
    text = text.replace("bigint(20) unsigned", "bigint unsigned")
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_check_clause(clause: str) -> str:
    compact = re.sub(r"\s+", " ", clause).strip().lower().replace("`", "")
    return compact


def _normalize_show_create(ddl: str) -> str:
    text = ddl.replace("\r\n", "\n")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\sint\(\d+\)\s", " int ", text, flags=re.I)
    text = re.sub(r"\sbigint\(\d+\)\s", " bigint ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def parse_expected_create_bodies(sql_text: str, tables: tuple[str, ...]) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for table in tables:
        match = re.search(
            rf"CREATE TABLE {table} \((.*?)\n\) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
            sql_text,
            flags=re.S,
        )
        if not match:
            raise ValueError(f"Reviewed SQL is missing CREATE TABLE {table}")
        bodies[table] = match.group(1)
    return bodies


def expected_structural_digest_from_sql(table: str, body: str) -> dict[str, Any]:
    """Build the reviewed-SQL structural contract for one table."""
    columns: list[dict[str, Any]] = []
    primary_key: tuple[str, ...] = ()
    unique_keys: list[dict[str, Any]] = []
    secondary_indexes: list[dict[str, Any]] = []
    foreign_keys: list[dict[str, Any]] = []
    checks: list[dict[str, str]] = []
    ordinal = 0
    for raw in body.splitlines():
        line = raw.strip().rstrip(",")
        if not line:
            continue
        if line.startswith("PRIMARY KEY"):
            primary_key = tuple(part.strip() for part in re.search(r"\((.*)\)", line).group(1).split(","))
            continue
        if line.startswith("UNIQUE KEY"):
            match = re.match(r"UNIQUE KEY (\w+) \((.*)\)", line)
            unique_keys.append(
                {
                    "name": match.group(1),
                    "columns": tuple(part.strip() for part in match.group(2).split(",")),
                    "non_unique": 0,
                }
            )
            continue
        if line.startswith("KEY ") or line.startswith("INDEX "):
            match = re.match(r"(?:KEY|INDEX) (\w+) \((.*)\)", line)
            secondary_indexes.append(
                {
                    "name": match.group(1),
                    "columns": tuple(part.strip() for part in match.group(2).split(",")),
                    "non_unique": 1,
                }
            )
            continue
        if line.startswith("CONSTRAINT ") and "FOREIGN KEY" in line:
            match = re.match(
                r"CONSTRAINT (\w+) FOREIGN KEY \((.*)\) REFERENCES (\w+) \((.*)\)"
                r"(?:\s+ON DELETE (\w+(?:\s+\w+)?))?(?:\s+ON UPDATE (\w+(?:\s+\w+)?))?",
                line,
            )
            foreign_keys.append(
                {
                    "name": match.group(1),
                    "columns": tuple(part.strip() for part in match.group(2).split(",")),
                    "referenced_table": match.group(3),
                    "referenced_columns": tuple(part.strip() for part in match.group(4).split(",")),
                    "on_delete": (match.group(5) or "RESTRICT").upper().replace(" ", "_"),
                    "on_update": (match.group(6) or "RESTRICT").upper().replace(" ", "_"),
                }
            )
            continue
        if line.startswith("CONSTRAINT ") and "CHECK" in line:
            match = re.match(r"CONSTRAINT (\w+) CHECK \((.*)\)", line)
            checks.append({"name": match.group(1), "clause": _normalize_check_clause(match.group(2))})
            continue
        ordinal += 1
        nullable = "NOT NULL" not in line
        working = line
        for token in (" NOT NULL", " NULL"):
            working = working.replace(token, "")
        charset = collation = None
        match = re.search(r"CHARACTER SET (\w+)", working)
        if match:
            charset = match.group(1)
            working = working.replace(match.group(0), "")
        match = re.search(r"COLLATE (\w+)", working)
        if match:
            collation = match.group(1)
            working = working.replace(match.group(0), "")
        default = None
        match = re.search(r"DEFAULT ([^ ]+)", working, flags=re.I)
        if match:
            default = match.group(1)
            working = working.replace(match.group(0), "")
        elif nullable:
            default = "NULL"
        extra = ""
        match = re.search(r"(AUTO_INCREMENT|on update .*)$", working, flags=re.I)
        if match:
            extra = match.group(1).lower()
            working = working[: match.start()].rstrip()
        name, type_text = working.split(" ", 1)
        columns.append(
            {
                "ordinal": ordinal,
                "name": name,
                "type": _canonical_type(type_text),
                "nullable": nullable,
                "default": default,
                "extra": extra,
                "charset": charset,
                "collation": collation,
            }
        )
    return {
        "table": table,
        "engine": "InnoDB",
        "table_collation": "utf8mb4_unicode_ci",
        "charset": "utf8mb4",
        "columns": columns,
        "primary_key": primary_key,
        "unique_keys": sorted(unique_keys, key=lambda item: item["name"]),
        "secondary_indexes": sorted(secondary_indexes, key=lambda item: item["name"]),
        "foreign_keys": sorted(foreign_keys, key=lambda item: item["name"]),
        "checks": sorted(checks, key=lambda item: item["name"]),
    }


def live_structural_digest(cursor: Any, schema: str, table: str) -> dict[str, Any]:
    """Collect a complete live structural digest from information_schema + SHOW CREATE."""
    cursor.execute(
        "SELECT ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (schema, table),
    )
    engine_row = cursor.fetchone()
    if not engine_row:
        raise ValueError(f"Required table is missing: {table}")
    engine, table_collation = str(engine_row[0]), str(engine_row[1])
    cursor.execute(
        "SELECT ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, "
        "CHARACTER_SET_NAME, COLLATION_NAME "
        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
        "ORDER BY ORDINAL_POSITION",
        (schema, table),
    )
    columns = []
    for ordinal, name, column_type, nullable, default, extra, charset, collation in cursor.fetchall():
        columns.append(
            {
                "ordinal": int(ordinal),
                "name": str(name),
                "type": _canonical_type(str(column_type)),
                "nullable": nullable == "YES",
                "default": None if default is None else str(default),
                "extra": str(extra or "").lower(),
                "charset": None if charset is None else str(charset),
                "collation": None if collation is None else str(collation),
            }
        )

    cursor.execute(
        "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME='PRIMARY' "
        "ORDER BY ORDINAL_POSITION",
        (schema, table),
    )
    primary_key = tuple(str(row[0]) for row in cursor.fetchall())

    cursor.execute(
        "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
        "FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME <> 'PRIMARY' "
        "ORDER BY INDEX_NAME, SEQ_IN_INDEX",
        (schema, table),
    )
    index_map: dict[str, dict[str, Any]] = {}
    for index_name, non_unique, _seq, column_name in cursor.fetchall():
        entry = index_map.setdefault(
            str(index_name),
            {"name": str(index_name), "non_unique": int(non_unique), "columns": []},
        )
        entry["columns"].append(str(column_name))
    unique_keys = []
    secondary_indexes = []
    for entry in sorted(index_map.values(), key=lambda item: item["name"]):
        payload = {
            "name": entry["name"],
            "columns": tuple(entry["columns"]),
            "non_unique": entry["non_unique"],
        }
        if entry["non_unique"] == 0:
            unique_keys.append(payload)
        else:
            secondary_indexes.append(payload)

    cursor.execute(
        "SELECT rc.CONSTRAINT_NAME, rc.UPDATE_RULE, rc.DELETE_RULE, "
        "kcu.COLUMN_NAME, kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME, kcu.ORDINAL_POSITION "
        "FROM information_schema.REFERENTIAL_CONSTRAINTS rc "
        "JOIN information_schema.KEY_COLUMN_USAGE kcu "
        "  ON rc.CONSTRAINT_SCHEMA=kcu.CONSTRAINT_SCHEMA AND rc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME "
        " AND rc.TABLE_NAME=kcu.TABLE_NAME "
        "WHERE rc.CONSTRAINT_SCHEMA=%s AND rc.TABLE_NAME=%s "
        "ORDER BY rc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION",
        (schema, table),
    )
    fk_map: dict[str, dict[str, Any]] = {}
    for name, update_rule, delete_rule, column_name, referenced_table, referenced_column, _ord in cursor.fetchall():
        entry = fk_map.setdefault(
            str(name),
            {
                "name": str(name),
                "columns": [],
                "referenced_table": str(referenced_table),
                "referenced_columns": [],
                "on_update": str(update_rule).upper(),
                "on_delete": str(delete_rule).upper(),
            },
        )
        entry["columns"].append(str(column_name))
        entry["referenced_columns"].append(str(referenced_column))
    foreign_keys = []
    for entry in sorted(fk_map.values(), key=lambda item: item["name"]):
        foreign_keys.append(
            {
                "name": entry["name"],
                "columns": tuple(entry["columns"]),
                "referenced_table": entry["referenced_table"],
                "referenced_columns": tuple(entry["referenced_columns"]),
                "on_delete": entry["on_delete"],
                "on_update": entry["on_update"],
            }
        )

    cursor.execute(
        "SELECT CONSTRAINT_NAME, CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA=%s AND CONSTRAINT_NAME IN ("
        "  SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "  WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_TYPE='CHECK'"
        ") ORDER BY CONSTRAINT_NAME",
        (schema, schema, table),
    )
    checks = [
        {"name": str(name), "clause": _normalize_check_clause(str(clause))}
        for name, clause in cursor.fetchall()
    ]

    cursor.execute(f"SHOW CREATE TABLE `{schema}`.`{table}`")
    _name, show_create = cursor.fetchone()
    digest = {
        "table": table,
        "engine": engine,
        "table_collation": table_collation,
        "charset": "utf8mb4" if table_collation.startswith("utf8mb4") else table_collation.split("_")[0],
        "columns": columns,
        "primary_key": primary_key,
        "unique_keys": unique_keys,
        "secondary_indexes": secondary_indexes,
        "foreign_keys": foreign_keys,
        "checks": checks,
        "show_create_normalized": _normalize_show_create(str(show_create)),
    }
    digest["table_digest_sha256"] = sha256(
        json.dumps({k: v for k, v in digest.items() if k != "table_digest_sha256"}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return digest


def compare_structural_digests(expected: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """Compare reviewed SQL contract to live MariaDB materialization."""
    mismatches: list[str] = []
    for key in ("table", "engine", "table_collation", "charset", "primary_key"):
        if expected[key] != live[key]:
            mismatches.append(f"{key}: expected {expected[key]!r} live {live[key]!r}")
    if expected["columns"] != live["columns"]:
        # Defaults: SQL NULL columns may omit DEFAULT; live shows NULL.
        if len(expected["columns"]) != len(live["columns"]):
            mismatches.append("columns length mismatch")
        else:
            for exp, got in zip(expected["columns"], live["columns"], strict=True):
                for field in ("ordinal", "name", "type", "nullable", "extra"):
                    if exp.get(field) != got.get(field):
                        mismatches.append(f"column.{field}: expected {exp} live {got}")
                        break
                else:
                    exp_charset = exp.get("charset")
                    exp_collation = exp.get("collation")
                    got_charset = got.get("charset")
                    got_collation = got.get("collation")
                    # SQL that omits CHARACTER SET inherits the table utf8mb4 defaults.
                    if exp_charset is None and got_charset in (None, "utf8mb4"):
                        exp_charset = got_charset
                    if exp_collation is None and got_collation in (None, "utf8mb4_unicode_ci"):
                        exp_collation = got_collation
                    if exp_charset != got_charset or exp_collation != got_collation:
                        mismatches.append(f"column.charset: expected {exp} live {got}")
                        continue
                    exp_default = exp.get("default")
                    got_default = got.get("default")
                    if exp_default != got_default and not (
                        exp.get("nullable") and exp_default in (None, "NULL") and got_default is None
                    ):
                        mismatches.append(f"column.default: expected {exp} live {got}")
    if expected["unique_keys"] != live["unique_keys"]:
        mismatches.append(f"unique_keys: expected {expected['unique_keys']!r} live {live['unique_keys']!r}")
    # InnoDB may materialize supporting secondary indexes for FK columns.
    expected_secondary = {item["name"]: item for item in expected["secondary_indexes"]}
    live_secondary = {item["name"]: item for item in live["secondary_indexes"]}
    for name, item in expected_secondary.items():
        if live_secondary.get(name) != item:
            mismatches.append(f"secondary_index missing/mismatch: {name}")
    for name, item in live_secondary.items():
        if name in expected_secondary:
            continue
        # Accept auto supporting indexes only when they exactly cover an FK column set.
        fk_column_sets = {fk["columns"] for fk in live["foreign_keys"]}
        if tuple(item["columns"]) not in fk_column_sets:
            mismatches.append(f"unexpected secondary_index: {item}")
    # Normalize NO_ACTION vs RESTRICT for comparison (MariaDB equivalent defaults).
    def _norm_fk(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for item in items:
            copy = dict(item)
            for rule in ("on_delete", "on_update"):
                value = str(copy.get(rule, "RESTRICT")).upper().replace(" ", "_")
                copy[rule] = "RESTRICT" if value in {"RESTRICT", "NO_ACTION"} else value
            normalized.append(copy)
        return sorted(normalized, key=lambda row: row["name"])

    if _norm_fk(expected["foreign_keys"]) != _norm_fk(live["foreign_keys"]):
        mismatches.append(
            f"foreign_keys: expected {expected['foreign_keys']!r} live {live['foreign_keys']!r}"
        )
    if expected["checks"] != live["checks"]:
        mismatches.append(f"checks: expected {expected['checks']!r} live {live['checks']!r}")
    return mismatches


def package_structural_digest(digests: dict[str, dict[str, Any]]) -> str:
    payload = {
        table: {k: v for k, v in digests[table].items() if k != "show_create_normalized"}
        for table in sorted(digests)
    }
    # Prefer including normalized SHOW CREATE in package identity when present.
    for table in sorted(digests):
        if "show_create_normalized" in digests[table]:
            payload[table]["show_create_normalized"] = digests[table]["show_create_normalized"]
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
