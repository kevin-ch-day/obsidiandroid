"""Pure safety checks for the opt-in Core backup/recovery tool."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
import subprocess

import pytest

from scripts.core_migration import core_backup_rehearsal
from scripts.core_migration.core_backup_rehearsal import CORE_SCHEMA, _manifest_hash, _retarget_dump_line, _validate_restore_target


def test_core_restore_target_is_disposable_and_never_the_production_schema() -> None:
    assert _validate_restore_target("od_core_restore_20260719") == "od_core_restore_20260719"
    for value in (CORE_SCHEMA, "erebus_threat_intel_prod", "od_core_phase2b_validate", "od_core_restore_BAD"):
        with pytest.raises(RuntimeError):
            _validate_restore_target(value)


def test_core_dump_retargeting_changes_only_the_core_schema_token() -> None:
    source = "CREATE DATABASE /*!32312 IF NOT EXISTS*/ `obsidiandroid_core_prod`;\nUSE `obsidiandroid_core_prod`;\n"
    transformed = _retarget_dump_line(source, "od_core_restore_20260719")
    assert "obsidiandroid_core_prod" not in transformed
    assert "`od_core_restore_20260719`" in transformed


def test_core_backup_manifest_hash_detects_tampering() -> None:
    manifest = {"manifest_version": "obsidiandroid-core-backup-v1", "source_schema": CORE_SCHEMA}
    manifest["manifest_sha256"] = _manifest_hash(manifest)
    assert manifest["manifest_sha256"] == _manifest_hash(manifest)
    manifest["source_schema"] = "tampered"
    assert manifest["manifest_sha256"] != _manifest_hash(manifest)


def test_core_dump_writer_compresses_bytes_when_subprocess_uses_a_file_descriptor(tmp_path: Path, monkeypatch) -> None:
    """Regression: subprocess stdout must not bypass ``gzip.GzipFile.write``."""
    destination = tmp_path / "core.sql.gz"

    def fake_run(command, *, stdout, stderr, check):
        del command, stderr, check
        stdout.write(b"CREATE DATABASE `obsidiandroid_core_prod`;\n")
        return subprocess.CompletedProcess(args=["mariadb-dump"], returncode=0)

    monkeypatch.setattr(core_backup_rehearsal.subprocess, "run", fake_run)
    core_backup_rehearsal._write_gzip_dump(["mariadb-dump"], destination)
    assert destination.read_bytes().startswith(b"\x1f\x8b")
    with gzip.open(destination, "rb") as handle:
        assert handle.read() == b"CREATE DATABASE `obsidiandroid_core_prod`;\n"


def test_core_backup_failure_receipt_is_private_credential_free_and_immutable(tmp_path: Path) -> None:
    receipt = tmp_path / "backup.failure_receipt.json"
    written = core_backup_rehearsal._write_failure_receipt(  # pylint: disable=protected-access
        receipt,
        operation="create_backup",
        error=RuntimeError("password=must-not-appear"),
        context={"requested_output_dir": "/private/backup"},
    )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert written == receipt
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert payload["status"] == "failed"
    assert payload["error_type"] == "RuntimeError"
    assert "password" not in receipt.read_text(encoding="utf-8")
    assert core_backup_rehearsal._write_failure_receipt(  # pylint: disable=protected-access
        receipt,
        operation="create_backup",
        error=RuntimeError("changed"),
        context={},
    ) is None
