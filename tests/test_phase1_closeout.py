"""Tests for the offline-only Phase 1 Core-migration closeout checker."""

from __future__ import annotations

from pathlib import Path

from scripts.core_migration import check_phase1_closeout as closeout


def _write_review_package(root: Path) -> None:
    ddl = root / closeout.DDL_RELATIVE_PATH
    ddl.parent.mkdir(parents=True, exist_ok=True)
    ddl.write_text(
        "-- DESIGN ONLY / PHASE 1: do not apply this file to a live database yet.\n",
        encoding="utf-8",
    )
    inventory = root / closeout.INVENTORY_RELATIVE_PATH
    inventory.mkdir(parents=True, exist_ok=True)
    for name in closeout.REQUIRED_INVENTORY_FILES:
        (inventory / name).write_text("review evidence\n", encoding="utf-8")


def test_closeout_is_ready_only_for_complete_disabled_phase1_package(tmp_path: Path) -> None:
    _write_review_package(tmp_path)

    report = closeout.evaluate_phase1_closeout(tmp_path, core_persistence_enabled=False)

    assert report["ready_for_human_phase2_review"] is True
    assert report["database_accessed"] is False
    assert report["database_writes"] is False


def test_closeout_blocks_when_core_persistence_is_enabled(tmp_path: Path) -> None:
    _write_review_package(tmp_path)

    report = closeout.evaluate_phase1_closeout(tmp_path, core_persistence_enabled=True)

    assert report["ready_for_human_phase2_review"] is False
    assert report["checks"]["core_persistence_disabled"]["ok"] is False


def test_closeout_reports_missing_local_inventory(tmp_path: Path) -> None:
    ddl = tmp_path / closeout.DDL_RELATIVE_PATH
    ddl.parent.mkdir(parents=True, exist_ok=True)
    ddl.write_text("-- DESIGN ONLY / PHASE 1: do not apply this file to a live database yet.\n", encoding="utf-8")

    report = closeout.evaluate_phase1_closeout(tmp_path, core_persistence_enabled=False)

    assert report["ready_for_human_phase2_review"] is False
    assert report["checks"]["generated_inventory_present"]["ok"] is False


def test_closeout_checker_has_no_database_execution_surface() -> None:
    source = Path(closeout.__file__).read_text(encoding="utf-8")

    assert "execute_query(" not in source
    assert "execute_core_query(" not in source
    assert "core_database_connection(" not in source
