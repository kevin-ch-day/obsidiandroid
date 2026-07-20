"""Strict private Phase 2C role-credential contracts with synthetic files."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from obsidiandroid.core_migration.mapping import CoreImportError
from obsidiandroid.core_migration.private_credentials import (
    Phase2CCredentialRole,
    load_disposable_rehearsal_writer_credentials,
    load_phase2c_credentials,
)


def _values(role: Phase2CCredentialRole) -> dict[str, str]:
    if role is Phase2CCredentialRole.CORE_WRITER:
        return {
            "OBSIDIANDROID_CORE_DB_HOST": "localhost", "OBSIDIANDROID_CORE_DB_PORT": "3306",
            "OBSIDIANDROID_CORE_DB_USER": "obsidiandroid_core_writer", "OBSIDIANDROID_CORE_DB_PASSWORD": "synthetic-secret",
            "OBSIDIANDROID_CORE_DB_NAME": "obsidiandroid_core_prod", "OBSIDIANDROID_CORE_PERSISTENCE_ENABLED": "false",
        }
    user = "obsidiandroid_erebus_reader" if role is Phase2CCredentialRole.EREBUS_READER else "obsidiandroid_core_auditor"
    database = "erebus_threat_intel_prod" if role is Phase2CCredentialRole.EREBUS_READER else "obsidiandroid_core_prod"
    return {
        "OBSIDIANDROID_DB_HOST": "localhost", "OBSIDIANDROID_DB_PORT": "3306", "OBSIDIANDROID_DB_USER": user,
        "OBSIDIANDROID_DB_PASSWORD": "synthetic-secret", "OBSIDIANDROID_DB_NAME": database,
    }


def _credential(tmp_path: Path, role: Phase2CCredentialRole, values: dict[str, str] | None = None) -> Path:
    tmp_path.chmod(0o700)
    path = tmp_path / f"{role}.env"
    payload = values or _values(role)
    path.write_text("".join(f"{key}={value}\n" for key, value in payload.items()), encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("role", list(Phase2CCredentialRole))
def test_loads_each_valid_role_contract(tmp_path: Path, role: Phase2CCredentialRole) -> None:
    credentials = load_phase2c_credentials(_credential(tmp_path, role), role)
    assert credentials.role is role
    assert credentials.host == "localhost"
    assert "synthetic-secret" not in repr(credentials)


def test_rejects_insecure_mode_symlink_and_wrong_role_without_secret(tmp_path: Path) -> None:
    writer = _credential(tmp_path, Phase2CCredentialRole.CORE_WRITER)
    writer.chmod(0o640)
    with pytest.raises(CoreImportError) as insecure:
        load_phase2c_credentials(writer, Phase2CCredentialRole.CORE_WRITER)
    assert "synthetic-secret" not in str(insecure.value)
    writer.chmod(0o600)
    with pytest.raises(CoreImportError, match="role contract"):
        load_phase2c_credentials(writer, Phase2CCredentialRole.CORE_AUDITOR)
    link = tmp_path / "writer-link.env"
    link.symlink_to(writer)
    with pytest.raises(CoreImportError, match="regular private"):
        load_phase2c_credentials(link, Phase2CCredentialRole.CORE_WRITER)


@pytest.mark.parametrize("mutation", [
    {"OBSIDIANDROID_CORE_DB_PORT": "not-a-port"},
    {"OBSIDIANDROID_CORE_DB_HOST": "remote.example"},
    {"OBSIDIANDROID_CORE_DB_NAME": "wrong"},
    {"OBSIDIANDROID_CORE_PERSISTENCE_ENABLED": "true"},
])
def test_writer_contract_rejects_invalid_policy_values(tmp_path: Path, mutation: dict[str, str]) -> None:
    values = _values(Phase2CCredentialRole.CORE_WRITER)
    values.update(mutation)
    with pytest.raises(CoreImportError):
        load_phase2c_credentials(_credential(tmp_path, Phase2CCredentialRole.CORE_WRITER, values), Phase2CCredentialRole.CORE_WRITER)


def test_rejects_malformed_duplicate_missing_and_insecure_parent(tmp_path: Path) -> None:
    malformed = _credential(tmp_path, Phase2CCredentialRole.CORE_AUDITOR)
    malformed.write_text("not-an-entry\n", encoding="utf-8")
    malformed.chmod(0o600)
    with pytest.raises(CoreImportError, match="malformed"):
        load_phase2c_credentials(malformed, Phase2CCredentialRole.CORE_AUDITOR)
    duplicate = _credential(tmp_path, Phase2CCredentialRole.CORE_AUDITOR)
    duplicate.write_text(duplicate.read_text(encoding="utf-8") + "OBSIDIANDROID_DB_USER=duplicate\n", encoding="utf-8")
    duplicate.chmod(0o600)
    with pytest.raises(CoreImportError, match="duplicate"):
        load_phase2c_credentials(duplicate, Phase2CCredentialRole.CORE_AUDITOR)
    insecure_parent = tmp_path / "insecure"
    insecure_parent.mkdir(mode=0o755)
    path = _credential(insecure_parent, Phase2CCredentialRole.CORE_AUDITOR)
    insecure_parent.chmod(0o755)
    with pytest.raises(CoreImportError, match="parent"):
        load_phase2c_credentials(path, Phase2CCredentialRole.CORE_AUDITOR)


def test_rejects_wrong_owner_when_platform_can_simulate_it(tmp_path: Path, monkeypatch) -> None:
    path = _credential(tmp_path, Phase2CCredentialRole.CORE_AUDITOR)
    actual_stat = path.stat()
    monkeypatch.setattr(os, "geteuid", lambda: actual_stat.st_uid + 1)
    with pytest.raises(CoreImportError, match="owned"):
        load_phase2c_credentials(path, Phase2CCredentialRole.CORE_AUDITOR)


def test_disposable_rehearsal_writer_is_pinned_to_one_phase2c_target(tmp_path: Path) -> None:
    target = "od_core_phase2c_rehearsal_20260720T120000Z"
    values = _values(Phase2CCredentialRole.CORE_WRITER)
    values["OBSIDIANDROID_CORE_DB_NAME"] = target
    path = _credential(tmp_path, Phase2CCredentialRole.CORE_WRITER, values)
    credentials = load_disposable_rehearsal_writer_credentials(path, target_database=target)
    assert credentials.database == target
    with pytest.raises(CoreImportError, match="schema does not match"):
        load_disposable_rehearsal_writer_credentials(path, target_database="od_core_phase2c_rehearsal_20260720T120001Z")
    with pytest.raises(CoreImportError):
        load_disposable_rehearsal_writer_credentials(path, target_database="obsidiandroid_core_prod")
