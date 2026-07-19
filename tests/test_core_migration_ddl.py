"""Contract tests for the un-applied ObsidianDroid Core v1 evidence DDL."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

DDL_PATH = Path("database/core_migrations/0001_core_evidence_foundation.sql")

EXPECTED_TABLES = (
    "core_schema_migration",
    "core_profile",
    "core_source_snapshot",
    "core_run",
    "core_run_sample",
    "core_artifact",
    "core_quality_finding",
)


def test_core_v1_ddl_is_present_and_explicitly_unapplied() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8")
    assert "DESIGN ONLY / PHASE 1" in sql
    assert "do not apply this file to a live database" in sql
    assert "CREATE DATABASE" not in sql
    assert re.search(r"^USE\s+", sql, flags=re.MULTILINE) is None


def test_core_v1_ddl_declares_only_reviewed_evidence_tables() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8")
    declared = tuple(re.findall(r"CREATE TABLE (core_[a-z_]+)", sql))
    assert declared == EXPECTED_TABLES
    assert "obsidiandroid_research" not in sql
    for table in EXPECTED_TABLES:
        assert re.search(rf"CREATE TABLE {table}\b", sql), table


def test_core_v1_ddl_has_integrity_links_and_utc_precision() -> None:
    sql = DDL_PATH.read_text(encoding="utf-8")
    assert sql.count("DATETIME(6)") >= 8
    for foreign_key in (
        "fk_core_run_profile",
        "fk_core_run_snapshot",
        "fk_core_run_sample_run",
        "fk_core_artifact_run",
        "fk_core_quality_finding_run",
    ):
        assert foreign_key in sql
    for checksum_column in (
        "migration_checksum",
        "cohort_checksum",
        "taxonomy_checksum",
        "permission_snapshot_checksum",
        "record_checksum",
        "sha256",
    ):
        assert checksum_column in sql
