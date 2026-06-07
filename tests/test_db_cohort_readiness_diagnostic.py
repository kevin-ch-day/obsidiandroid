"""Tests for split-catalog cohort readiness diagnostics."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

import obsidiandroid.database.db_cohort_readiness as db_cohort_readiness


def test_cohort_readiness_snapshot_separates_primary_and_permission_routing(monkeypatch) -> None:
    primary_queries: list[str] = []
    permission_queries: list[str] = []

    def fake_get_table_columns(table_name: str) -> list[str]:
        columns = {
            "malware_sample_catalog": ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"],
            "vt_sample_verdict_confidence_current": ["sample_id", "confidence_bucket"],
            "v_android_apk_family_resolved": ["sample_id", "resolved_family_lc"],
            "android_malware_family": ["family_id", "family_slug", "primary_type_id"],
            "android_malware_type": ["type_id", "type_slug"],
            "android_permission_obs_sample": ["sample_id", "permission_string_norm"],
        }
        return columns.get(table_name, [])

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        primary_queries.append(query)
        if "LEFT JOIN `erebus_threat_intel_prod`.`android_malware_family`" in query:
            columns = ["sample_id", "resolved_family_lc", "type_slug"]
            rows = [
                (1, "anubis", "banker"),
                (2, "anubis", "banker"),
                (3, "anubis", "banker"),
                (4, "flubot", "dropper"),
                (6, "blankbot", None),
                (7, "devixor", "dropper"),
                (8, "devixor", "dropper"),
                (9, "devixor", "dropper"),
                (10, "devixor", "dropper"),
                (11, "devixor", "dropper"),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`malware_sample_catalog` AS msc" in query:
            columns = ["sample_id", "resolved_family_lc", "type_slug"]
            rows = [
                (1, "anubis", "banker"),
                (2, "anubis", "banker"),
                (3, "anubis", "banker"),
                (4, "flubot", "dropper"),
                (7, "devixor", "dropper"),
                (8, "devixor", "dropper"),
                (9, "devixor", "dropper"),
                (10, "devixor", "dropper"),
                (11, "devixor", "dropper"),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`malware_sample_catalog`" in query:
            columns = [
                "sample_id",
                "platform",
                "family_label",
                "classification_primary",
                "classification_subtype",
            ]
            rows = [
                (1, "android", "Anubis", "Trojan", "Banker"),
                (2, "android", "Anubis", "Trojan", "Banker"),
                (3, "android", "Anubis", "", ""),
                (4, "android", "FluBot", "Trojan", "Dropper"),
                (6, "android", "BlankBot", "", ""),
                (7, "android", "Devixor", "Trojan", "Banker"),
                (8, "android", "Devixor", "Trojan", "Banker"),
                (9, "android", "Devixor", "Trojan", "Banker"),
                (10, "android", "Devixor", "Trojan", "Banker"),
                (11, "android", "Devixor", "Trojan", "Banker"),
                (5, "windows", "AgentTesla", "Trojan", "Stealer"),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`vt_sample_verdict_confidence_current`" in query:
            return [(1,), (2,), (4,), (7,), (8,), (9,), (10,), (11,)]
        raise AssertionError(f"Unexpected primary query: {query}")

    def fake_permission(query, params=None, fetch=False, **_kwargs):
        permission_queries.append(query)
        if "GROUP BY r.resolved_family_lc, ops.permission_string_norm" in query:
            columns = ["family", "permission_string_norm", "sample_count"]
            rows = [
                ("anubis", "android.permission.read_sms", 2),
                ("anubis", "android.permission.read_phone_state", 2),
                ("blankbot", "android.permission.request_install_packages", 1),
                ("blankbot", "android.permission.query_all_packages", 1),
                ("devixor", "android.permission.read_sms", 5),
                ("devixor", "android.permission.read_phone_state", 5),
            ]
            return (columns, rows)
        if "FROM `android_permission_intel`.`android_permission_obs_sample`" in query:
            return [(1,), (2,), (3,), (4,), (6,), (7,), (8,), (9,), (10,), (11,), (99,)]
        raise AssertionError(f"Unexpected permission query: {query}")

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "get_table_columns", fake_get_table_columns)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["authority_source_mode"] == "legacy_resolution_fallback"
    assert snapshot["primary_available"] is True
    assert snapshot["permission_intel_available"] is True
    assert snapshot["permission_obs_available"] is True
    assert snapshot["vt_confidence_available"] is True
    assert snapshot["buckets"]["all_catalog"] == {"sample_count": 11, "family_count": 5}
    assert snapshot["buckets"]["android_platform"] == {"sample_count": 10, "family_count": 4}
    assert snapshot["buckets"]["android_with_permission_obs"] == {"sample_count": 10, "family_count": 4}
    assert snapshot["buckets"]["android_high_or_strong_vt_with_permission_obs"] == {"sample_count": 8, "family_count": 3}
    assert snapshot["buckets"]["android_labeled_primary_with_permission_obs"] == {"sample_count": 8, "family_count": 3}
    assert snapshot["buckets"]["android_banker_with_permission_obs"] == {"sample_count": 7, "family_count": 2}
    assert snapshot["buckets"]["android_family_ready_min3_permission_obs"] == {"sample_count": 8, "family_count": 2}
    assert snapshot["taxonomy_signals"]["banker_label_bucket_samples"] == 7
    assert snapshot["taxonomy_signals"]["banker_type_bucket_samples"] == 3
    assert snapshot["taxonomy_signals"]["banker_type_minus_label_samples"] == 0
    assert snapshot["taxonomy_signals"]["missing_primary_label_raw_samples"] == 2
    assert snapshot["taxonomy_signals"]["missing_primary_label_samples"] == 2
    assert snapshot["taxonomy_signals"]["unresolved_family_samples"] == 1
    assert snapshot["taxonomy_signals"]["unresolved_family_count"] == 1
    assert snapshot["taxonomy_signals"]["known_unresolved_family_samples"] == 1
    assert snapshot["taxonomy_signals"]["known_unresolved_family_count"] == 1
    assert snapshot["taxonomy_signals"]["family_type_conflict_count"] == 2
    assert snapshot["taxonomy_signals"]["family_type_conflict_issue_counts"] == {
        "type_mismatch": 1,
        "db_family_missing": 1,
    }
    assert snapshot["taxonomy_signals"]["family_type_conflict_priority_counts"] == {
        "medium": 2,
    }
    assert snapshot["taxonomy_signals"]["family_type_conflict_action_counts"] == {
        "review_db_type_mapping": 1,
        "review_unmapped_family": 1,
    }
    assert snapshot["taxonomy_signals"]["high_priority_conflict_count"] == 0
    assert snapshot["taxonomy_signals"]["repair_candidate_count"] == 2
    assert snapshot["taxonomy_signals"]["top_family_type_conflicts"] == [
        {
            "family": "devixor",
            "db_type_slug": "dropper",
            "issue": "type_mismatch",
            "sample_count": 5,
            "high_strong_sample_count": 5,
            "dominant_label_semantic": "banker",
            "dominant_label_samples": 5,
            "unlabeled_samples": 0,
            "known_locally": True,
            "operator_model_candidate": "banking_trojan",
            "fraud_posture_candidate": "banking_targeted",
            "permission_signal_summary": "sms+telephony",
            "priority": "medium",
            "suggested_action": "review_db_type_mapping",
        },
        {
            "family": "blankbot",
            "db_type_slug": "<unmapped>",
            "issue": "db_family_missing",
            "sample_count": 1,
            "high_strong_sample_count": 0,
            "dominant_label_semantic": "<unlabeled>",
            "dominant_label_samples": 1,
            "unlabeled_samples": 1,
            "known_locally": True,
            "operator_model_candidate": "unclear",
            "fraud_posture_candidate": "unclear",
            "permission_signal_summary": "overlay",
            "priority": "medium",
            "suggested_action": "review_unmapped_family",
        },
    ]
    assert snapshot["taxonomy_signals"]["top_repair_candidates"] == [
        {
            "family": "devixor",
            "db_type_slug": "dropper",
            "issue": "type_mismatch",
            "sample_count": 5,
            "high_strong_sample_count": 5,
            "dominant_label_semantic": "banker",
            "dominant_label_samples": 5,
            "unlabeled_samples": 0,
            "known_locally": True,
            "operator_model_candidate": "banking_trojan",
            "fraud_posture_candidate": "banking_targeted",
            "permission_signal_summary": "sms+telephony",
            "priority": "medium",
            "suggested_action": "review_db_type_mapping",
        },
        {
            "family": "blankbot",
            "db_type_slug": "<unmapped>",
            "issue": "db_family_missing",
            "sample_count": 1,
            "high_strong_sample_count": 0,
            "dominant_label_semantic": "<unlabeled>",
            "dominant_label_samples": 1,
            "unlabeled_samples": 1,
            "known_locally": True,
            "operator_model_candidate": "unclear",
            "fraud_posture_candidate": "unclear",
            "permission_signal_summary": "overlay",
            "priority": "medium",
            "suggested_action": "review_unmapped_family",
        },
    ]
    assert snapshot["taxonomy_signals"]["top_unresolved_families"] == [
        {
            "family": "blankbot",
            "sample_count": 1,
            "high_strong_sample_count": 0,
            "known_locally": True,
        }
    ]
    assert any("outside the current Android catalog cohort" in warning for warning in snapshot["warnings"])
    assert any("Primary labels are raw-missing for 2" in warning for warning in snapshot["warnings"])
    assert any("unmapped family slug" in warning for warning in snapshot["warnings"])
    assert any("recognized by the local canonical taxonomy" in warning for warning in snapshot["warnings"])
    assert any("Family/type backlog contains 2 family-level conflict candidate(s)" in warning for warning in snapshot["warnings"])
    assert any("Authority view unavailable, falling back to legacy family/type joins" in warning for warning in snapshot["warnings"])
    assert any("malware_sample_catalog" in q or "vt_sample_verdict_confidence_current" in q for q in primary_queries)
    assert any("android_permission_obs_sample" in q for q in permission_queries)


def test_cohort_readiness_snapshot_degrades_when_permission_intel_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        db_cohort_readiness.db_engine,
        "get_table_columns",
        lambda table_name: ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"]
        if table_name == "malware_sample_catalog"
        else [],
    )

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        columns = [
            "sample_id",
            "platform",
            "family_label",
            "classification_primary",
            "classification_subtype",
        ]
        rows = [(1, "android", "Anubis", "Trojan", "Banker")]
        return (columns, rows) if return_columns else rows

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(
        db_cohort_readiness.db_engine,
        "execute_permission_query",
        lambda *_args, **_kwargs: [],
    )

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["status"] == "degraded"
    assert snapshot["authority_source_mode"] == "unavailable"
    assert snapshot["buckets"]["all_catalog"] == {"sample_count": 1, "family_count": 1}
    assert snapshot["buckets"]["android_platform"] == {"sample_count": 1, "family_count": 1}
    assert snapshot["buckets"]["android_with_permission_obs"] == {"sample_count": None, "family_count": None}
    assert any("Permission Intel unavailable" in warning for warning in snapshot["warnings"])


def test_cohort_readiness_snapshot_splits_missing_primary_residual_lanes(monkeypatch) -> None:
    def fake_get_table_columns(table_name: str) -> list[str]:
        columns = {
            "malware_sample_catalog": ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"],
            "vt_sample_verdict_confidence_current": ["sample_id", "confidence_bucket", "vt_malicious_count"],
            "v_android_sample_family_type_authority": [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ],
            "v_android_apk_family_resolved": ["sample_id", "resolved_family_lc"],
            "android_malware_family": ["family_id", "family_slug", "primary_type_id"],
            "android_malware_type": ["type_id", "type_slug"],
            "android_permission_obs_sample": ["sample_id", "permission_string_norm"],
            "vt_false_positive_suppression_rule": ["scope_value", "suppression_weight", "active_flag", "scope_type"],
            "virustotal_sample_vendor_verdicts": ["sample_id", "verdict_category", "verdict_label"],
        }
        return columns.get(table_name, [])

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "lane_rows AS" in query:
            columns = [
                "residual_lane",
                "sample_count",
                "high_or_strong_sample_count",
                "zero_malicious_sample_count",
                "already_suppressed_sample_count",
            ]
            rows = [
                ("public_package_identity_provenance_review", 2, 0, 2, 0),
                ("already_sample_suppressed", 1, 0, 1, 1),
                ("high_strong_primary_backfill_review", 1, 1, 0, 0),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`v_android_sample_family_type_authority`" in query:
            columns = [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ]
            rows = [
                (1, "anubis", "anubis", "banker", "Trojan", "Banker", "authority_family_typed", "raw_subtype_matches_authority"),
                (2, "unknown", None, None, "", "", "resolved_unknown", "raw_missing"),
                (3, None, None, None, "", "", "missing_resolved_family", "raw_missing"),
                (4, None, None, None, "", "", "missing_resolved_family", "raw_missing"),
                (5, "cerberus", "cerberus", "banker", "", "", "authority_family_typed", "raw_missing"),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`malware_sample_catalog`" in query:
            columns = [
                "sample_id",
                "platform",
                "family_label",
                "classification_primary",
                "classification_subtype",
            ]
            rows = [
                (1, "android", "Anubis", "Trojan", "Banker"),
                (2, "android", "Unknown", "", ""),
                (3, "android", "", "", ""),
                (4, "android", "", "", ""),
                (5, "android", "Cerberus", "", ""),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`vt_sample_verdict_confidence_current`" in query:
            return [(1,), (5,)]
        raise AssertionError(f"Unexpected primary query: {query}")

    def fake_permission(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "GROUP BY r.resolved_family_lc, ops.permission_string_norm" in query:
            columns = ["family", "permission_string_norm", "sample_count"]
            return (columns, [])
        if "FROM `android_permission_intel`.`android_permission_obs_sample`" in query:
            return [(1,), (2,), (3,), (4,), (5,)]
        raise AssertionError(f"Unexpected permission query: {query}")

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "get_table_columns", fake_get_table_columns)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["taxonomy_signals"]["missing_primary_label_raw_samples"] == 4
    assert snapshot["taxonomy_signals"]["missing_primary_label_samples"] == 3
    assert snapshot["taxonomy_signals"]["missing_primary_label_actionable_samples"] == 1
    assert snapshot["taxonomy_signals"]["missing_primary_label_residual_samples"] == 3
    assert snapshot["taxonomy_signals"]["missing_primary_label_suppressed_samples"] == 1
    assert snapshot["taxonomy_signals"]["missing_primary_label_active_residual_samples"] == 2
    assert snapshot["taxonomy_signals"]["missing_primary_label_lane_counts"] == {
        "public_package_identity_provenance_review": 2,
        "already_sample_suppressed": 1,
        "high_strong_primary_backfill_review": 1,
    }
    assert snapshot["taxonomy_signals"]["top_missing_primary_label_lanes"][0] == {
        "lane": "public_package_identity_provenance_review",
        "sample_count": 2,
        "high_or_strong_sample_count": 0,
        "zero_malicious_sample_count": 2,
        "already_suppressed_sample_count": 0,
    }
    assert any(
        "active/actionable missing-primary debt=3" in warning
        and "Actionable high/strong label-review rows=1; residual/provenance rows=3" in warning
        for warning in snapshot["warnings"]
    )
    assert any(
        "Already-suppressed rows=1; active residual review rows=2" in warning
        for warning in snapshot["warnings"]
    )


def test_cohort_readiness_snapshot_excludes_policy_held_tokens_from_unresolved_backlog(monkeypatch) -> None:
    def fake_get_table_columns(table_name: str) -> list[str]:
        columns = {
            "malware_sample_catalog": ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"],
            "vt_sample_verdict_confidence_current": ["sample_id", "confidence_bucket"],
            "v_android_sample_family_type_authority": [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ],
            "v_android_apk_family_resolved": ["sample_id", "resolved_family_lc"],
            "android_malware_family": ["family_id", "family_slug", "primary_type_id"],
            "android_malware_type": ["type_id", "type_slug"],
            "vendor_label_generic_token_fact": ["normalized_token", "token_kind", "is_active"],
            "android_permission_obs_sample": ["sample_id", "permission_string_norm"],
        }
        return columns.get(table_name, [])

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "FROM `erebus_threat_intel_prod`.`vendor_label_generic_token_fact`" in query:
            columns = ["normalized_token", "token_kind"]
            rows = [("badpack", "packer_evasion_token")]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`v_android_sample_family_type_authority`" in query:
            columns = [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ]
            rows = [
                (1, "badpack", None, None, "Trojan", "Banker", "resolved_but_no_authority_family", "mismatch"),
                (2, "devixor", "devixor", "dropper", "Trojan", "Banker", "authority_family_typed", "mismatch"),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`malware_sample_catalog`" in query:
            columns = [
                "sample_id",
                "platform",
                "family_label",
                "classification_primary",
                "classification_subtype",
            ]
            rows = [
                (1, "android", "BadPack", "Trojan", "Banker"),
                (2, "android", "Devixor", "Trojan", "Banker"),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`vt_sample_verdict_confidence_current`" in query:
            return [(1,), (2,)]
        raise AssertionError(f"Unexpected primary query: {query}")

    def fake_permission(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "GROUP BY r.resolved_family_lc, ops.permission_string_norm" in query:
            columns = ["family", "permission_string_norm", "sample_count"]
            rows = [
                ("badpack", "android.permission.read_sms", 1),
                ("devixor", "android.permission.read_sms", 1),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `android_permission_intel`.`android_permission_obs_sample`" in query:
            return [(1,), (2,)]
        raise AssertionError(f"Unexpected permission query: {query}")

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "get_table_columns", fake_get_table_columns)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["authority_source_mode"] == "live_view"
    assert snapshot["taxonomy_signals"]["unresolved_family_samples"] == 0
    assert snapshot["taxonomy_signals"]["unresolved_family_count"] == 0
    assert snapshot["taxonomy_signals"]["policy_held_family_samples"] == 1
    assert snapshot["taxonomy_signals"]["policy_held_family_count"] == 1
    assert snapshot["taxonomy_signals"]["policy_held_family_token_kind_counts"] == {
        "packer_evasion_token": 1,
    }
    assert snapshot["taxonomy_signals"]["top_policy_held_families"] == [
        {
            "family": "badpack",
            "sample_count": 1,
            "token_kind": "packer_evasion_token",
            "high_strong_sample_count": 1,
        }
    ]
    assert snapshot["taxonomy_signals"]["top_unresolved_families"] == []
    assert snapshot["taxonomy_signals"]["family_type_conflict_count"] == 0
    assert snapshot["taxonomy_signals"]["family_type_conflict_priority_counts"] == {}
    assert snapshot["taxonomy_signals"]["family_type_conflict_action_counts"] == {}
    assert snapshot["taxonomy_signals"]["high_priority_conflict_count"] == 0
    assert snapshot["taxonomy_signals"]["top_family_type_conflicts"] == []
    assert any("policy-held generic/coarse token" in warning for warning in snapshot["warnings"])


def test_cohort_readiness_snapshot_suppresses_broad_spyware_vs_rat_conflict_when_permission_model_supports_rat(monkeypatch) -> None:
    def fake_get_table_columns(table_name: str) -> list[str]:
        columns = {
            "malware_sample_catalog": ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"],
            "vt_sample_verdict_confidence_current": ["sample_id", "confidence_bucket"],
            "v_android_sample_family_type_authority": [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ],
            "v_android_apk_family_resolved": ["sample_id", "resolved_family_lc"],
            "android_malware_family": ["family_id", "family_slug", "primary_type_id"],
            "android_malware_type": ["type_id", "type_slug"],
            "vendor_label_generic_token_fact": ["normalized_token", "token_kind", "is_active"],
            "android_permission_obs_sample": ["sample_id", "permission_string_norm"],
        }
        return columns.get(table_name, [])

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "FROM `erebus_threat_intel_prod`.`vendor_label_generic_token_fact`" in query:
            columns = ["normalized_token", "token_kind"]
            rows: list[tuple[str, str]] = []
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`v_android_sample_family_type_authority`" in query:
            columns = [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ]
            rows = [(1, "arsinkrat", "arsinkrat", "rat", "Trojan", "Spyware", "authority_family_typed", "mismatch")]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`malware_sample_catalog`" in query:
            columns = [
                "sample_id",
                "platform",
                "family_label",
                "classification_primary",
                "classification_subtype",
            ]
            rows = [(1, "android", "ArsinkRAT", "Trojan", "Spyware")]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`vt_sample_verdict_confidence_current`" in query:
            return [(1,)]
        raise AssertionError(f"Unexpected primary query: {query}")

    def fake_permission(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "GROUP BY r.resolved_family_lc, ops.permission_string_norm" in query:
            columns = ["family", "permission_string_norm", "sample_count"]
            rows = [
                ("arsinkrat", "android.permission.read_sms", 1),
                ("arsinkrat", "android.permission.read_call_log", 1),
                ("arsinkrat", "android.permission.record_audio", 1),
                ("arsinkrat", "android.permission.system_alert_window", 1),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `android_permission_intel`.`android_permission_obs_sample`" in query:
            return [(1,)]
        raise AssertionError(f"Unexpected permission query: {query}")

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "get_table_columns", fake_get_table_columns)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["taxonomy_signals"]["family_type_conflict_count"] == 0
    assert snapshot["taxonomy_signals"]["top_family_type_conflicts"] == []


def test_cohort_readiness_snapshot_reports_cross_family_alias_slug_overlap(monkeypatch) -> None:
    def fake_get_table_columns(table_name: str) -> list[str]:
        columns = {
            "malware_sample_catalog": ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"],
            "vt_sample_verdict_confidence_current": ["sample_id", "confidence_bucket"],
            "v_android_sample_family_type_authority": [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ],
            "v_android_apk_family_resolved": ["sample_id", "resolved_family_lc"],
            "android_malware_family": ["family_id", "family_slug", "primary_type_id", "is_active"],
            "android_malware_family_alias": ["alias_id", "alias_name", "family_id", "is_active", "review_status"],
            "android_malware_type": ["type_id", "type_slug"],
            "android_permission_obs_sample": ["sample_id", "permission_string_norm"],
        }
        return columns.get(table_name, [])

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "JOIN `erebus_threat_intel_prod`.`android_malware_family` AS alias_family" in query:
            columns = [
                "alias_name",
                "alias_family_id",
                "alias_family_slug",
                "slug_family_id",
                "family_slug",
                "family_name",
            ]
            rows = [("Wroba", 47, "roamingmantis", 129, "wroba", "Wroba")]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`v_android_sample_family_type_authority`" in query:
            columns = [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ]
            rows = [(1, "roamingmantis", "roamingmantis", "banker", "Trojan", "Banker", "authority_family_typed", "raw_subtype_matches_authority")]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`malware_sample_catalog`" in query:
            columns = [
                "sample_id",
                "platform",
                "family_label",
                "classification_primary",
                "classification_subtype",
            ]
            rows = [(1, "android", "RoamingMantis", "Trojan", "Banker")]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`vt_sample_verdict_confidence_current`" in query:
            return [(1,)]
        raise AssertionError(f"Unexpected primary query: {query}")

    def fake_permission(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "GROUP BY r.resolved_family_lc, ops.permission_string_norm" in query:
            columns = ["family", "permission_string_norm", "sample_count"]
            rows = [("roamingmantis", "android.permission.read_sms", 1)]
            return (columns, rows) if return_columns else rows
        if "FROM `android_permission_intel`.`android_permission_obs_sample`" in query:
            return [(1,)]
        raise AssertionError(f"Unexpected permission query: {query}")

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "get_table_columns", fake_get_table_columns)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["taxonomy_signals"]["alias_family_overlap_count"] == 1
    assert snapshot["taxonomy_signals"]["top_alias_family_overlaps"] == [
        {
            "alias_name": "Wroba",
            "alias_family_id": 47,
            "alias_family_slug": "roamingmantis",
            "slug_family_id": 129,
            "family_slug": "wroba",
            "family_name": "Wroba",
        }
    ]
    assert any("Alias/family authority overlap includes 1 accepted alias token(s)" in warning for warning in snapshot["warnings"])


def test_cohort_readiness_snapshot_degrades_when_vt_confidence_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        db_cohort_readiness.db_engine,
        "get_table_columns",
        lambda table_name: (
            ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"]
            if table_name == "malware_sample_catalog"
            else ["sample_id", "permission_string_norm"]
            if table_name == "android_permission_obs_sample"
            else []
        ),
    )

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        columns = [
            "sample_id",
            "platform",
            "family_label",
            "classification_primary",
            "classification_subtype",
        ]
        rows = [
            (1, "android", "Anubis", "Trojan", "Banker"),
            (2, "android", "Anubis", "", ""),
        ]
        return (columns, rows) if return_columns else rows

    def fake_permission(query, params=None, fetch=False, **_kwargs):
        return [(1,), (2,)]

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["status"] == "degraded"
    assert snapshot["authority_source_mode"] == "unavailable"
    assert snapshot["vt_confidence_available"] is False
    assert snapshot["buckets"]["android_with_permission_obs"] == {"sample_count": 2, "family_count": 1}
    assert snapshot["buckets"]["android_high_or_strong_vt_with_permission_obs"] == {"sample_count": None, "family_count": None}
    assert any("VT confidence surface unavailable" in warning for warning in snapshot["warnings"])


def test_cohort_readiness_snapshot_skips_banker_type_warning_when_type_tables_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        db_cohort_readiness.db_engine,
        "get_table_columns",
        lambda table_name: (
            ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"]
            if table_name == "malware_sample_catalog"
            else ["sample_id", "confidence_bucket"]
            if table_name == "vt_sample_verdict_confidence_current"
            else ["sample_id", "permission_string_norm"]
            if table_name == "android_permission_obs_sample"
            else []
        ),
    )

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "FROM `erebus_threat_intel_prod`.`malware_sample_catalog`" in query:
            columns = [
                "sample_id",
                "platform",
                "family_label",
                "classification_primary",
                "classification_subtype",
            ]
            rows = [
                (1, "android", "Anubis", "Trojan", "Banker"),
                (2, "android", "Anubis", "", ""),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`vt_sample_verdict_confidence_current`" in query:
            return [(1,), (2,)]
        raise AssertionError(f"Unexpected primary query: {query}")

    def fake_permission(query, params=None, fetch=False, **_kwargs):
        return [(1,), (2,)]

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["authority_source_mode"] == "unavailable"
    assert any("Primary labels are raw-missing for 1" in warning for warning in snapshot["warnings"])
    assert not any("Banker type-slug coverage exceeds" in warning for warning in snapshot["warnings"])


def test_cohort_readiness_snapshot_prefers_authority_view_when_available(monkeypatch) -> None:
    def fake_get_table_columns(table_name: str) -> list[str]:
        columns = {
            "malware_sample_catalog": ["sample_id", "platform", "family_label", "classification_primary", "classification_subtype"],
            "vt_sample_verdict_confidence_current": ["sample_id", "confidence_bucket"],
            "v_android_apk_family_resolved": ["sample_id", "resolved_family_lc"],
            "android_malware_family": ["family_id", "family_slug", "primary_type_id"],
            "android_malware_type": ["type_id", "type_slug"],
            "v_android_sample_family_type_authority": [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ],
            "android_permission_obs_sample": ["sample_id", "permission_string_norm"],
        }
        return columns.get(table_name, [])

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "FROM `erebus_threat_intel_prod`.`v_android_sample_family_type_authority`" in query:
            columns = [
                "sample_id",
                "resolved_family_lc",
                "family_slug",
                "type_slug",
                "raw_classification_primary",
                "raw_classification_subtype",
                "authority_bucket",
                "raw_vs_authority_status",
            ]
            rows = [
                (1, "anubis", "anubis", "banker", "Trojan", "Banker", "authority_family_typed", "raw_subtype_matches_authority"),
                (2, "anubis", "anubis", "banker", "Trojan", "Banker", "authority_family_typed", "raw_subtype_matches_authority"),
                (3, "anubis", "anubis", "banker", "", "", "authority_family_typed", "raw_missing"),
                (4, "flubot", "flubot", "dropper", "Trojan", "Dropper", "authority_family_typed", "raw_conflicts_with_authority"),
                (6, "blankbot", None, None, "", "", "resolved_but_no_authority_family", "authority_unknown"),
                (7, "devixor", "devixor", "dropper", "Trojan", "Banker", "authority_family_typed", "raw_conflicts_with_authority"),
                (8, "devixor", "devixor", "dropper", "Trojan", "Banker", "authority_family_typed", "raw_conflicts_with_authority"),
                (9, "devixor", "devixor", "dropper", "Trojan", "Banker", "authority_family_typed", "raw_conflicts_with_authority"),
                (10, "devixor", "devixor", "dropper", "Trojan", "Banker", "authority_family_typed", "raw_conflicts_with_authority"),
                (11, "devixor", "devixor", "dropper", "Trojan", "Banker", "authority_family_typed", "raw_conflicts_with_authority"),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`malware_sample_catalog`" in query:
            columns = [
                "sample_id",
                "platform",
                "family_label",
                "classification_primary",
                "classification_subtype",
            ]
            rows = [
                (1, "android", "Anubis", "Trojan", "Banker"),
                (2, "android", "Anubis", "Trojan", "Banker"),
                (3, "android", "Anubis", "", ""),
                (4, "android", "FluBot", "Trojan", "Dropper"),
                (6, "android", "BlankBot", "", ""),
                (7, "android", "Devixor", "Trojan", "Banker"),
                (8, "android", "Devixor", "Trojan", "Banker"),
                (9, "android", "Devixor", "Trojan", "Banker"),
                (10, "android", "Devixor", "Trojan", "Banker"),
                (11, "android", "Devixor", "Trojan", "Banker"),
                (5, "windows", "AgentTesla", "Trojan", "Stealer"),
            ]
            return (columns, rows) if return_columns else rows
        if "FROM `erebus_threat_intel_prod`.`vt_sample_verdict_confidence_current`" in query:
            return [(1,), (2,), (4,), (7,), (8,), (9,), (10,), (11,)]
        raise AssertionError(f"Unexpected primary query: {query}")

    def fake_permission(query, params=None, fetch=False, **_kwargs):
        if "GROUP BY r.resolved_family_lc, ops.permission_string_norm" in query:
            columns = ["family", "permission_string_norm", "sample_count"]
            rows = [
                ("anubis", "android.permission.read_sms", 2),
                ("anubis", "android.permission.read_phone_state", 2),
                ("blankbot", "android.permission.request_install_packages", 1),
                ("blankbot", "android.permission.query_all_packages", 1),
                ("devixor", "android.permission.read_sms", 5),
                ("devixor", "android.permission.read_phone_state", 5),
            ]
            return (columns, rows)
        if "FROM `android_permission_intel`.`android_permission_obs_sample`" in query:
            return [(1,), (2,), (3,), (4,), (6,), (7,), (8,), (9,), (10,), (11,)]
        raise AssertionError(f"Unexpected permission query: {query}")

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "get_table_columns", fake_get_table_columns)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["authority_source_mode"] == "live_view"
    assert snapshot["taxonomy_signals"]["banker_type_bucket_samples"] == 3
    assert snapshot["taxonomy_signals"]["unresolved_family_samples"] == 1
    assert snapshot["taxonomy_signals"]["top_unresolved_families"] == [
        {
            "family": "blankbot",
            "sample_count": 1,
            "high_strong_sample_count": 0,
            "known_locally": True,
        }
    ]
    assert not any("Authority view unavailable, falling back to legacy family/type joins" in warning for warning in snapshot["warnings"])
