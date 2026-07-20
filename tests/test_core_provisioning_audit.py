"""Static checks for the non-mutating production Core audit command."""

from __future__ import annotations

from pathlib import Path

from scripts.core_migration.audit_provisioned_core import (
    CORE_RESULT_TABLES,
    EXPECTED_FIXTURE_COUNTS,
    EXPECTED_MIGRATIONS,
    EXPECTED_TABLES,
)


def test_provisioning_audit_is_inventory_only() -> None:
    text = Path("scripts/core_migration/audit_provisioned_core.py").read_text(encoding="utf-8")
    assert "Read-only audit" in text
    assert "INSERT " not in text
    assert "UPDATE " not in text
    assert "DELETE " not in text
    assert "CREATE " not in text
    assert "EXPECTED_MIGRATIONS" in text
    assert "fixture_contract_ok" in text
    assert "results_empty" in text


def test_provisioning_audit_expects_phase2d_nineteen_table_contract() -> None:
    assert set(EXPECTED_MIGRATIONS) == {"0001", "0002", "0003", "0004", "0005"}
    assert len(EXPECTED_TABLES) == 19
    assert CORE_RESULT_TABLES <= EXPECTED_TABLES
    assert EXPECTED_FIXTURE_COUNTS == {
        "core_profile": 1,
        "core_source_snapshot": 1,
        "core_run": 1,
        "core_run_sample": 9716,
        "core_artifact": 57,
        "core_quality_finding": 0,
    }
    assert "label_contract" in CORE_RESULT_TABLES
    assert "core_label_contract" not in EXPECTED_TABLES
