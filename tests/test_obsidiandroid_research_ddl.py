"""Contract tests for ObsidianDroid research database DDL drafts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

DDL_DIR = Path("database/sql/obsidiandroid")

EXPECTED_TABLES = (
    "profiles",
    "runs",
    "samples",
    "sample_label_facts",
    "profile_membership",
    "permission_vocabulary",
    "sample_permission_facts",
    "permission_pattern_facts",
    "model_metrics",
    "prediction_facts",
    "quality_flags",
    "split_assignments",
    "release_manifests",
)

EXPECTED_DDL_FILES = (
    "001_create_core_tables.sql",
    "002_create_indexes.sql",
    "003_create_views.sql",
    "README.md",
)

CURATION_STATES = (
    "benchmark_include",
    "exploratory_include",
    "diagnostic_only",
    "audit_only",
    "needs_review",
    "exclude_from_training",
    "exclude_from_claims",
)


@pytest.mark.parametrize("filename", EXPECTED_DDL_FILES)
def test_obsidiandroid_ddl_files_exist(filename: str) -> None:
    assert (DDL_DIR / filename).is_file()


def test_core_ddl_declares_research_schema_and_tables() -> None:
    sql = (DDL_DIR / "001_create_core_tables.sql").read_text(encoding="utf-8")
    assert "obsidiandroid_research" in sql
    assert "OBSIDIANDROID_RESEARCH_DB_NAME" in sql
    for table in EXPECTED_TABLES:
        assert re.search(rf"CREATE TABLE IF NOT EXISTS {table}\b", sql), table
    assert "source_git_commit" in sql
    assert "source_git_tag" in sql
    assert "code_version" in sql
    for state in CURATION_STATES:
        assert state in sql


def test_index_ddl_targets_expected_tables() -> None:
    sql = (DDL_DIR / "002_create_indexes.sql").read_text(encoding="utf-8")
    assert "USE obsidiandroid_research" in sql
    assert "idx_runs_profile_id" in sql
    assert "idx_profile_membership_curation_state" in sql
    assert "idx_release_manifests_git_tag" in sql


def test_view_ddl_includes_release_and_curation_views() -> None:
    sql = (DDL_DIR / "003_create_views.sql").read_text(encoding="utf-8")
    assert "v_release_run_map" in sql
    assert "v_run_curation_summary" in sql
    assert "v_sample_permissions_present" in sql
