"""Tests for the offline-only Phase 1 Core-migration closeout checker."""

from __future__ import annotations

from pathlib import Path
import json

from scripts.core_migration import check_phase1_closeout as closeout


def _write_review_package(root: Path) -> None:
    ddl = root / closeout.DDL_RELATIVE_PATH
    ddl.parent.mkdir(parents=True, exist_ok=True)
    ddl.write_text(
        "-- DESIGN ONLY / PHASE 1: do not apply this file to a live database yet.\n"
        + "\n".join(f"CREATE TABLE {table} (id INT);" for table in closeout.EXPECTED_FOUNDATION_TABLES),
        encoding="utf-8",
    )
    inventory = root / closeout.INVENTORY_RELATIVE_PATH
    inventory.mkdir(parents=True, exist_ok=True)
    for name in closeout.REQUIRED_INVENTORY_FILES:
        (inventory / name).write_text("review evidence\n", encoding="utf-8")
    (inventory / closeout.FIXTURE_PREVIEW_FILENAME).write_text(
        json.dumps(
            {
                "dry_run": True,
                "run_id": closeout.FIXTURE_RUN_ID,
                "plan_sha256": "a" * 64,
                "proposed_destination_rows": closeout.EXPECTED_FIXTURE_ROWS,
                "fixture_classification": {
                    "storage_validation_fixture": True,
                    "publication_status": "NOT_APPLICABLE",
                    "frozen_benchmark_status": "not_frozen_benchmark",
                    "paper_reproduction_status": "not_a_paper_reproduction",
                },
            }
        ),
        encoding="utf-8",
    )


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


def test_closeout_blocks_an_incorrect_fixture_preview(tmp_path: Path) -> None:
    _write_review_package(tmp_path)
    preview = tmp_path / closeout.INVENTORY_RELATIVE_PATH / closeout.FIXTURE_PREVIEW_FILENAME
    payload = json.loads(preview.read_text(encoding="utf-8"))
    payload["fixture_classification"]["publication_status"] = "PUBLISHED"
    preview.write_text(json.dumps(payload), encoding="utf-8")

    report = closeout.evaluate_phase1_closeout(tmp_path, core_persistence_enabled=False)

    assert report["ready_for_human_phase2_review"] is False
    assert report["checks"]["fixture_preview_is_nonpublication_dry_run"]["ok"] is False
