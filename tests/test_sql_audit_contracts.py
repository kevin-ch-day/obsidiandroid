from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_read_only_audit_sql_does_not_hardcode_dev_schema() -> None:
    assert "USE erebus_database_dev;" not in _read("database/sql/advanced_deep_data_audit.sql")
    assert "USE erebus_database_dev;" not in _read("database/sql/advanced_vendor_parser_audit.sql")
    assert "USE erebus_database_dev;" not in _read("database/sql/advanced_vendor_column_profiling.sql")


def test_authority_sql_views_filter_inactive_family_and_alias_rows() -> None:
    authority_view_sql = _read("database/sql/view_android_sample_family_type_authority.sql")
    resolution_view_sql = _read("database/sql/label_authority_foundation.sql")
    deep_audit_sql = _read("database/sql/advanced_deep_data_audit.sql")

    assert "AND fam.is_active = 1" in authority_view_sql
    assert "AND alias.is_active = 1" in authority_view_sql
    assert "AND fam.is_active = 1" in resolution_view_sql
    assert "FROM v_android_sample_family_type_authority" in deep_audit_sql


def test_authority_foundation_adds_real_identity_keys() -> None:
    foundation_sql = _read("database/sql/label_authority_foundation.sql")

    assert "active_sample_id INT UNSIGNED AS" in foundation_sql
    assert "authority_content_sha1 CHAR(40) AS" in foundation_sql
    assert "UNIQUE KEY uq_malware_family_authority_active_sample (active_sample_id)" in foundation_sql
    assert "UNIQUE KEY uq_malware_family_authority_content (authority_content_sha1)" in foundation_sql
    assert "evidence_identity_sha1 CHAR(40) AS" in foundation_sql
    assert "UNIQUE KEY uq_mfle_identity (evidence_identity_sha1)" in foundation_sql


def test_authority_backfill_and_evidence_loaders_use_identity_based_dedup() -> None:
    backfill_sql = _read("database/sql/label_authority_backfill.sql")
    template_sql = _read("database/sql/label_authority_vendor_evidence_load_template.sql")
    evidence_backfill_sql = _read("database/sql/label_authority_vendor_evidence_backfill.sql")

    assert "tmp_malware_family_authority_seed" in backfill_sql
    assert "auth.authority_content_sha1 <> seed.authority_content_sha1" in backfill_sql
    assert "auth.authority_content_sha1 = seed.authority_content_sha1" in backfill_sql
    assert "e.evidence_identity_sha1 = SHA1(" in template_sql
    assert "e.evidence_identity_sha1 = SHA1(" in evidence_backfill_sql


def test_legacy_audit_sql_prefers_resolved_authority_surfaces() -> None:
    parser_sql = _read("database/sql/advanced_vendor_parser_audit.sql")
    profiling_sql = _read("database/sql/advanced_vendor_column_profiling.sql")
    deep_audit_sql = _read("database/sql/advanced_deep_data_audit.sql")

    assert "FROM v_android_sample_family_type_authority" in parser_sql
    assert "JOIN v_android_sample_family_type_authority a ON a.sample_id = v.sample_id" in profiling_sql
    assert "FROM v_android_sample_family_type_authority" in deep_audit_sql


def test_vendor_parser_audit_dedupes_long_vendor_unpivot_logic() -> None:
    parser_sql = _read("database/sql/advanced_vendor_parser_audit.sql")

    assert "CREATE TEMPORARY TABLE tmp_vendor_parser_audit_vendor_long AS" in parser_sql
    assert parser_sql.count("FROM virustotal_sample_vendor_engine_verdicts") < 20
    assert "DROP TEMPORARY TABLE IF EXISTS tmp_vendor_parser_audit_vendor_long;" in parser_sql
