"""Read-only reconciliation of Core rows against a reviewed import plan."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, Iterable

from .mapping import CoreImportError, _canonical_hash


_UTC_DATETIME_COLUMNS = frozenset({"extracted_at_utc", "run_started_at_utc", "run_completed_at_utc"})


def _normalized_value(column: str, value: Any) -> Any:
    """Normalize equivalent Core storage representations before hashing."""
    if value is None:
        return None
    if column == "mutable_pointer_flag":
        return bool(value)
    if column in _UTC_DATETIME_COLUMNS:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.astimezone(UTC).replace(tzinfo=None)
            return value.isoformat(timespec="microseconds") + "Z"
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _project(rows: Iterable[dict[str, Any]], columns: list[str], key_columns: list[str]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for row in rows:
        if any(column not in row for column in columns):
            missing = sorted(column for column in columns if column not in row)
            raise CoreImportError(f"Core reconciliation projection omitted required columns: {missing!r}")
        projected.append({column: _normalized_value(column, row[column]) for column in columns})
    return sorted(projected, key=lambda row: tuple(str(row.get(key) or "") for key in key_columns))


def reconcile_destination_rows(
    *,
    plan: dict[str, Any],
    observed_rows: dict[str, Iterable[dict[str, Any]]],
) -> dict[str, Any]:
    """Compare auditor-projected Core rows with plan-bound table hashes.

    Callers must provide only the columns named by the plan's reconciliation
    contract.  This deliberately excludes generated IDs, import timestamps,
    and receipt IDs while checking the exact imported evidence content.
    """
    contract = plan.get("destination_reconciliation")
    if not isinstance(contract, dict):
        raise CoreImportError("Import plan lacks a destination reconciliation contract")
    result: dict[str, Any] = {"tables": {}, "all_match": True}
    destination_rows = plan.get("destination_rows")
    if not isinstance(destination_rows, dict):
        raise CoreImportError("Import plan lacks destination rows for semantic reconciliation")
    for table, expected in contract.items():
        if table not in observed_rows:
            raise CoreImportError(f"Core reconciliation omitted observed table {table!r}")
        columns = expected.get("columns")
        key_columns = expected.get("key_columns")
        if not isinstance(columns, list) or not isinstance(key_columns, list):
            raise CoreImportError(f"Core reconciliation contract for {table!r} is malformed")
        rows = _project(observed_rows[table], columns, key_columns)
        expected_rows = _project(destination_rows.get(table, []), columns, key_columns)
        key_rows = [{key: row.get(key) for key in key_columns} for row in rows]
        expected_key_rows = [{key: row.get(key) for key in key_columns} for row in expected_rows]
        actual = {
            "row_count": len(rows),
            "key_sha256": _canonical_hash(key_rows),
            "row_sha256": _canonical_hash(rows),
        }
        semantic_expected = {
            "row_count": len(expected_rows),
            "key_sha256": _canonical_hash(expected_key_rows),
            "row_sha256": _canonical_hash(expected_rows),
        }
        matches = all(actual[key] == semantic_expected[key] for key in actual)
        result["tables"][table] = {"expected": semantic_expected, "actual": actual, "matches": matches}
        result["all_match"] = bool(result["all_match"] and matches)
    unexpected = sorted(set(observed_rows) - set(contract))
    if unexpected:
        raise CoreImportError(f"Core reconciliation received unexpected tables: {unexpected!r}")
    return result
