"""Read-only Core-auditor reconciliation command tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from obsidiandroid.core_migration.mapping import CoreImportError, build_import_plan
from obsidiandroid.core_migration.reconciliation import reconcile_destination_rows


_SCRIPT = Path("scripts/core_migration/verify_phase2c_import.py")
_SPEC = importlib.util.spec_from_file_location("phase2c_import_verifier", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _plan() -> dict:
    return build_import_plan(
        run={"run_id": "fixture-run", "profile_id": "fixture-profile", "created_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64},
        snapshots=[{"run_id": "fixture-run", "extracted_at_utc": "2026-07-19 12:00:00", "selection_rule_version": "v1", "snapshot_sha256_hash": "a" * 64, "snapshot_row_count": 1}],
        samples=[{"run_id": "fixture-run", "sha256": "b" * 64, "sample_id": 1}],
        artifacts=[],
        conflicts=[],
    )


class _Cursor:
    def __init__(self, *, plan: dict, identity: dict[str, str]) -> None:
        self.plan = plan
        self.identity = identity
        self.calls = 0

    def execute(self, _sql: str, _params=()) -> None:
        self.calls += 1

    def fetchone(self):
        return self.identity

    def fetchall(self):
        table = list(_MODULE._TABLES)[self.calls - 2]
        columns = self.plan["destination_reconciliation"][table]["columns"]
        return [{column: row.get(column) for column in columns} for row in self.plan["destination_rows"][table]]

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, *, plan: dict, identity: dict[str, str]) -> None:
        self.cursor_value = _Cursor(plan=plan, identity=identity)

    def cursor(self, *, dictionary: bool):
        assert dictionary is True
        return self.cursor_value


def test_auditor_collects_only_plan_bound_rows_and_reconciles() -> None:
    plan = _plan()
    connection = _Connection(
        plan=plan,
        identity={"DATABASE()": "obsidiandroid_core_prod", "CURRENT_USER()": "obsidiandroid_core_auditor@localhost"},
    )
    observed = _MODULE.collect_observed_rows(connection, plan)
    assert set(observed) == set(plan["destination_reconciliation"])
    assert reconcile_destination_rows(plan=plan, observed_rows=observed)["all_match"] is True


def test_auditor_rejects_a_writer_or_wrong_database_identity() -> None:
    plan = _plan()
    connection = _Connection(plan=plan, identity={"DATABASE()": "wrong", "CURRENT_USER()": "obsidiandroid_core_writer@localhost"})
    with pytest.raises(CoreImportError, match="did not select"):
        _MODULE.collect_observed_rows(connection, plan)


def test_auditor_command_has_no_import_or_source_extract_dependency() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "execute_import_plan" not in text
    assert "create_phase2c_source_extract" not in text
    assert "obsidiandroid_core_auditor@localhost" in text
