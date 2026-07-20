"""Static guardrails for Core account automation; it must never carry a secret."""

from __future__ import annotations

from pathlib import Path


def test_account_script_uses_local_hosts_and_narrow_grants() -> None:
    text = Path("scripts/core_migration/apply_service_accounts.py").read_text(encoding="utf-8")
    assert 'HOST = "localhost"' in text
    assert "'%'" not in text
    assert "GRANT OPTION" not in text
    assert "CREATE USER" in text
    assert "ACCOUNT LOCK" in text
    assert "GRANT DELETE" not in text
    assert "Password123" not in text


def test_read_only_audit_checks_privilege_separation() -> None:
    text = Path("scripts/core_migration/audit_provisioned_core.py").read_text(encoding="utf-8")
    assert "EXPECTED_ACCOUNTS" in text
    assert "negative_boundaries" in text
    assert "no_core_writer_migration_ledger_privilege" in text
    assert "no_unrelated_table_privileges" in text
    assert "no_service_routine_privilege" in text
    assert "account_set_ok" in text
    assert "INSERT " not in text
    assert "UPDATE " not in text
    assert "DELETE " not in text
