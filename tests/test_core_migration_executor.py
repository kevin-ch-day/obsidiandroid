"""Offline tests for the Core-only numbered migration executor."""

from __future__ import annotations

from pathlib import Path

import pytest

from obsidiandroid.core_migration.executor import CoreMigrationError, apply_migrations, discover_migrations, validate_target_name


def _write(directory: Path, name: str, text: str = "SELECT 1;") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def test_discover_migrations_is_ordered_and_hashed(tmp_path: Path) -> None:
    _write(tmp_path, "0001_first.sql")
    _write(tmp_path, "0002_second.sql")
    found = discover_migrations(tmp_path)
    assert [item.version for item in found] == ["0001", "0002"]
    assert all(len(item.checksum) == 64 for item in found)


def test_discover_migrations_rejects_gap_and_invalid_name(tmp_path: Path) -> None:
    _write(tmp_path, "0001_first.sql")
    _write(tmp_path, "0003_third.sql")
    with pytest.raises(CoreMigrationError, match="contiguous"):
        discover_migrations(tmp_path)
    (tmp_path / "not-a-migration.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(CoreMigrationError, match="Invalid"):
        discover_migrations(tmp_path)


@pytest.mark.parametrize("name", ["erebus_threat_intel_prod", "android_permission_intel", "obsidiandroid_core_prod", "phase2a_restore"])
def test_protected_schema_is_rejected(name: str) -> None:
    with pytest.raises(CoreMigrationError):
        validate_target_name(name)


def test_dry_run_never_needs_connection_and_writes_receipt(tmp_path: Path) -> None:
    _write(tmp_path / "migrations", "0001_first.sql")
    receipt = tmp_path / "receipt.json"
    result = apply_migrations(
        target_database="od_core_phase2b_validate_20260719T120000Z",
        migrations_dir=tmp_path / "migrations",
        dry_run=True,
        receipt_path=receipt,
    )
    assert result["status"] == "planned"
    assert receipt.exists()
