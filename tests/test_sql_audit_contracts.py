from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    path = REPO_ROOT / relative_path
    return path.read_text(encoding="utf-8")


def test_read_only_audit_sql_does_not_hardcode_dev_schema() -> None:
    assert "USE erebus_database_dev;" not in _read("database/sql/advanced_deep_data_audit.sql")
    assert "USE erebus_database_dev;" not in _read("database/sql/advanced_vendor_parser_audit.sql")
    assert "USE erebus_database_dev;" not in _read("database/sql/advanced_vendor_column_profiling.sql")


def test_live_operator_sql_does_not_hardcode_prod_schema() -> None:
    active_paths = [
        "database/sql/create_android_missing_resolution_triage.sql",
        "database/sql/android_missing_resolution_worklist.sql",
        "database/sql/android_missing_primary_label_audit.sql",
        "database/sql/android_family_resolution_gap_regex_audit.sql",
        "database/sql/android_family_resolution_priority_regex_worklist.sql",
        "database/sql/android_missing_primary_label_remediation_priorities.sql",
        "database/sql/android_missing_primary_label_false_positive_provenance_queue.sql",
        "database/sql/android_missing_primary_label_likely_legit_package_identity_queue.sql",
        "database/sql/android_missing_primary_label_package_reuse_review_queue.sql",
        "database/sql/android_unknown_high_confidence_family_review_queue.sql",
        "database/sql/android_pattern_information_metrics.sql",
        "database/sql/android_pattern_advanced_metrics.sql",
        "database/sql/android_typed_without_pi_audit.sql",
        "database/sql/create_vt_false_positive_review_candidates_effective.sql",
        "database/sql/create_vt_false_positive_review_candidates_triage.sql",
        "database/sql/vt_false_positive_review_suppression_audit.sql",
        "database/sql/vt_false_positive_suppression_contract_gap_audit.sql",
        "database/sql/android_regex_advanced_audit.sql",
    ]
    for path in active_paths:
        assert "USE erebus_threat_intel_prod;" not in _read(path)


def test_android_missing_resolution_triage_view_excludes_suppressed_rows() -> None:
    sql = _read("database/sql/create_android_missing_resolution_triage.sql")

    assert "vt_false_positive_suppression_rule" in sql
    assert "s.scope_type = 'sample'" in sql
    assert "s.scope_type = 'package'" in sql
    assert "COALESCE(s.max_suppression_weight, 0) <= 0" in sql
    assert "'vt_tail_policy_hold_review'" in sql
    assert "'typed_malware_no_family_signal_review'" in sql
    assert "'low_signal_singleton_provenance_review'" in sql
    assert "com.app.pacotesinkinstall" in sql
    assert "internet_confirmed_malware_package_review" in sql
    assert "com.theporter.android.driverapp" in sql
    assert "likely_legit_package_identity_review" in sql


def test_authority_sql_views_filter_inactive_family_and_alias_rows() -> None:
    authority_view_sql = _read("database/sql/view_android_sample_family_type_authority.sql")
    resolution_view_sql = _read("database/sql/label_authority_foundation.sql")
    deep_audit_sql = _read("database/sql/advanced_deep_data_audit.sql")

    assert "AND fam.is_active = 1" in authority_view_sql
    assert "AND alias.is_active = 1" in authority_view_sql
    assert "LEFT JOIN vendor_label_generic_token_fact AS gt" in authority_view_sql
    assert "resolved_token_policy_held_not_family" in authority_view_sql
    assert "known_legit_package_identity_review" in authority_view_sql
    assert "known_legit_package_identity" in authority_view_sql
    assert "low_context_provenance_review" in authority_view_sql
    assert "low_context_blank_package_no_family_signal" in authority_view_sql
    assert "pua_or_provenance_review" in authority_view_sql
    assert "pua_without_family_signal" in authority_view_sql
    assert "vt_tail_policy_hold_review" in authority_view_sql
    assert "vt_tail_token_policy_held_not_family" in authority_view_sql
    assert "typed_malware_no_family_signal_review" in authority_view_sql
    assert "coarse_trojan_banker_without_family_signal" in authority_view_sql
    assert "low_signal_singleton_provenance_review" in authority_view_sql
    assert "blank_family_singleton_no_signal" in authority_view_sql
    assert "AND fam.is_active = 1" in resolution_view_sql
    assert "FROM v_android_sample_family_type_authority" in deep_audit_sql


def test_fakecop_campaign_attribution_is_not_an_alias() -> None:
    campaign_table_sql = _read(
        "database/sql/create_android_malware_family_campaign_relation.sql"
    )

    assert "android_malware_family_campaign_relation" in campaign_table_sql
    assert "campaign_actor_token" in campaign_table_sql
    assert "attributed_to_campaign" in campaign_table_sql
    assert "INSERT INTO android_malware_family_alias" not in campaign_table_sql
    assert "INSERT INTO malware_family_alias_fact" not in campaign_table_sql


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


