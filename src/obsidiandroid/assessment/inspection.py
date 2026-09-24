"""Distinguish hidden MariaDB metadata from proven assessment schema drift.

Migration validation remains strict. The read-only doctor may report partial
verification when independent SHOW CREATE evidence demonstrates metadata hiding.
"""

from copy import deepcopy
import re

from .schema import normalize_sql, schema_report

_ACCESS_DENIED = {1044, 1142, 1227, 1370}
_CHECK = re.compile(r"^\s*CONSTRAINT `((?:``|[^`])+)` CHECK \((.*)\),?$", re.M)


_FK = re.compile(
    r"^\s*CONSTRAINT `([^`]+)` FOREIGN KEY \(([^)]+)\) REFERENCES "
    r"(?:(`[^`]+`)\.)?`([^`]+)` \(([^)]+)\)([^\n]*)$",
    re.M,
)


def _foreign_keys(ddl, table, database):
    rows = []
    for name, columns, ref_schema, ref_table, ref_columns, tail in _FK.findall(ddl):
        local = re.findall(r"`([^`]+)`", columns)
        remote = re.findall(r"`([^`]+)`", ref_columns)
        if len(local) != len(remote):
            continue
        rules = {}
        for action in ("UPDATE", "DELETE"):
            match = re.search(
                r"ON " + action + r" (RESTRICT|CASCADE|SET NULL|NO ACTION)", tail
            )
            rules[action] = match[1] if match else "RESTRICT"
        target = ref_schema.strip("`") if ref_schema else database
        for i, (column, ref_column) in enumerate(zip(local, remote), 1):
            rows.append(
                {
                    "TABLE_NAME": table,
                    "CONSTRAINT_NAME": name,
                    "COLUMN_NAME": column,
                    "ORDINAL_POSITION": i,
                    "REFERENCED_TABLE_SCHEMA": "$self"
                    if target == database
                    else target,
                    "REFERENCED_TABLE_NAME": ref_table,
                    "REFERENCED_COLUMN_NAME": ref_column,
                    "UPDATE_RULE": rules["UPDATE"],
                    "DELETE_RULE": rules["DELETE"],
                }
            )
    return rows


def inspect_schema(connection):
    """Return ready, partial, or drift without repairing or granting privileges."""
    report = deepcopy(schema_report(connection))
    if report["status"] == "ready":
        return report
    unverified = []
    mismatches = []
    with connection.cursor() as cur:
        cur.execute("SELECT DATABASE()")
        database = cur.fetchone()[0]
        for difference in report["differences"]:
            section = difference["section"]
            if section == "checks":
                expected = {
                    (r["TABLE_NAME"], r["CONSTRAINT_NAME"]): r
                    for r in difference["expected"]
                }
                observed = {
                    (r["TABLE_NAME"], r["CONSTRAINT_NAME"]): r
                    for r in difference["observed"]
                }
                # Visible altered/extra constraints always prove a mismatch.
                if any(expected.get(k) != v for k, v in observed.items()):
                    mismatches.append(difference)
                    continue
                missing = expected.keys() - observed.keys()
                ddl_checks = {}
                denied = set()
                for table in sorted({k[0] for k in missing}):
                    try:
                        cur.execute(f"SHOW CREATE TABLE `{table}`")
                        ddl = cur.fetchone()[1]
                        ddl_checks[table] = {
                            name.replace("``", "`"): normalize_sql(clause, database)
                            for name, clause in _CHECK.findall(ddl)
                        }
                    except Exception as exc:
                        if getattr(exc, "errno", None) not in _ACCESS_DENIED:
                            raise
                        denied.add(table)
                proven_mismatch = any(
                    table not in denied
                    and ddl_checks[table]
                    != {
                        name: row["CHECK_CLAUSE"]
                        for (t, name), row in expected.items()
                        if t == table
                    }
                    for table in {k[0] for k in missing}
                )
                if proven_mismatch:
                    mismatches.append(difference)
                else:
                    unverified.append(
                        {
                            "section": section,
                            "reason": "CHECK_CONSTRAINTS metadata is hidden; use a metadata auditor",
                            "constraints": sorted(f"{t}.{n}" for t, n in missing),
                            "show_create_confirmed": not denied,
                        }
                    )
            elif section == "foreign_keys" and not difference["observed"]:
                ddl_rows = []
                denied = False
                for table in sorted({r["TABLE_NAME"] for r in difference["expected"]}):
                    try:
                        cur.execute(f"SHOW CREATE TABLE `{table}`")
                        ddl_rows.extend(
                            _foreign_keys(cur.fetchone()[1], table, database)
                        )
                    except Exception as exc:
                        if getattr(exc, "errno", None) not in _ACCESS_DENIED:
                            raise
                        denied = True
                if denied or ddl_rows == difference["expected"]:
                    unverified.append(
                        {
                            "section": section,
                            "reason": "REFERENTIAL_CONSTRAINTS metadata is hidden; use a metadata auditor",
                        }
                    )
                else:
                    mismatches.append(difference)
            elif section == "triggers":
                expected = {r["TRIGGER_NAME"]: r for r in difference["expected"]}
                observed = {r["TRIGGER_NAME"]: r for r in difference["observed"]}
                if any(expected.get(k) != v for k, v in observed.items()):
                    mismatches.append(difference)
                    continue
                hidden = []
                for name in sorted(expected.keys() - observed.keys()):
                    try:
                        cur.execute(f"SHOW CREATE TRIGGER `{name}`")
                        cur.fetchone()
                        # Visible DDL with absent metadata is still incomplete.
                        hidden.append(name)
                    except Exception as exc:
                        if getattr(exc, "errno", None) in _ACCESS_DENIED:
                            hidden.append(name)
                        elif getattr(exc, "errno", None) == 1360:
                            mismatches.append(difference)
                            break
                        else:
                            raise
                if hidden:
                    unverified.append(
                        {
                            "section": section,
                            "reason": "Trigger metadata visibility is incomplete",
                            "triggers": hidden,
                        }
                    )
            else:
                mismatches.append(difference)
    report["metadata_differences"] = report["differences"]
    report["differences"] = mismatches
    report["unverified"] = unverified
    report["status"] = "drift" if mismatches else "partial" if unverified else "ready"
    return report
