"""Static checks for the non-mutating production Core audit command."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.core_migration.audit_contracts import CONTRACTS
from obsidiandroid.core_migration.migration_checksums import MIGRATION_CHECKSUMS


def test_provisioning_audit_is_inventory_only() -> None:
    text = Path("scripts/core_migration/audit_provisioned_core.py").read_text(encoding="utf-8")
    assert "Read-only" in text
    assert "INSERT " not in text
    assert "UPDATE " not in text
    assert "DELETE " not in text
    assert "CREATE " not in text
    assert "--contract" in text
    assert "CONTRACTS" in text
    from obsidiandroid.core_migration.audit_contracts import CONTRACTS as LIVE
    assert "phase2d_partial_0004" in LIVE


def test_phase_aware_contracts_cover_partial_and_final() -> None:
    assert "phase2d_partial_0004" in CONTRACTS
    assert "phase2d_schema_complete" in CONTRACTS
    assert set(CONTRACTS["phase2d_schema_complete"]["migrations"]) == set(MIGRATION_CHECKSUMS)
