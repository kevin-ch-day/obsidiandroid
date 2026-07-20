"""Offline tests for partial-0004 ledger remediation helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.core_migration.ledger_remediation import (
    FAILED_PRODUCTION_RECEIPT_ID,
    MIGRATION_0004_CHECKSUM,
    PRE_MIGRATION_BACKUP_SHA256,
    CoreLedgerRemediationError,
    build_ledger_row,
    build_remediation_notes,
    compare_table_digests,
    expected_table_digest_from_sql,
    load_failed_receipt,
    parse_expected_create_bodies,
    physical_schema_verification_hash,
    verify_backup_sha256,
)


def test_load_failed_receipt_requires_incident_authority(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
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
    path.write_text(json.dumps({"receipt_id": "nope", "status": "failed", "error_type": "IntegrityError", "applied": ["0003"]}), encoding="utf-8")
    with pytest.raises(CoreLedgerRemediationError, match="receipt ID"):
        load_failed_receipt(path)


def test_verify_backup_sha256(tmp_path: Path) -> None:
    backup = tmp_path / "backup.sql.gz"
    backup.write_bytes(b"demo-backup")
    digest = verify_backup_sha256(backup, expected=__import__("hashlib").sha256(b"demo-backup").hexdigest())
    assert len(digest) == 64
    with pytest.raises(CoreLedgerRemediationError, match="backup SHA-256"):
        verify_backup_sha256(backup, expected=PRE_MIGRATION_BACKUP_SHA256)


def test_reviewed_0004_sql_parses_and_compares_to_itself() -> None:
    sql = Path("database/core_migrations/0004_core_label_and_confusion_contracts.sql").read_text(encoding="utf-8")
    bodies = parse_expected_create_bodies(sql)
    digests = {
        table: expected_table_digest_from_sql(table, body) for table, body in bodies.items()
    }
    assert set(digests) == {
        "core_label_contract",
        "core_label_assignment",
        "core_confusion_cell",
    }
    for table, digest in digests.items():
        assert compare_table_digests(digest, digest) == []
    assert len(physical_schema_verification_hash(digests)) == 64


def test_build_ledger_row_uses_remediator_identity() -> None:
    notes = build_remediation_notes(
        failed_receipt_id=FAILED_PRODUCTION_RECEIPT_ID,
        backup_sha256=PRE_MIGRATION_BACKUP_SHA256,
        verification_hash="a" * 64,
    )
    row = build_ledger_row(
        migration_checksum=MIGRATION_0004_CHECKSUM,
        application_commit="5ddae57",
        mariadb_version="10.11.18-MariaDB",
        receipt_id="b" * 64,
        notes=notes,
    )
    assert row["migration_version"] == "0004"
    assert row["executor_id"] == "obsidiandroid-core-results-ledger-remediator"
    assert FAILED_PRODUCTION_RECEIPT_ID in row["notes"]
    assert PRE_MIGRATION_BACKUP_SHA256 in row["notes"]
    assert "ddl_not_rerun=true" in row["notes"]


def test_remediation_script_is_fail_closed_by_default() -> None:
    text = Path("scripts/core_migration/remediate_partial_0004_ledger.py").read_text(encoding="utf-8")
    assert "--approve-ledger-repair" in text
    assert "Refusing to overwrite an existing remediation receipt" in text
    assert "ddl_rerun" in text
    assert "REMEDIATION_EXECUTOR_ID" in text
