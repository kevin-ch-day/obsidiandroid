"""Synthetic tests for permission capability-category contract and reports."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.reporting.permission_capability_categories import (
    CANONICAL_CAPABILITY_CATEGORIES,
    EXPLICIT_PERMISSION_CAPABILITY_MAP,
    build_permission_capability_inventory,
    build_sample_category_matrix,
    classify_capability_categories,
    compose_permission_capability_category_report,
    normalize_permission_token,
)
from obsidiandroid.reporting.permission_governance_lanes import classify_protection_lane


def test_normalize_and_unknown_mapping() -> None:
    assert normalize_permission_token("  Android.Permission.READ_SMS ") == "android.permission.read_sms"
    assert classify_capability_categories("") == ("app_defined_unknown",)
    assert classify_capability_categories("com.example.app.permission.custom_token") == ("app_defined_unknown",)


def test_explicit_and_multi_category_mapping() -> None:
    assert classify_capability_categories("android.permission.read_sms") == ("sms_mms",)
    multi = classify_capability_categories("android.permission.disable_keyguard")
    assert multi == ("overlay_screen", "device_admin_security")
    assert all(c in CANONICAL_CAPABILITY_CATEGORIES for c in multi)
    assert "android.permission.disable_keyguard" in EXPLICIT_PERMISSION_CAPABILITY_MAP


def test_capability_separated_from_protection_lane() -> None:
    token = "android.permission.read_sms"
    cats = classify_capability_categories(token)
    lane = classify_protection_lane(
        pi_bucket_source="AOSP",
        dangerous_bucket="dangerous",
        permission_string=token,
        base_protection_level="dangerous",
    )
    assert cats == ("sms_mms",)
    assert lane == "aosp_dangerous"
    inv = build_permission_capability_inventory(
        [token],
        pi_bucket_source={token: "AOSP"},
        dangerous_bucket={token: "dangerous"},
    )
    assert list(inv["capability_category"]) == ["sms_mms"]
    assert "protection_lane" in inv.columns
    assert inv.iloc[0]["protection_lane"] == "aosp_dangerous"


def test_sample_category_prevalence_family_and_package_balance() -> None:
    labels = pd.DataFrame(
        [
            {"sample_id": 1, "family_canonical": "A", "type_slug": "rat", "package_name": "com.a"},
            {"sample_id": 2, "family_canonical": "A", "type_slug": "rat", "package_name": "com.a"},
            {"sample_id": 3, "family_canonical": "B", "type_slug": "rat", "package_name": "com.b"},
            {"sample_id": 4, "family_canonical": "B", "type_slug": "rat", "package_name": "com.c"},
        ]
    )
    perms = pd.DataFrame(
        [
            {"sample_id": 1, "permission_name": "android.permission.send_sms", "permission_present": 1},
            {"sample_id": 2, "permission_name": "android.permission.send_sms", "permission_present": 1},
            {"sample_id": 3, "permission_name": "android.permission.camera", "permission_present": 1},
        ]
    )
    matrix = build_sample_category_matrix(labels, perms)
    assert matrix.loc[matrix.sample_id == 1, "sms_mms"].iloc[0] == 1
    assert matrix.loc[matrix.sample_id == 3, "camera"].iloc[0] == 1
    assert matrix.loc[matrix.sample_id == 4, "sms_mms"].iloc[0] == 0
    # sample-weighted sms = 2/4; package-balanced uses known packages a,b,c means 1,0,0 → 1/3
    from obsidiandroid.reporting.package_balanced_permission_analysis import (
        family_balanced_prevalence,
        package_balanced_prevalence,
        sample_weighted_prevalence,
    )

    sw = sample_weighted_prevalence(matrix, "sms_mms")
    pb = package_balanced_prevalence(matrix, "sms_mms")
    fb = family_balanced_prevalence(matrix, "sms_mms")
    assert abs(sw - 0.5) < 1e-9
    assert abs(pb - (1 / 3)) < 1e-9
    assert pd.notna(fb)
    assert sw != pb


def test_composer_deterministic_no_db(tmp_path: Path, monkeypatch) -> None:
    """Composer must be offline, deterministic, and must not mutate archive inputs."""
    run_id = "20260721T231415Z__e0c43b"
    run_root = tmp_path / "run"
    diag = run_root / "diagnostics"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    diag.mkdir(parents=True)
    tables.mkdir(parents=True)
    (run_root / ".COMPLETE").write_text("ok\n", encoding="utf-8")
    labels = pd.DataFrame(
        [
            {
                "sample_id": i,
                "family_canonical": f"F{i % 3}",
                "type_slug": "rat" if i < 20 else "banker",
                "package_name": f"com.p{i % 5}",
                "family_id": i % 3,
                "sha256": f"h{i}",
            }
            for i in range(40)
        ]
    )
    # Minimal snapshot for verify_completed_run cohort counts
    snap = labels.copy()
    snap["type_slug"] = snap["type_slug"]
    labels.to_csv(diag / f"aligned_labels_{run_id}.csv", index=False)
    snap.to_csv(diag / f"analysis_snapshot_{run_id}.csv", index=False)
    perms = []
    for i in range(40):
        perms.append({"sample_id": i, "permission_name": "android.permission.internet", "permission_present": 1})
        if i % 2 == 0:
            perms.append({"sample_id": i, "permission_name": "android.permission.send_sms", "permission_present": 1})
    pd.DataFrame(perms).to_csv(diag / f"ml_sample_permission_feature_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {
                "permission_string": "android.permission.send_sms",
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "dangerous",
                "feature_column": "x",
                "feature_group": "g",
                "global_support": 10,
                "max_family_support": 2,
                "max_type_support": 2,
                "pruned_as_leakage": False,
                "retained_after_pruning": True,
            }
        ]
    ).to_csv(diag / "permission_feature_audit.csv", index=False)
    pd.DataFrame([{"samples_with_permission_rows": 9457}]).to_csv(
        tables / f"permission_coverage_report_{run_id}.csv", index=False
    )
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": "android_malware_all_current",
                "git_commit": "deadbeef",
                "dataset_hash": "abc",
                "cohort_prepared_row_count": 9716,
                "run_status": "complete",
            }
        ),
        encoding="utf-8",
    )

    # Block accidental DB imports/use
    import obsidiandroid.reporting.permission_capability_categories as mod

    def _boom(*_a, **_k):
        raise AssertionError("database access is forbidden")

    monkeypatch.setattr(mod, "compose_permission_capability_category_report", mod.compose_permission_capability_category_report)

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    m1 = compose_permission_capability_category_report(run_root=run_root, run_id=run_id, output_dir=out1, min_samples=5)
    m2 = compose_permission_capability_category_report(run_root=run_root, run_id=run_id, output_dir=out2, min_samples=5)
    assert m1["sample_count"] == 40
    # Deterministic CSVs (ignore manifest timestamps/checksums)
    for name in (
        "permission_capability_inventory.csv",
        "category_prevalence_by_type.csv",
        "sample_capability_matrix.csv",
    ):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes()
    # Archive/input unchanged
    assert (run_root / ".COMPLETE").read_text(encoding="utf-8") == "ok\n"
    assert "android.permission.send_sms" in (diag / f"ml_sample_permission_feature_{run_id}.csv").read_text()
