"""Synthetic tests for protection-stratified permission analysis."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.reporting.permission_governance_lanes import (
    CANONICAL_PROTECTION_LANES,
    classify_protection_lane,
    reconcile_lane_token_counts,
)
from obsidiandroid.reporting.type_permission_protection import (
    build_app_defined_permission_risk,
    build_dominant_family_lane_sensitivity,
    enrich_pairwise_protection,
    verify_completed_run,
    PAIRWISE_PROTECTION_EMPTY_COLUMNS,
)
from obsidiandroid.common.csv_io import optional_csv as _optional_csv
from obsidiandroid.common.csv_io import write_csv as _write_csv


def test_lane_token_reconciliation_covers_all_lanes() -> None:
    lanes = list(CANONICAL_PROTECTION_LANES) + list(CANONICAL_PROTECTION_LANES)
    recon = reconcile_lane_token_counts(lanes)
    assert recon["reconciles"] is True
    assert recon["total_tokens"] == len(lanes)


def test_sample_weighted_vs_family_balanced_leave_largest_by_lane() -> None:
    fam = pd.DataFrame(
        [
            {
                "family_canonical": "ClayRat",
                "type_slug": "rat",
                "family_support": 40,
                "permission": "android.permission.send_sms",
                "prevalence_pct": 95.0,
                "positive_count": 38,
            },
            {
                "family_canonical": "ClayRat",
                "type_slug": "rat",
                "family_support": 40,
                "permission": "android.permission.internet",
                "prevalence_pct": 100.0,
                "positive_count": 40,
            },
            {
                "family_canonical": "ArsinkRAT",
                "type_slug": "rat",
                "family_support": 30,
                "permission": "android.permission.send_sms",
                "prevalence_pct": 20.0,
                "positive_count": 6,
            },
            {
                "family_canonical": "ArsinkRAT",
                "type_slug": "rat",
                "family_support": 30,
                "permission": "android.permission.internet",
                "prevalence_pct": 100.0,
                "positive_count": 30,
            },
            {
                "family_canonical": "SpyNote",
                "type_slug": "rat",
                "family_support": 20,
                "permission": "android.permission.send_sms",
                "prevalence_pct": 15.0,
                "positive_count": 3,
            },
            {
                "family_canonical": "SpyNote",
                "type_slug": "rat",
                "family_support": 20,
                "permission": "android.permission.internet",
                "prevalence_pct": 100.0,
                "positive_count": 20,
            },
        ]
    )
    lookup = {
        "android.permission.send_sms": "aosp_dangerous",
        "android.permission.internet": "aosp_normal",
    }
    inv = pd.DataFrame(
        [
            {
                "type_slug": "rat",
                "sample_count": 90,
                "active_families": 3,
                "largest_family_canonical": "ClayRat",
            }
        ]
    )
    table = build_dominant_family_lane_sensitivity(
        fam_prev=fam,
        type_inventory=inv,
        role_annotations=pd.DataFrame(),
        pairwise=pd.DataFrame(),
        lane_lookup=lookup,
        focus_types=("rat",),
    )
    assert not table.empty
    assert set(table["headline_lane"]) <= {"aosp_dangerous", "aosp_normal"}
    dang = table[(table.headline_lane == "aosp_dangerous") & (table.scenario == "exclude_largest")]
    assert not dang.empty
    assert dang.iloc[0].excluded_families == "ClayRat"


def test_app_defined_identity_risk_and_pairwise_lanes() -> None:
    audit = pd.DataFrame(
        [
            {
                "permission_string": "com.example.FOO",
                "pi_bucket_source": "APP_DEFINED",
                "dangerous_bucket": "app_defined",
                "global_support": 1,
                "max_family_support": 1,
                "retained_after_pruning": "no",
                "feature_column": "perm__com_example_foo",
            },
            {
                "permission_string": "com.shared.BAR",
                "pi_bucket_source": "APP_DEFINED",
                "dangerous_bucket": "app_defined",
                "global_support": 50,
                "max_family_support": 10,
                "retained_after_pruning": "yes",
                "feature_column": "perm__com_shared_bar",
            },
        ]
    )
    fam = pd.DataFrame(
        [
            {
                "family_canonical": "OnlyFam",
                "type_slug": "banker",
                "family_support": 1,
                "permission": "com.example.foo",
                "prevalence_pct": 100.0,
                "positive_count": 1,
            },
            {
                "family_canonical": "A",
                "type_slug": "banker",
                "family_support": 20,
                "permission": "com.shared.bar",
                "prevalence_pct": 50.0,
                "positive_count": 10,
            },
            {
                "family_canonical": "B",
                "type_slug": "banker",
                "family_support": 20,
                "permission": "com.shared.bar",
                "prevalence_pct": 40.0,
                "positive_count": 8,
            },
            {
                "family_canonical": "C",
                "type_slug": "banker",
                "family_support": 10,
                "permission": "com.shared.bar",
                "prevalence_pct": 30.0,
                "positive_count": 3,
            },
        ]
    )
    lookup = {
        "com.example.foo": "app_defined",
        "com.shared.bar": "app_defined",
        "android.permission.internet": "aosp_normal",
        "android.permission.send_sms": "aosp_dangerous",
    }
    risk = build_app_defined_permission_risk(audit=audit, fam_prev=fam, lane_lookup=lookup)
    assert "identity_risk" in set(risk.reportability_status)
    pairwise = pd.DataFrame(
        [
            {
                "type_slug": "rat",
                "permission_a": "android.permission.internet",
                "permission_b": "android.permission.send_sms",
                "family_balanced_prevalence": 0.4,
                "family_balanced_prevalence_pct": 40.0,
                "largest_family_share_of_positives": 0.9,
                "reportability_status": "family_balanced_supported",
                "positive_sample_count": 100,
                "type_sample_count": 200,
            }
        ]
    )
    enriched = enrich_pairwise_protection(
        pairwise=pairwise, lane_lookup=lookup, fam_prev=fam
    )
    assert enriched.iloc[0].lane_pair_class == "cross_lane"
    assert enriched.iloc[0].reportability_status == "dominant_family_sensitive"
    assert classify_protection_lane(pi_bucket_source="OEM", dangerous_bucket="oem_vendor") == "oem_platform"
    assert classify_protection_lane(pi_bucket_source="GOOGLE", dangerous_bucket="google") == "google_platform"


def test_verify_completed_run_rejects_wrong_id(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / ".COMPLETE").write_text("{}", encoding="utf-8")
    (run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "wrong",
                "profile_id": "android_malware_all_current",
                "cohort_prepared_row_count": 9716,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="run identity mismatch"):
        verify_completed_run(run, expected_run_id="20260721T231415Z__e0c43b")


def test_optional_csv_treats_empty_files_as_empty_frame(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    header_only = tmp_path / "header.csv"
    _write_csv(header_only, pd.DataFrame(), empty_columns=PAIRWISE_PROTECTION_EMPTY_COLUMNS)

    assert _optional_csv(missing).empty
    assert _optional_csv(empty).empty
    loaded = _optional_csv(header_only)
    assert list(loaded.columns)[:3] == ["type_slug", "permission_a", "permission_b"]
    assert loaded.empty


def test_compose_does_not_import_database() -> None:
    import obsidiandroid.reporting.type_permission_protection as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "obsidiandroid.database" not in src
    assert "mysql" not in src.lower()
    assert "create_engine" not in src
