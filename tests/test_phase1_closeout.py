"""Tests for the offline-only Phase 1 Core-migration closeout checker."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.core_migration import check_phase1_closeout as closeout


def _write_csv(path: Path, fields: set[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(fields))
        writer.writeheader()
        writer.writerows(rows)


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
    report_names = []
    writer_tables = ["dangerous_distribution_by_type", *[f"warehouse_table_{index}" for index in range(24)]]
    for name in closeout.REQUIRED_INVENTORY_FILES:
        path = inventory / name
        report_names.append(name)
        if name in closeout.REQUIRED_COLUMNS:
            fields = closeout.REQUIRED_COLUMNS[name]
            row = {field: "value" for field in fields}
            if name == "derived_object_inventory.csv":
                rows = [{**row, "object_name": table, "current_writer": "stage_results_warehouse.py"} for table in writer_tables]
            elif name == "warehouse_writer_inventory.csv":
                rows = [{**row, "target_object": table, "sql_operation": "CREATE_TABLE_IF_NOT_EXISTS"} for table in writer_tables]
            else:
                rows = [row]
            _write_csv(path, fields, rows)
        elif name == "core_migration_disposition_matrix.md":
            path.write_text("# Matrix\n\n| object_name |\n|---|\n" + "".join(f"| {table} |\n" for table in writer_tables), encoding="utf-8")
        else:
            path.write_text("review evidence\n", encoding="utf-8")
    (inventory / closeout.FIXTURE_PREVIEW_FILENAME).write_text(
        json.dumps({
            "dry_run": True, "run_id": closeout.FIXTURE_RUN_ID, "plan_sha256": "a" * 64,
            "proposed_destination_rows": closeout.EXPECTED_FIXTURE_ROWS,
            "fixture_classification": {"storage_validation_fixture": True, "publication_status": "NOT_APPLICABLE", "frozen_benchmark_status": "not_frozen_benchmark", "paper_reproduction_status": "not_a_paper_reproduction"},
        }),
        encoding="utf-8",
    )
    lifecycle = root / closeout.LIFECYCLE_TEST_RELATIVE_PATH
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    lifecycle.write_text("# synthetic lifecycle test\n", encoding="utf-8")
    manifest = inventory / closeout.PACKAGE_MANIFEST_FILENAME
    manifest.write_text(json.dumps({"reports": [{"file": name} for name in report_names]}), encoding="utf-8")
    (inventory / closeout.PACKAGE_MANIFEST_CHECKSUM_FILENAME).write_text(
        f"{hashlib.sha256(manifest.read_bytes()).hexdigest()}  {manifest.name}\n", encoding="utf-8"
    )


def test_closeout_is_ready_only_for_complete_disabled_phase1_package(tmp_path: Path) -> None:
    _write_review_package(tmp_path)
    report = closeout.evaluate_phase1_closeout(tmp_path, core_persistence_enabled=False)
    assert report["historical_contract_complete"] is True
    assert report["database_accessed"] is False
    assert report["database_writes"] is False


def test_closeout_blocks_when_core_persistence_is_enabled(tmp_path: Path) -> None:
    _write_review_package(tmp_path)
    report = closeout.evaluate_phase1_closeout(tmp_path, core_persistence_enabled=True)
    assert report["historical_contract_complete"] is False
    assert report["checks"]["core_persistence_disabled"]["ok"] is False


def test_closeout_reports_missing_local_inventory(tmp_path: Path) -> None:
    ddl = tmp_path / closeout.DDL_RELATIVE_PATH
    ddl.parent.mkdir(parents=True, exist_ok=True)
    ddl.write_text("-- DESIGN ONLY / PHASE 1: do not apply this file to a live database yet.\n", encoding="utf-8")
    report = closeout.evaluate_phase1_closeout(tmp_path, core_persistence_enabled=False)
    assert report["historical_contract_complete"] is False
    assert report["checks"]["generated_inventory_present"]["ok"] is False


def test_closeout_blocks_missing_writer_created_table_from_derived_inventory(tmp_path: Path) -> None:
    _write_review_package(tmp_path)
    derived = tmp_path / closeout.INVENTORY_RELATIVE_PATH / "derived_object_inventory.csv"
    _write_csv(derived, closeout.REQUIRED_COLUMNS[derived.name], [{field: "value" for field in closeout.REQUIRED_COLUMNS[derived.name]}])
    report = closeout.evaluate_phase1_closeout(tmp_path, core_persistence_enabled=False)
    assert report["historical_contract_complete"] is False
    assert report["checks"]["writer_created_tables_covered"]["ok"] is False


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
    assert report["historical_contract_complete"] is False
    assert report["checks"]["fixture_preview_is_nonpublication_dry_run"]["ok"] is False
