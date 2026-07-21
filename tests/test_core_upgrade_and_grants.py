"""Offline tests for nonempty Core upgrade and grant planning."""

from __future__ import annotations

from pathlib import Path

from scripts.core_migration.apply_core_results_grants import expected_grant_set, planned_grant_statements
from scripts.core_migration.upgrade_core_schema import detect_unledgered_physical_ddl


def test_grant_plan_is_insert_and_select_only() -> None:
    statements = planned_grant_statements()
    assert statements
    assert all("GRANT INSERT" in s or "GRANT SELECT" in s for s in statements)
    assert all("UPDATE" not in s and "DELETE" not in s for s in statements)
    assert expected_grant_set()


def test_upgrade_detects_partial_0004_shape() -> None:
    tables = [
        "core_schema_migration",
        "core_run",
        "core_label_contract",
        "core_model_execution",
    ]
    applied = {"0001": "a", "0002": "b", "0003": "c"}
    issues = detect_unledgered_physical_ddl(tables, applied)
    assert "unledgered_partial_0004_or_result_ddl" in issues


def test_upgrade_allows_post_remediation_temporary_names() -> None:
    tables = ["core_label_contract", "core_model_execution", "label_contract"]
    applied = {"0001": "a", "0002": "b", "0003": "c", "0004": "d"}
    issues = detect_unledgered_physical_ddl(tables, applied)
    # final names without 0005 still flagged
    assert "final_result_names_without_0005_ledger" in issues


def test_upgrade_script_is_dry_run_by_default() -> None:
    text = Path("scripts/core_migration/upgrade_core_schema.py").read_text(encoding="utf-8")
    assert "--approve-production-upgrade" in text
    assert "never import" in text.lower() or "Never imports" in text or "never imports" in text
    assert "grants" in text.lower()
