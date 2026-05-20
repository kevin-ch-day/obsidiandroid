"""Tests for split-catalog cohort readiness diagnostics."""

from __future__ import annotations

import obsidiandroid.database.db_cohort_readiness as db_cohort_readiness


def test_cohort_readiness_snapshot_separates_primary_and_permission_routing(monkeypatch) -> None:
    primary_queries: list[str] = []
    permission_queries: list[str] = []

    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        primary_queries.append(query)
        if "information_schema.tables" in query:
            table_name = params[1]
            if table_name in {
                "malware_sample_catalog",
                "vt_sample_verdict_confidence_current",
                "v_android_apk_family_resolved",
                "android_malware_family",
                "android_malware_type",
            }:
                return [(1,)]
            return []
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
        if "information_schema.tables" in query:
            assert params[1] == "android_permission_obs_sample"
            return [(1,)]
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
    assert any("Primary labels are missing for 2" in warning for warning in snapshot["warnings"])
    assert any("unmapped family slug" in warning for warning in snapshot["warnings"])
    assert any("recognized by the local canonical taxonomy" in warning for warning in snapshot["warnings"])
    assert any("Family/type backlog contains 2 family-level conflict candidate(s)" in warning for warning in snapshot["warnings"])
    assert any("Authority view unavailable, falling back to legacy family/type joins" in warning for warning in snapshot["warnings"])
    assert any("malware_sample_catalog" in q or "vt_sample_verdict_confidence_current" in q for q in primary_queries)
    assert any("android_permission_obs_sample" in q for q in permission_queries)


def test_cohort_readiness_snapshot_degrades_when_permission_intel_missing(monkeypatch) -> None:
    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "information_schema.tables" in query:
            return [(1,)]
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


def test_cohort_readiness_snapshot_degrades_when_vt_confidence_missing(monkeypatch) -> None:
    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "information_schema.tables" in query:
            table_name = params[1]
            return [(1,)] if table_name == "malware_sample_catalog" else []
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
        if "information_schema.tables" in query:
            return [(1,)]
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
    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "information_schema.tables" in query:
            table_name = params[1]
            if table_name in {"malware_sample_catalog", "vt_sample_verdict_confidence_current"}:
                return [(1,)]
            return []
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
        if "information_schema.tables" in query:
            return [(1,)]
        return [(1,), (2,)]

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_permission_query", fake_permission)

    snapshot = db_cohort_readiness.get_cohort_readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["authority_source_mode"] == "unavailable"
    assert any("Primary labels are missing for 1" in warning for warning in snapshot["warnings"])
    assert not any("Banker type-slug coverage exceeds" in warning for warning in snapshot["warnings"])


def test_cohort_readiness_snapshot_prefers_authority_view_when_available(monkeypatch) -> None:
    def fake_primary(query, params=None, fetch=False, return_columns=False, **_kwargs):
        if "information_schema.tables" in query:
            table_name = params[1]
            if table_name in {
                "malware_sample_catalog",
                "vt_sample_verdict_confidence_current",
                "v_android_apk_family_resolved",
                "android_malware_family",
                "android_malware_type",
            }:
                return [(1,)]
            return []
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
        if "information_schema.tables" in query:
            assert params[1] == "android_permission_obs_sample"
            return [(1,)]
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