def test_missing_primary_label_audit_uses_live_contract_surfaces() -> None:
    sql = _read("database/sql/android_missing_primary_label_audit.sql")

    assert "FROM malware_sample_catalog AS msc" in sql
    assert "android_permission_intel.android_permission_obs_sample" in sql
    assert "LEFT JOIN v_android_sample_family_type_authority AS a" in sql
    assert "vt_sample_verdict_confidence_current" in sql
    assert "classification_primary" in sql

    remediation_sql = _read("database/sql/android_missing_primary_label_remediation_priorities.sql")
    assert "android_permission_intel.android_permission_obs_sample" in remediation_sql
    assert "v_android_sample_family_type_authority" in remediation_sql
    assert "vt_sample_verdict_confidence_current" in remediation_sql
    assert "candidate_pua_manual_confirm" in remediation_sql

    provenance_sql = _read("database/sql/android_missing_primary_label_false_positive_provenance_queue.sql")
    assert "android_permission_intel.android_permission_obs_sample" in provenance_sql
    assert "missing_resolved_family" in provenance_sql
    assert "confidence_score" in provenance_sql

    legit_sql = _read("database/sql/android_missing_primary_label_likely_legit_package_identity_queue.sql")
    assert "android_permission_intel.android_permission_obs_sample" in legit_sql
    assert "missing_resolved_family" in legit_sql
    assert "known_legit_package_identity_review" in legit_sql
    assert "com.ubnt.easyunifi" in legit_sql
    assert "com.aptoide.android.aptoidegames" in legit_sql
    assert "fc.admin.fcexpressadmin" in legit_sql
    assert "com.frontrow.vlog" in legit_sql
    assert "com.theporter.android.driverapp" in legit_sql
    assert "likely_legit_package_identity_review" in legit_sql
    assert "catalog_rows_for_package" in legit_sql
    assert "distinct_catalog_labels_for_package" in legit_sql

    package_reuse_sql = _read("database/sql/android_missing_primary_label_package_reuse_review_queue.sql")
    assert "possible_false_positive_or_package_reuse" in package_reuse_sql
    assert "31128" in package_reuse_sql

    unknown_sql = _read("database/sql/android_unknown_high_confidence_family_review_queue.sql")
    assert "android_permission_intel.android_permission_obs_sample" in unknown_sql
    assert "resolved_unknown" in unknown_sql
    assert "candidate_same_package_label_review" in unknown_sql

    policy_held_report = _read("scripts/diagnostics/report_android_policy_held_token_risk.py")
    assert "android_policy_held_token_risk_latest.csv" in policy_held_report
    assert "vendor_label_generic_token_fact" in policy_held_report
    assert "android_permission_obs_sample" in policy_held_report
    assert "policy_hold_lane" in policy_held_report
    assert "generic_family_token_review" in policy_held_report
    assert "Keep out of family authority" in policy_held_report

    family_gap_sql = _read("database/sql/android_family_resolution_gap_regex_audit.sql")
    assert "vw_malware_sample_catalog_family_resolution_review" in family_gap_sql
    assert "accepted alias hit opportunities" in family_gap_sql.lower()
    assert "taxonomy-note contradiction scanner" in family_gap_sql.lower()

    family_priority_sql = _read("database/sql/android_family_resolution_priority_regex_worklist.sql")
    assert "priority worklist" in family_priority_sql.lower()
    assert "accepted_alias_mapping_gap" in family_priority_sql
    assert "alias_family_contradiction" in family_priority_sql
    assert "repeated unresolved family/vt-token pairs" in family_priority_sql.lower()

    missing_resolution_worklist_sql = _read("database/sql/android_missing_resolution_worklist.sql")
    assert "known_legit_package_identity_review" in missing_resolution_worklist_sql
    assert "low_context_provenance_review" in missing_resolution_worklist_sql
    assert "pua_or_provenance_review" in missing_resolution_worklist_sql
    assert "vt_tail_policy_hold_review" in missing_resolution_worklist_sql
    assert "typed_malware_no_family_signal_review" in missing_resolution_worklist_sql
    assert "low_signal_singleton_provenance_review" in missing_resolution_worklist_sql
    assert "com.app.pacotesinkinstall" in missing_resolution_worklist_sql
    assert "internet_confirmed_malware_package_review" in missing_resolution_worklist_sql
    assert "com.moonfair.wlkm" in missing_resolution_worklist_sql
    assert "cris.org.in.prs.ima" in missing_resolution_worklist_sql
    assert "com.aptoide.android.aptoidegames" in missing_resolution_worklist_sql
    assert "fc.admin.fcexpressadmin" in missing_resolution_worklist_sql
    assert "com.theporter.android.driverapp" in missing_resolution_worklist_sql
    assert "likely_legit_package_identity_review" in missing_resolution_worklist_sql

    remediation_priorities_sql = _read("database/sql/android_missing_primary_label_remediation_priorities.sql")
    assert "com.moonfair.wlkm" in remediation_priorities_sql
    assert "internet_confirmed_malware_package_review" in remediation_priorities_sql
    assert "com.example.kyc" in remediation_priorities_sql
    assert "cris.org.in.prs.ima" in remediation_priorities_sql
    assert "com.aptoide.android.aptoidegames" in remediation_priorities_sql
    assert "fc.admin.fcexpressadmin" in remediation_priorities_sql
    assert "com.frontrow.vlog" in remediation_priorities_sql
    assert "com.theporter.android.driverapp" in remediation_priorities_sql
