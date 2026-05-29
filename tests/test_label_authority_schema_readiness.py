from __future__ import annotations

import pandas as pd

import scripts.diagnostics.label_authority_schema_readiness as readiness


def test_main_reports_live_authority_view_when_found(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        readiness,
        "_fetch_columns",
        lambda: pd.DataFrame(
            [
                {"table_name": "malware_sample_catalog", "column_name": "sample_id"},
                {"table_name": "malware_sample_catalog", "column_name": "sha256"},
                {"table_name": "malware_sample_catalog", "column_name": "sample_label"},
                {"table_name": "malware_sample_catalog", "column_name": "family_label"},
                {"table_name": "malware_sample_catalog", "column_name": "classification_primary"},
                {"table_name": "malware_sample_catalog", "column_name": "classification_subtype"},
                {"table_name": "malware_sample_catalog", "column_name": "vt_first_seen_itw_date"},
                {"table_name": "malware_sample_catalog", "column_name": "vt_first_submission_at_utc"},
                {"table_name": "android_malware_family", "column_name": "family_id"},
                {"table_name": "android_malware_family", "column_name": "family_slug"},
                {"table_name": "android_malware_family", "column_name": "family_name"},
                {"table_name": "android_malware_family", "column_name": "primary_type_id"},
                {"table_name": "android_malware_family", "column_name": "is_active"},
                {"table_name": "android_malware_type", "column_name": "type_id"},
                {"table_name": "android_malware_type", "column_name": "type_slug"},
                {"table_name": "v_android_apk_family_resolved", "column_name": "sample_id"},
                {"table_name": "v_android_apk_family_resolved", "column_name": "resolved_family_lc"},
                {
                    "table_name": "virustotal_sample_vendor_engine_verdicts",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "virustotal_sample_vendor_engine_verdicts",
                    "column_name": "updated_at",
                },
                *[
                    {
                        "table_name": "virustotal_sample_vendor_engine_verdicts",
                        "column_name": column_name,
                    }
                    for column_name in readiness.CORE_VENDOR_COLUMNS
                ],
                {"table_name": "virustotal_vendor_engines", "column_name": "vendor_key"},
                {"table_name": "virustotal_vendor_engines", "column_name": "is_engine_active"},
                {"table_name": "virustotal_vendor_engines", "column_name": "is_trusted_vendor"},
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "resolved_family_lc",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "family_slug",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "type_slug",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "authority_bucket",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "authority_gap_reason",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "raw_vs_authority_status",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "authority_bucket",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "package_cluster_key",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "package_cluster_size",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "review_lane",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "recommended_action",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_effective",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_effective",
                    "column_name": "sample_label",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "sample_label",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "global_policy_bucket",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "review_lane",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "recommended_triage_action",
                },
                {
                    "table_name": "vendor_label_generic_token_fact",
                    "column_name": "normalized_token",
                },
                {
                    "table_name": "vendor_label_generic_token_fact",
                    "column_name": "token_kind",
                },
                {
                    "table_name": "vendor_label_generic_token_fact",
                    "column_name": "is_active",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        readiness,
        "_fetch_objects",
        lambda: pd.DataFrame(
            [
                {"table_name": "malware_sample_catalog", "table_type": "BASE TABLE"},
                {"table_name": "android_malware_family", "table_type": "BASE TABLE"},
                {"table_name": "android_malware_type", "table_type": "BASE TABLE"},
                {"table_name": "v_android_apk_family_resolved", "table_type": "VIEW"},
                {"table_name": "virustotal_sample_vendor_engine_verdicts", "table_type": "BASE TABLE"},
                {"table_name": "virustotal_vendor_engines", "table_type": "BASE TABLE"},
                {"table_name": "v_android_sample_family_type_authority", "table_type": "VIEW"},
                {"table_name": "v_android_missing_resolution_triage", "table_type": "VIEW"},
                {
                    "table_name": "v_vt_false_positive_review_candidates_effective",
                    "table_type": "VIEW",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "table_type": "VIEW",
                },
                {"table_name": "vendor_label_generic_token_fact", "table_type": "BASE TABLE"},
            ]
        ),
    )
    monkeypatch.setattr(
        readiness,
        "_estimate_seedable_vendor_rows",
        lambda: pd.DataFrame([{"vendor_key": "kaspersky", "nonempty_rows": 10}]),
    )

    rc = readiness.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "Current live authority objects" in out
    assert "v_android_sample_family_type_authority: view" in out
    assert "current live authority coverage view is already present" in out
    assert "Current policy tables" in out
    assert "vendor_label_generic_token_fact: table" in out
    assert "active-column contract: canonical:is_active" in out
    assert "current generic-token policy table satisfies the expected live contract" in out
