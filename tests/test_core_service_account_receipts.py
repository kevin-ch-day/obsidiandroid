"""Credential-free receipt handling for Core account provisioning."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _module():
    path = Path("scripts/core_migration/apply_service_accounts.py")
    spec = importlib.util.spec_from_file_location("core_service_accounts", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_receipt_is_private_and_not_overwritten(tmp_path: Path) -> None:
    module = _module()
    receipt = tmp_path / "receipt.json"
    module._write_receipt(receipt, {"status": "planned"})
    assert receipt.stat().st_mode & 0o777 == 0o600
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        module._write_receipt(receipt, {"status": "changed"})


def test_failure_receipt_records_only_effect_metadata() -> None:
    module = _module()
    receipt = module._failure_receipt(
        created_roles=["core_migrator"],
        applied_grants=["GRANT SELECT ON safe.table"],
        credential_reference_state="not_attempted",
        error=RuntimeError("password=must-not-appear"),
    )
    assert receipt["status"] == "failed"
    assert receipt["created_roles"] == ["core_migrator"]
    assert receipt["error_type"] == "RuntimeError"
    assert "password" not in repr(receipt)
