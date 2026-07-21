"""Tests for hardened partial-0004 ledger remediation lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from obsidiandroid.core_migration.ledger_remediation import (
    FAILED_PRODUCTION_RECEIPT_ID,
    MIGRATION_0004_CHECKSUM,
    PRE_MIGRATION_BACKUP_SHA256,
    STATUS_APPLIED_AND_VERIFIED,
    STATUS_COMMITTED_BUT_POSTCHECK_FAILED,
    STATUS_FAILED_BEFORE_COMMIT,
    STATUS_PLANNED,
    CoreLedgerRemediationError,
    create_receipt_exclusive,
    load_failed_receipt,
    plan_or_apply_remediation,
    verify_backup_sha256,
)
from obsidiandroid.core_migration.migration_checksums import MIGRATION_CHECKSUMS
from obsidiandroid.core_migration.structural_digest import (
    compare_structural_digests,
    expected_structural_digest_from_sql,
    parse_expected_create_bodies,
)


REPO = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO / "database" / "core_migrations"
SQL_0004 = MIGRATIONS / "0004_core_label_and_confusion_contracts.sql"


def _ok_structure(*_args, **_kwargs):
    return {
        "tables": [],
        "table_digests": {},
        "physical_schema_verification_hash": "a" * 64,
        "live_digests": {},
    }


def test_load_failed_receipt_and_backup(tmp_path: Path) -> None:
    path = tmp_path / "failed.json"
    path.write_text(
        json.dumps(
            {
                "receipt_id": FAILED_PRODUCTION_RECEIPT_ID,
                "status": "failed",
                "error_type": "IntegrityError",
                "applied": ["0003"],
            }
        ),
        encoding="utf-8",
    )
    assert load_failed_receipt(path)["receipt_id"] == FAILED_PRODUCTION_RECEIPT_ID
    backup = tmp_path / "b.sql.gz"
    backup.write_bytes(b"x")
    digest = verify_backup_sha256(backup, expected=__import__("hashlib").sha256(b"x").hexdigest())
    assert len(digest) == 64
    with pytest.raises(CoreLedgerRemediationError):
        verify_backup_sha256(backup, expected=PRE_MIGRATION_BACKUP_SHA256)


def test_receipt_path_exists_before_execution(tmp_path: Path) -> None:
    receipt = tmp_path / "remediation.json"
    create_receipt_exclusive(receipt, {"status": STATUS_PLANNED})
    with pytest.raises(CoreLedgerRemediationError, match="existing remediation receipt"):
        plan_or_apply_remediation(
            connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("should not open db")),
            target_database="obsidiandroid_core_prod",
            migrations_dir=MIGRATIONS,
            sql_0004=SQL_0004,
            failed_receipt_path=tmp_path / "missing.json",
            backup_path=None,
            remediation_receipt_path=receipt,
            approve=False,
            approved_current_user="root@localhost",
            approved_server_attestation_sha256=None,
            application_commit=None,
        )


def test_reviewed_0004_sql_structural_self_compare() -> None:
    bodies = parse_expected_create_bodies(
        SQL_0004.read_text(encoding="utf-8"),
        ("core_label_contract", "core_label_assignment", "core_confusion_cell"),
    )
    for table, body in bodies.items():
        digest = expected_structural_digest_from_sql(table, body)
        assert compare_structural_digests(digest, digest) == []
        assert digest["columns"][0]["ordinal"] == 1


class _FakeCursor:
    def __init__(self) -> None:
        self.fail_on = None
        self._last: Any = None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        text = " ".join(sql.split())
        if self.fail_on == "insert" and text.startswith("INSERT INTO"):
            raise RuntimeError("insert failed")
        if text.startswith("SELECT DATABASE()"):
            self._last = ("od_core_phase2b_validate_20260720T000000Z", "root@localhost", "10.11.18-MariaDB")
        elif "@@hostname" in text:
            self._last = ("host", 3306, 1, "10.11.18-MariaDB", "MariaDB")
        elif text.startswith("SELECT migration_version") and "executor_id" not in text:
            self._last = [
                ("0001", MIGRATION_CHECKSUMS["0001"], "applied", None),
                ("0002", MIGRATION_CHECKSUMS["0002"], "applied", "r2"),
                ("0003", MIGRATION_CHECKSUMS["0003"], "applied", FAILED_PRODUCTION_RECEIPT_ID),
            ]
        elif text.startswith("SELECT migration_version, migration_checksum, execution_status, receipt_id, executor_id"):
            self._last = (
                "0004",
                MIGRATION_0004_CHECKSUM,
                "applied",
                "c" * 64,
                "obsidiandroid-core-results-ledger-remediator",
            )
        elif text.startswith("SELECT COUNT(*)"):
            self._last = (0,)
        elif text.startswith("SELECT run_id"):
            self._last = []
        else:
            self._last = None

    def fetchone(self):
        if isinstance(self._last, list):
            return None
        return self._last

    def fetchall(self):
        if isinstance(self._last, list):
            return self._last
        return []

    def close(self) -> None:
        return None


class _FakeConn:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor_obj = cursor
        self.fail_commit = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("commit failed")

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        return None


def _failed_receipt(tmp_path: Path) -> Path:
    path = tmp_path / "failed.json"
    path.write_text(
        json.dumps(
            {
                "receipt_id": FAILED_PRODUCTION_RECEIPT_ID,
                "status": "failed",
                "error_type": "IntegrityError",
                "applied": ["0003"],
                "application_commit": "deadbeef",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_failure_before_insert_writes_failed_before_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "obsidiandroid.core_migration.ledger_remediation.verify_partial_0004_structure",
        _ok_structure,
    )
    monkeypatch.setattr(
        "obsidiandroid.core_migration.ledger_remediation.verify_result_tables_empty",
        lambda *args, **kwargs: {},
    )
    cursor = _FakeCursor()
    cursor.fail_on = "insert"
    conn = _FakeConn(cursor)
    receipt = tmp_path / "remediation.json"
    with pytest.raises(RuntimeError, match="insert failed"):
        plan_or_apply_remediation(
            connection_factory=lambda: conn,
            target_database="od_core_phase2b_validate_20260720T000000Z",
            migrations_dir=MIGRATIONS,
            sql_0004=SQL_0004,
            failed_receipt_path=_failed_receipt(tmp_path),
            backup_path=None,
            remediation_receipt_path=receipt,
            approve=True,
            approved_current_user="root@localhost",
            approved_server_attestation_sha256=None,
            application_commit=None,
            require_failed_receipt_authority=True,
            require_production_fixture=False,
        )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == STATUS_FAILED_BEFORE_COMMIT
    assert conn.rolled_back is True


def test_commit_failure_is_failed_before_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "obsidiandroid.core_migration.ledger_remediation.verify_partial_0004_structure",
        _ok_structure,
    )
    monkeypatch.setattr(
        "obsidiandroid.core_migration.ledger_remediation.verify_result_tables_empty",
        lambda *args, **kwargs: {},
    )
    cursor = _FakeCursor()
    conn = _FakeConn(cursor)
    conn.fail_commit = True
    receipt = tmp_path / "remediation.json"
    with pytest.raises(RuntimeError, match="commit failed"):
        plan_or_apply_remediation(
            connection_factory=lambda: conn,
            target_database="od_core_phase2b_validate_20260720T000000Z",
            migrations_dir=MIGRATIONS,
            sql_0004=SQL_0004,
            failed_receipt_path=_failed_receipt(tmp_path),
            backup_path=None,
            remediation_receipt_path=receipt,
            approve=True,
            approved_current_user="root@localhost",
            approved_server_attestation_sha256=None,
            application_commit=None,
            require_failed_receipt_authority=True,
            require_production_fixture=False,
        )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == STATUS_FAILED_BEFORE_COMMIT


def test_postcheck_failure_writes_emergency_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _structure(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _ok_structure()
        raise CoreLedgerRemediationError("postcheck boom")

    monkeypatch.setattr(
        "obsidiandroid.core_migration.ledger_remediation.verify_partial_0004_structure",
        _structure,
    )
    monkeypatch.setattr(
        "obsidiandroid.core_migration.ledger_remediation.verify_result_tables_empty",
        lambda *args, **kwargs: {},
    )
    cursor = _FakeCursor()
    conn = _FakeConn(cursor)
    receipt = tmp_path / "remediation.json"
    with pytest.raises(CoreLedgerRemediationError, match="emergency_receipt"):
        plan_or_apply_remediation(
            connection_factory=lambda: conn,
            target_database="od_core_phase2b_validate_20260720T000000Z",
            migrations_dir=MIGRATIONS,
            sql_0004=SQL_0004,
            failed_receipt_path=_failed_receipt(tmp_path),
            backup_path=None,
            remediation_receipt_path=receipt,
            approve=True,
            approved_current_user="root@localhost",
            approved_server_attestation_sha256=None,
            application_commit=None,
            require_failed_receipt_authority=True,
            require_production_fixture=False,
        )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == STATUS_COMMITTED_BUT_POSTCHECK_FAILED
    assert payload["rollback_claimed"] is False
    assert list(tmp_path.glob("0004_ledger_remediation_EMERGENCY_*.json"))


def test_successful_finalize_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "obsidiandroid.core_migration.ledger_remediation.verify_partial_0004_structure",
        _ok_structure,
    )
    monkeypatch.setattr(
        "obsidiandroid.core_migration.ledger_remediation.verify_result_tables_empty",
        lambda *args, **kwargs: {},
    )
    cursor = _FakeCursor()
    conn = _FakeConn(cursor)
    receipt = tmp_path / "remediation.json"
    result = plan_or_apply_remediation(
        connection_factory=lambda: conn,
        target_database="od_core_phase2b_validate_20260720T000000Z",
        migrations_dir=MIGRATIONS,
        sql_0004=SQL_0004,
        failed_receipt_path=_failed_receipt(tmp_path),
        backup_path=None,
        remediation_receipt_path=receipt,
        approve=True,
        approved_current_user="root@localhost",
        approved_server_attestation_sha256=None,
        application_commit=None,
        require_failed_receipt_authority=True,
        require_production_fixture=False,
    )
    assert result["status"] == STATUS_APPLIED_AND_VERIFIED
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == STATUS_APPLIED_AND_VERIFIED
