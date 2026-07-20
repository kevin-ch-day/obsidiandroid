"""Pure safety checks for the opt-in Core backup/recovery tool."""

from __future__ import annotations

import pytest

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
