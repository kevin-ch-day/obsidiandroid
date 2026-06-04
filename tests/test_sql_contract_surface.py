from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_ROOT = REPO_ROOT / "database" / "sql"


def _read_sql(name: str) -> str:
    return (SQL_ROOT / name).read_text(encoding="utf-8")


def test_sql_surface_is_reduced_to_live_contract_files() -> None:
    expected = {
        "README.md",
        "label_authority_audit.sql",
        "label_authority_backfill.sql",
        "label_authority_foundation.sql",
        "label_authority_reference_seed.sql",
        "label_authority_schema_smoke.sql",
        "label_authority_vendor_evidence_backfill.sql",
        "label_authority_vendor_evidence_load_template.sql",
        "malware_artifact_ingest_queue_buffer_audit.sql",
        "malware_artifact_ingest_queue_prune_materialized_nonprocessing_rows.sql",
        "view_android_sample_family_type_authority.sql",
        "view_android_sample_family_type_authority_smoke.sql",
    }
    observed = {path.name for path in SQL_ROOT.iterdir() if path.is_file()}
    assert observed == expected


def test_live_sql_contract_files_do_not_hardcode_environment_schema() -> None:
    live_files = [
        "label_authority_audit.sql",
        "label_authority_backfill.sql",
        "label_authority_foundation.sql",
        "label_authority_reference_seed.sql",
        "label_authority_schema_smoke.sql",
        "label_authority_vendor_evidence_backfill.sql",
        "label_authority_vendor_evidence_load_template.sql",
        "malware_artifact_ingest_queue_buffer_audit.sql",
        "malware_artifact_ingest_queue_prune_materialized_nonprocessing_rows.sql",
        "view_android_sample_family_type_authority.sql",
        "view_android_sample_family_type_authority_smoke.sql",
    ]
    for name in live_files:
        sql = _read_sql(name)
        assert "USE erebus_database_dev;" not in sql
        assert "USE erebus_threat_intel_prod;" not in sql


def test_authority_sql_views_keep_active_family_and_alias_filters() -> None:
    authority_view_sql = _read_sql("view_android_sample_family_type_authority.sql")
    foundation_sql = _read_sql("label_authority_foundation.sql")

    assert "AND fam.is_active = 1" in authority_view_sql
    assert "AND alias.is_active = 1" in authority_view_sql
    assert "LEFT JOIN vendor_label_generic_token_fact AS gt" in authority_view_sql
    assert "resolved_token_policy_held_not_family" in authority_view_sql
    assert "AND fam.is_active = 1" in foundation_sql


def test_authority_foundation_and_backfill_keep_identity_dedup_contracts() -> None:
    foundation_sql = _read_sql("label_authority_foundation.sql")
    backfill_sql = _read_sql("label_authority_backfill.sql")
    template_sql = _read_sql("label_authority_vendor_evidence_load_template.sql")
    evidence_backfill_sql = _read_sql("label_authority_vendor_evidence_backfill.sql")

    assert "active_sample_id INT UNSIGNED AS" in foundation_sql
    assert "authority_content_sha1 CHAR(40) AS" in foundation_sql
    assert "UNIQUE KEY uq_malware_family_authority_active_sample (active_sample_id)" in foundation_sql
    assert "UNIQUE KEY uq_malware_family_authority_content (authority_content_sha1)" in foundation_sql
    assert "evidence_identity_sha1 CHAR(40) AS" in foundation_sql
    assert "UNIQUE KEY uq_mfle_identity (evidence_identity_sha1)" in foundation_sql

    assert "tmp_malware_family_authority_seed" in backfill_sql
    assert "auth.authority_content_sha1 <> seed.authority_content_sha1" in backfill_sql
    assert "auth.authority_content_sha1 = seed.authority_content_sha1" in backfill_sql
    assert "e.evidence_identity_sha1 = SHA1(" in template_sql
    assert "e.evidence_identity_sha1 = SHA1(" in evidence_backfill_sql

