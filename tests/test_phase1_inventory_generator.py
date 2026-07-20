"""Focused contracts for the read-only Phase 1 inventory generator."""

from __future__ import annotations

from scripts.core_migration import generate_phase1_inventory as inventory


def test_active_writer_discovery_includes_all_declared_tables() -> None:
    tables = inventory._writer_table_lines()

    assert len(tables) == 25
    assert "dangerous_distribution_by_type" in tables
    assert "analysis_run" in tables


def test_report_contracts_expose_required_closeout_fields() -> None:
    assert "current_readers" in inventory.DERIVED_FIELDS
    assert "rollback_behavior" in inventory.WRITER_FIELDS
    assert "archive_recovery_status" in inventory.ARTIFACT_FIELDS
    assert "resulting_objects_status" in inventory.MIGRATION_FIELDS
