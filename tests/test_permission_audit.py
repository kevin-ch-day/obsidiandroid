from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.research_validity import permission_audit as pa


def test_classify_perm_row_uses_live_app_defined_label() -> None:
    tier, src = pa._classify_perm_row("APP_DEFINED", "UNKNOWN")  # pylint: disable=protected-access
    assert tier == "app_defined"
    assert src == "APP_DEFINED"


def test_write_permission_intel_audit_artifacts_reports_coverage_and_unknowns(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_fetch_permission_rows(_sample_ids):
        return pd.DataFrame(
            {
                "sample_id": [1, 1, 2, 2],
                "permission_string": [
                    "android.permission.read_sms",
                    "com.anddoes.launcher.permission.update_count",
                    "android.permission.internet",
                    "android.permission.read_sms",
                ],
                "permission_source": ["AOSP", "UNKNOWN", "AOSP", "APP_DEFINED"],
                "protection_level": ["DANGEROUS", "UNKNOWN", "NORMAL", "UNKNOWN"],
            }
        )

    monkeypatch.setattr(pa, "_fetch_permission_rows", fake_fetch_permission_rows)

    def fake_execute_permission_query(query, fetch=False, as_dataframe=False, **_kwargs):
        assert fetch is True
        assert as_dataframe is True
        if "FROM permission_signal_catalog" in query:
            return pd.DataFrame(
                {
                    "signal_key": ["sms", "app_defined_scaffolding", "aosp_hidden_privileged"],
                    "display_name": ["SMS", "App-Defined Scaffolding", "AOSP Hidden / Privileged"],
                    "authority_lane": ["behavior_safe_capability", "app_scaffolding", "aosp_hidden_privileged"],
                    "default_malware_capability_posture": [
                        "candidate_behavior_area_only",
                        "exclude_from_malware_capability_claims",
                        "review_before_behavioral_claims",
                    ],
                    "include_in_model_features": [1, 1, 1],
                    "include_in_behavioral_claims": [1, 0, 0],
                    "mitre_candidate_only": [1, 1, 1],
                    "default_weight": [1.0, 0.5, 0.75],
                }
            )
        if "FROM permission_signal_mappings" in query:
            return pd.DataFrame(
                {
                    "signal_key": ["app_defined_scaffolding", "aosp_hidden_privileged"],
                    "perm_name": ["app_defined_dynamic_receiver_guard", "needs_source_validation"],
                    "namespace": ["remediation_lane", "remediation_lane"],
                    "mapping_basis": ["remediation_lane", "remediation_lane"],
                    "source_family_key": ["app_defined_dynamic_receiver_guard", "needs_source_validation"],
                    "include_in_model_features": [1, 0],
                    "include_in_behavioral_claims": [0, 0],
                    "candidate_behavior_area": ["app_scaffolding", "aosp_hidden_privileged_review"],
                    "mitre_candidate_tactic": [None, None],
                    "confidence": ["high", "medium"],
                }
            )
        if "vw_permission_unknown_unresolved_candidates" in query:
            return pd.DataFrame(
                {
                    "source_family_key": ["third_party_sdk_or_launcher", "app_defined_legacy_push_permission"],
                    "source_family_label": [
                        "Third-party SDK / launcher / badge ecosystem",
                        "Legacy app-defined push messaging permission",
                    ],
                    "review_lane": ["third_party_sdk", "source_validation_required"],
                    "token_count": [2, 3],
                    "total_seen": [1113, 13725],
                    "sample_count": [383, 503],
                    "package_count": [10, 12],
                }
            )
        if "vw_permission_aosp_metadata_completeness" in query:
            return pd.DataFrame(
                {
                    "metadata_completeness_class": ["sparse_shell", "partial_metadata_gap", "metadata_complete"],
                    "token_count": [263, 122, 254],
                    "missing_protection_level_count": [263, 12, 0],
                    "missing_description_count": [263, 40, 0],
                    "missing_added_in_api_level_count": [263, 70, 0],
                }
            )
        return pd.DataFrame(
            {
                "table_name": [
                    "permission_signal_catalog",
                    "permission_signal_mappings",
                    "android_permission_run_aosp_import",
                    "android_permission_triage_audit",
                ],
                "expected_role": [
                    "signal_catalog_seed",
                    "signal_mapping_seed",
                    "aosp_import_provenance",
                    "triage_operator_audit",
                ],
                "row_count": [0, 0, 0, 2],
            }
        )

    monkeypatch.setattr(pa.db_engine, "execute_permission_query", fake_execute_permission_query)

    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_canonical": ["Alpha", "Beta", "Gamma"],
            "type_slug": ["banker", "rat", "spyware"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name", "hash_like"],
            "source_batch_label": ["", "Zimperium IOC", ""],
        }
    )

    out = pa.write_permission_intel_audit_artifacts(
        diagnostics_dir=tmp_path,
        samples_df=samples_df,
    )

    assert len(out) == 10
    summary = pd.read_csv(tmp_path / "permission_intel_audit_summary.csv")
    metrics = dict(zip(summary["metric"], summary["value"]))
    assert int(metrics["cohort_samples"]) == 3
    assert int(metrics["samples_with_permission_intel"]) == 2
    assert int(metrics["samples_without_permission_intel"]) == 1
    assert int(metrics["unknown_permission_rows"]) == 1
    assert int(metrics["rows_source_app_defined"]) == 1

    missing_by_type = pd.read_csv(tmp_path / "permission_intel_missing_by_type.csv")
    assert missing_by_type.iloc[0]["type_slug"] == "spyware"
    assert int(missing_by_type.iloc[0]["sample_count"]) == 1

    unknown = pd.read_csv(tmp_path / "permission_intel_unknown_permissions.csv")
    assert "com.anddoes.launcher.permission.update_count" in unknown["permission_string"].tolist()

    remediation = pd.read_csv(tmp_path / "permission_intel_remediation_lanes.csv")
    lane = remediation.loc[remediation["source_family_key"] == "third_party_sdk_or_launcher"].iloc[0]
    assert lane["lane_class"] == "ecosystem_noise"
    assert lane["default_action"] == "classify_as_launcher_or_sdk_ecosystem"
    assert lane["include_in_model_features"] == "yes"
    assert lane["include_in_behavioral_claims"] == "no"

    lifecycle = pd.read_csv(tmp_path / "permission_intel_workflow_gaps.csv")
    assert int(lifecycle.loc[lifecycle["table_name"] == "permission_signal_catalog", "is_empty"].iloc[0]) == 1

    aosp = pd.read_csv(tmp_path / "permission_intel_aosp_metadata_debt.csv")
    assert "sparse_shell" in aosp["metadata_completeness_class"].tolist()

    signal_catalog = pd.read_csv(tmp_path / "permission_intel_signal_catalog_summary.csv")
    assert "sms" in signal_catalog["signal_key"].tolist()

    signal_review = pd.read_csv(tmp_path / "permission_intel_signal_mapping_review.csv")
    assert "needs_source_validation" in signal_review["perm_name"].tolist()

    report = (tmp_path / "permission_intel_audit_report.md").read_text(encoding="utf-8")
    assert "Coverage: 66.667%" in report
    assert "Behavior-claim-safe signals: sms" in report
    assert "Model-only / fingerprint signals:" in report
    assert "Mappings requiring review:" in report
    assert "Top UNKNOWN permission tokens:" in report
    assert "Concentrated remediation lanes:" in report
    assert "Workflow table gaps:" in report
