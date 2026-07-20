"""Static checks for the non-mutating production Core audit command."""

from __future__ import annotations

from pathlib import Path


def test_provisioning_audit_is_inventory_only() -> None:
    text = Path("scripts/core_migration/audit_provisioned_core.py").read_text(encoding="utf-8")
    assert "Read-only audit" in text
    assert "INSERT " not in text
    assert "UPDATE " not in text
    assert "DELETE " not in text
    assert "CREATE " not in text
    assert "EXPECTED_MIGRATIONS" in text
    assert "evidence_empty" in text
