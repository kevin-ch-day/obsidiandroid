"""Contract tests for the un-applied ObsidianDroid Core v1 evidence DDL."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

DDL_PATH = Path("database/core_migrations/0001_core_evidence_foundation.sql")
CONTRACT_DDL_PATH = Path("database/core_migrations/0002_core_evidence_contracts.sql")
RESULTS_DDL_PATH = Path("database/core_migrations/0003_core_results_contracts.sql")
LABELS_DDL_PATH = Path("database/core_migrations/0004_core_label_and_confusion_contracts.sql")
IMMUTABLE_0001_SHA256 = "fd65d0106b50484da3ca802f8a2b98649f9bac06993989c5602f09d30c0badae"

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
    import hashlib
    assert hashlib.sha256(DDL_PATH.read_bytes()).hexdigest() == IMMUTABLE_0001_SHA256


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


def test_follow_up_contract_migration_completes_the_same_seven_table_model() -> None:
    sql = CONTRACT_DDL_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE" not in sql
    assert "ALTER TABLE core_" in sql
    for required_contract in (
        "expected_sha256",
        "observed_sha256",
        "source_record_hash",
        "source_query_contract_version",
        "snapshot_key",
        "supersedes_run_id",
        "chk_core_run_status",
        "chk_core_artifact_availability",
        "chk_core_quality_finding_state",
        "chk_core_run_snapshot_kind",
        "chk_core_artifact_pointer_pair",
        "uq_core_quality_finding_source_record",
    ):
        assert required_contract in sql


def test_core_results_migration_is_additive_and_keeps_results_in_core() -> None:
    sql = RESULTS_DDL_PATH.read_text(encoding="utf-8")
    expected = (
        "core_run_stage", "core_feature_contract", "core_split_ledger",
        "core_model_execution", "core_model_metric", "core_prediction",
        "core_experiment", "core_experiment_metric", "core_permission_measure",
    )
    assert tuple(re.findall(r"CREATE TABLE (core_[a-z_]+)", sql)) == expected
    assert "erebus_threat_intel_prod" not in sql
    assert "android_permission_intel" not in sql
    for contract in ("fk_core_model_execution_feature", "fk_core_prediction_execution", "ordered_column_hash", "split_contract_hash"):
        assert contract in sql


def test_core_label_and_confusion_migration_keeps_ml_outputs_queryable() -> None:
    sql = LABELS_DDL_PATH.read_text(encoding="utf-8")
    assert tuple(re.findall(r"CREATE TABLE (core_[a-z_]+)", sql)) == (
        "core_label_contract", "core_label_assignment", "core_confusion_cell",
    )
    for contract in ("label_universe_hash", "taxonomy_version", "true_label", "predicted_label", "sample_count"):
        assert contract in sql
