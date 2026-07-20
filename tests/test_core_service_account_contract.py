"""Static guardrails for Core account automation; it must never carry a secret."""

from __future__ import annotations

import importlib.util
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
    assert '"status": "failed"' in text
    assert "credential_reference_state" in text
    assert text.index("created = _create_accounts") < text.index("credential_references = _write_credential_references")
    assert "Refusing to overwrite an existing service-account receipt" in text


def test_read_only_audit_checks_privilege_separation() -> None:
    text = Path("scripts/core_migration/audit_provisioned_core.py").read_text(encoding="utf-8")
    assert "EXPECTED_ACCOUNTS" in text
    assert "negative_boundaries" in text
    assert "no_core_writer_migration_ledger_privilege" in text
    assert "no_unrelated_table_privileges" in text
    assert "no_service_routine_privilege" in text
    assert "account_set_ok" in text
    assert "obsidiandroid_pipeline_reader" in text
    assert "no_normal_reader_core_privilege" in text
    assert "INSERT " not in text
    assert "UPDATE " not in text
    assert "DELETE " not in text


def test_read_only_audit_allows_the_approved_normal_reader_but_no_unknown_account() -> None:
    path = Path("scripts/core_migration/audit_provisioned_core.py")
    spec = importlib.util.spec_from_file_location("core_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    approved = {
        **module.EXPECTED_ACCOUNTS,
        **module.APPROVED_RUNTIME_ACCOUNTS,
    }
    assert module.account_contract(approved)["account_set_ok"] is True

    with_unknown = {**approved, "obsidiandroid_unreviewed": approved["obsidiandroid_core_auditor"]}
    result = module.account_contract(with_unknown)
    assert result["account_set_ok"] is False
    assert result["unexpected_accounts"] == ["obsidiandroid_unreviewed"]
