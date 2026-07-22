"""Tests for run-scoped Permission Intel authority enrichment."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.reporting.permission_authority_enrichment import (
    apply_applite_dual_status_patch,
    build_enrichment_table,
    build_lane_transition_table,
    compose_permission_authority_enrichment,
    headline_lane_from_enrichment,
    parse_protection_level_string,
)
from obsidiandroid.reporting.permission_governance_lanes import (
    LANE_AOSP_DANGEROUS,
    LANE_AOSP_NORMAL,
    LANE_AOSP_SIGNATURE,
    LANE_AOSP_SIGNATURE_PRIVILEGED,
    LANE_UNKNOWN_UNRESOLVED,
)


def test_protection_level_parsing_variants() -> None:
    assert parse_protection_level_string("normal")["base_protection_level"] == "normal"
    assert parse_protection_level_string("dangerous|instant")["base_protection_level"] == "dangerous"
    assert "instant" in parse_protection_level_string("dangerous|instant")["protection_flags"]
    sig = parse_protection_level_string("signature")
    assert sig["base_protection_level"] == "signature"
    sp = parse_protection_level_string("signature|privileged|appop")
    assert sp["base_protection_level"] == "signature"
    assert "privileged" in sp["protection_flags"].split(",")
    assert "appop" in sp["protection_flags"].split(",")
    unk = parse_protection_level_string("internal|role")
    assert unk["base_protection_level"] == ""
    multi = parse_protection_level_string("signature|normal")
    assert multi["multi_base_conflict"] is True


def test_headline_lanes_from_enrichment() -> None:
    assert (
        headline_lane_from_enrichment(
            run_pi_bucket_source="AOSP",
            run_dangerous_bucket="unknown",
            match_status="exact_authority_match",
            base_protection_level="signature",
            protection_flags="privileged,appop",
            namespace_class="aosp",
        )
        == LANE_AOSP_SIGNATURE_PRIVILEGED
    )
    assert (
        headline_lane_from_enrichment(
            run_pi_bucket_source="AOSP",
            run_dangerous_bucket="unknown",
            match_status="exact_authority_match",
            base_protection_level="signature",
            protection_flags="",
            namespace_class="aosp",
        )
        == LANE_AOSP_SIGNATURE
    )
    assert (
        headline_lane_from_enrichment(
            run_pi_bucket_source="AOSP",
            run_dangerous_bucket="dangerous",
            match_status="exact_authority_match",
            base_protection_level="dangerous",
            protection_flags="instant",
            namespace_class="aosp",
        )
        == LANE_AOSP_DANGEROUS
    )
    assert (
        headline_lane_from_enrichment(
            run_pi_bucket_source="AOSP",
            run_dangerous_bucket="unknown",
            match_status="multiple_authority_conflict",
            base_protection_level="signature",
            protection_flags="",
            namespace_class="aosp",
        )
        == LANE_UNKNOWN_UNRESOLVED
    )


def test_one_row_per_token_alias_and_conflict(tmp_path: Path) -> None:
    audit = pd.DataFrame(
        [
            {
                "permission_string": "android.permission.SEND_SMS",
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "dangerous",
                "global_support": 10,
                "feature_column": "perm__send_sms",
                "retained_after_pruning": "yes",
            },
            {
                "permission_string": "android.permission.BIND_ACCESSIBILITY_SERVICE",
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "unknown",
                "global_support": 5,
                "feature_column": "perm__bind_a11y",
                "retained_after_pruning": "yes",
            },
            {
                "permission_string": "com.example.FOO",
                "pi_bucket_source": "APP_DEFINED",
                "dangerous_bucket": "app_defined",
                "global_support": 1,
                "feature_column": "perm__foo",
                "retained_after_pruning": "no",
            },
        ]
    )
    # Monkeypatch expected token count by building enrichment directly with small universe
    import obsidiandroid.reporting.permission_authority_enrichment as mod

    old = mod.EXPECTED_TOKEN_COUNT
    mod.EXPECTED_TOKEN_COUNT = 3
    try:
        pi = {
            "observed_at_utc": "2026-07-21T00:00:00+00:00",
            "alias_map": {"android.permission.send_sms": "android.permission.send_sms"},
            "fact_conflicts": set(),
            "facts": pd.DataFrame(
                [
                    {
                        "permission_string_norm": "android.permission.bind_accessibility_service",
                        "permission_string": "android.permission.BIND_ACCESSIBILITY_SERVICE",
                        "source_family_key": "aosp",
                        "authority_source_type": "android_public_docs",
                        "protection_level": "signature",
                        "visibility_class": "public_manifest",
                        "lifecycle_status": "current",
                        "authority_confidence": "high",
                        "is_current_best": 1,
                        "defining_package": "",
                        "updated_at_utc": "2026-01-01",
                        "authority_fact_id": 1,
                    }
                ]
            ),
            "aosp": pd.DataFrame(
                [
                    {
                        "constant_value_norm": "android.permission.send_sms",
                        "protection_level": "dangerous",
                        "lifecycle_status": "current",
                        "authority_source_type": "android_public_docs",
                        "source_family_key": "aosp",
                        "record_updated_at_utc": "2026-01-01",
                    }
                ]
            ),
            "oem": pd.DataFrame(),
            "unknown": pd.DataFrame(),
            "reviews": pd.DataFrame(),
        }
        enrichment = build_enrichment_table(audit, pi)
        assert len(enrichment) == 3
        assert set(enrichment.normalized_token) == {
            "android.permission.send_sms",
            "android.permission.bind_accessibility_service",
            "com.example.foo",
        }
        bind = enrichment[
            enrichment.normalized_token == "android.permission.bind_accessibility_service"
        ].iloc[0]
        assert bind.headline_lane == LANE_AOSP_SIGNATURE
        sms = enrichment[enrichment.normalized_token == "android.permission.send_sms"].iloc[0]
        assert sms.headline_lane == LANE_AOSP_DANGEROUS
        transitions = build_lane_transition_table(run_audit=audit, enrichment=enrichment)
        assert len(transitions) == 3
        moved = transitions[
            (transitions.old_lane == LANE_UNKNOWN_UNRESOLVED)
            & (transitions.enriched_lane == LANE_AOSP_SIGNATURE)
        ]
        assert len(moved) == 1
    finally:
        mod.EXPECTED_TOKEN_COUNT = old


def test_applite_dual_status() -> None:
    status = apply_applite_dual_status_patch()
    assert status["local_authority_status"] == "governed_curated"
    assert status["external_context_status"] == "sparse_or_thin"


def test_compose_enrichment_mocked_no_writes(tmp_path: Path) -> None:
    import obsidiandroid.reporting.permission_authority_enrichment as mod

    run_id = "20260721T231415Z__e0c43b"
    run = tmp_path / "run"
    diag = run / "diagnostics"
    tables = run / "bundles" / "permission_trends" / "tables"
    diag.mkdir(parents=True)
    tables.mkdir(parents=True)
    (run / ".COMPLETE").write_text("{}", encoding="utf-8")
    # Minimal audit with exactly 3 tokens; patch expected count
    audit = pd.DataFrame(
        [
            {
                "permission_string": "android.permission.INTERNET",
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "normal",
                "global_support": 100,
                "feature_column": "perm__internet",
                "retained_after_pruning": "yes",
                "feature_group": "network_c2",
                "max_family_support": 50,
                "max_type_support": 80,
                "pruned_as_leakage": "no",
            },
            {
                "permission_string": "android.permission.BIND_ACCESSIBILITY_SERVICE",
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "unknown",
                "global_support": 20,
                "feature_column": "perm__a11y",
                "retained_after_pruning": "yes",
                "feature_group": "ungrouped",
                "max_family_support": 10,
                "max_type_support": 15,
                "pruned_as_leakage": "no",
            },
            {
                "permission_string": "com.example.X",
                "pi_bucket_source": "APP_DEFINED",
                "dangerous_bucket": "app_defined",
                "global_support": 1,
                "feature_column": "perm__x",
                "retained_after_pruning": "no",
                "feature_group": "ungrouped",
                "max_family_support": 1,
                "max_type_support": 1,
                "pruned_as_leakage": "no",
            },
        ]
    )
    audit.to_csv(diag / "permission_feature_audit.csv", index=False)
    snap = pd.DataFrame(
        [
            {
                "sample_id": 1,
                "sha256": "a" * 64,
                "family_id": 1,
                "family_canonical": "ClayRat",
                "type_slug": "rat",
                "source_batch_label": "b",
                "effective_first_seen_year": 2025,
            }
        ]
    )
    snap.to_csv(diag / f"analysis_snapshot_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "profile_id": "android_malware_all_current",
                "sample_count": 9716,
                "samples_with_permission_rows": 9457,
            }
        ]
    ).to_csv(tables / f"permission_coverage_report_{run_id}.csv", index=False)
    # minimal trends to allow skip enriched compose
    (run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": "android_malware_all_current",
                "git_commit": "abc",
                "cohort_prepared_row_count": 9716,
                "dataset_hash": "d",
                "config_hash": "c",
                "analysis_snapshot": {"snapshot_sha256_hash": "s"},
            }
        ),
        encoding="utf-8",
    )
    old = mod.EXPECTED_TOKEN_COUNT
    # Also bypass verify prepared/bearing via monkeypatch verify? verify checks 9716/9457 from coverage - OK
    mod.EXPECTED_TOKEN_COUNT = 3
    try:
        pi = {
            "observed_at_utc": "2026-07-21T12:00:00+00:00",
            "alias_map": {},
            "fact_conflicts": set(),
            "facts": pd.DataFrame(
                [
                    {
                        "permission_string_norm": "android.permission.bind_accessibility_service",
                        "permission_string": "android.permission.BIND_ACCESSIBILITY_SERVICE",
                        "source_family_key": "aosp",
                        "authority_source_type": "android_public_docs",
                        "protection_level": "signature",
                        "visibility_class": "public",
                        "lifecycle_status": "current",
                        "authority_confidence": "high",
                        "is_current_best": 1,
                        "defining_package": "",
                        "updated_at_utc": "2026-01-01",
                        "authority_fact_id": 9,
                    }
                ]
            ),
            "aosp": pd.DataFrame(
                [
                    {
                        "constant_value_norm": "android.permission.internet",
                        "protection_level": "normal",
                        "lifecycle_status": "current",
                        "authority_source_type": "android_public_docs",
                        "source_family_key": "aosp",
                        "record_updated_at_utc": "2026-01-01",
                    }
                ]
            ),
            "oem": pd.DataFrame(),
            "unknown": pd.DataFrame(),
            "reviews": pd.DataFrame(),
        }
        out = compose_permission_authority_enrichment(
            run_root=run,
            run_id=run_id,
            output_dir=diag / "permission_authority_enrichment",
            repo_root=tmp_path,
            skip_enriched_compose=True,
            pi_bundle=pi,
        )
        assert out["boundaries"]["database_writes"] is False
        assert out["boundaries"]["artifact_only_reports_mutated"] is False
        assert out["summary"]["signature_tokens"] == 1
        enrich = pd.read_csv(diag / "permission_authority_enrichment" / "permission_authority_enrichment.csv")
        assert len(enrich) == 3
        # artifact-only dir must not be created by this skip path
        assert not (diag / "type_permission_protection").exists()
    finally:
        mod.EXPECTED_TOKEN_COUNT = old


def test_no_db_write_imports_in_enrichment_module() -> None:
    import obsidiandroid.reporting.permission_authority_enrichment as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "execute_core_query" not in src
    assert "INSERT INTO" not in src.upper()
    assert "DELETE FROM" not in src.upper()
    assert "CREATE TABLE" not in src.upper()
    assert "DROP TABLE" not in src.upper()
