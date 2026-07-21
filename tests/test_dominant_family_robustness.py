"""Tests for dominant-family robustness audit."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.reporting.dominant_family_robustness import (
    build_banker_rat_dangerous_contrast,
    build_dominant_family_robustness_table,
    classify_robustness,
    compose_dominant_family_robustness_report,
)


def test_classify_robustness_classes() -> None:
    assert (
        classify_robustness(
            families_used_all=8,
            families_used_ex=7,
            family_balanced_all=50.0,
            family_balanced_ex=48.0,
            sample_weighted_all=60.0,
            sample_weighted_ex=55.0,
            dominant_share_of_positives=0.2,
        )
        == "robust_without_dominant"
    )
    assert (
        classify_robustness(
            families_used_all=8,
            families_used_ex=7,
            family_balanced_all=55.0,
            family_balanced_ex=8.0,
            sample_weighted_all=80.0,
            sample_weighted_ex=20.0,
            dominant_share_of_positives=0.5,
        )
        == "collapses_without_dominant"
    )
    assert (
        classify_robustness(
            families_used_all=8,
            families_used_ex=7,
            family_balanced_all=50.0,
            family_balanced_ex=25.0,
            sample_weighted_all=70.0,
            sample_weighted_ex=40.0,
            dominant_share_of_positives=0.4,
        )
        == "weakens_without_dominant"
    )
    assert (
        classify_robustness(
            families_used_all=5,
            families_used_ex=4,
            family_balanced_all=60.0,
            family_balanced_ex=5.0,
            sample_weighted_all=90.0,
            sample_weighted_ex=10.0,
            dominant_share_of_positives=0.85,
        )
        == "dominant_family_driven"
    )


def test_leave_dominant_family_metrics() -> None:
    inventory = pd.DataFrame(
        [
            {
                "type_slug": "rat",
                "largest_family_canonical": "ClayRat",
                "sample_count": 100,
                "active_families": 4,
                "largest_family_share": 0.5,
            },
            {
                "type_slug": "banker",
                "largest_family_canonical": "Godfather",
                "sample_count": 100,
                "active_families": 4,
                "largest_family_share": 0.3,
            },
        ]
    )
    fam = pd.DataFrame(
        [
            {
                "type_slug": "rat",
                "family_canonical": "ClayRat",
                "family_support": 50,
                "permission": "android.permission.read_call_log",
                "positive_count": 45,
                "prevalence_pct": 90.0,
            },
            {
                "type_slug": "rat",
                "family_canonical": "ArsinkRAT",
                "family_support": 30,
                "permission": "android.permission.read_call_log",
                "positive_count": 24,
                "prevalence_pct": 80.0,
            },
            {
                "type_slug": "rat",
                "family_canonical": "SpyNote",
                "family_support": 10,
                "permission": "android.permission.read_call_log",
                "positive_count": 5,
                "prevalence_pct": 50.0,
            },
            {
                "type_slug": "rat",
                "family_canonical": "OtherRAT",
                "family_support": 10,
                "permission": "android.permission.read_call_log",
                "positive_count": 0,
                "prevalence_pct": 0.0,
            },
            {
                "type_slug": "banker",
                "family_canonical": "Godfather",
                "family_support": 40,
                "permission": "android.permission.read_call_log",
                "positive_count": 4,
                "prevalence_pct": 10.0,
            },
            {
                "type_slug": "banker",
                "family_canonical": "B2",
                "family_support": 30,
                "permission": "android.permission.read_call_log",
                "positive_count": 3,
                "prevalence_pct": 10.0,
            },
            {
                "type_slug": "banker",
                "family_canonical": "B3",
                "family_support": 20,
                "permission": "android.permission.read_call_log",
                "positive_count": 2,
                "prevalence_pct": 10.0,
            },
            {
                "type_slug": "banker",
                "family_canonical": "B4",
                "family_support": 10,
                "permission": "android.permission.read_call_log",
                "positive_count": 1,
                "prevalence_pct": 10.0,
            },
        ]
    )
    lane_lookup = {"android.permission.read_call_log": "aosp_dangerous"}
    out = build_dominant_family_robustness_table(fam, inventory, lane_lookup, min_family_support=3)
    rat = out[(out.type_slug == "rat")].iloc[0]
    assert rat.dominant_family_canonical == "ClayRat"
    assert float(rat.family_balanced_prevalence_pct) == 55.0  # (90+80+50+0)/4
    assert float(rat.family_balanced_ex_dominant_pct) == (80 + 50 + 0) / 3
    contrast = build_banker_rat_dangerous_contrast(out)
    assert "permission" in contrast.columns
    assert len(contrast) == 1


def test_compose_robustness_fixture(tmp_path: Path) -> None:
    run_id = "rob_fix"
    run_root = tmp_path / "run"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    type_dir = run_root / "diagnostics" / "type_permission_pattern_report"
    diag = run_root / "diagnostics"
    tables.mkdir(parents=True)
    type_dir.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(json.dumps({"run_status": "complete"}), encoding="utf-8")

    pd.DataFrame(
        [
            {
                "type_slug": "rat",
                "sample_count": 100,
                "active_families": 4,
                "largest_family_canonical": "ClayRat",
                "largest_family_share": 0.5,
                "suppression_or_inclusion_reason": "included_in_main_comparison",
            },
            {
                "type_slug": "banker",
                "sample_count": 100,
                "active_families": 4,
                "largest_family_canonical": "Godfather",
                "largest_family_share": 0.3,
                "suppression_or_inclusion_reason": "included_in_main_comparison",
            },
        ]
    ).to_csv(type_dir / f"type_inventory_{run_id}.csv", index=False)

    rows = []
    for type_slug, dominant, other in [
        ("rat", "ClayRat", ["A", "B", "C"]),
        ("banker", "Godfather", ["X", "Y", "Z"]),
    ]:
        rows.append(
            {
                "type_slug": type_slug,
                "family_canonical": dominant,
                "family_support": 40,
                "permission": "android.permission.read_sms",
                "positive_count": 36,
                "prevalence_pct": 90.0,
            }
        )
        for fam in other:
            rows.append(
                {
                    "type_slug": type_slug,
                    "family_canonical": fam,
                    "family_support": 20,
                    "permission": "android.permission.read_sms",
                    "positive_count": 10,
                    "prevalence_pct": 50.0,
                }
            )
    pd.DataFrame(rows).to_csv(tables / f"permission_prevalence_by_family_{run_id}.csv", index=False)
    pd.DataFrame([{"type_slug": "rat", "sample_count": 100}]).to_csv(
        tables / f"family_support_distribution_{run_id}.csv", index=False
    )
    pd.DataFrame(
        [{"type_slug": "rat", "permission": "android.permission.read_sms", "n_samples": 100, "permission_positive_count": 50, "prevalence_pct": 50.0}]
    ).to_csv(tables / f"permission_prevalence_by_type_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {
                "permission_string": "android.permission.read_sms",
                "pi_bucket_source": "AOSP",
                "dangerous_bucket": "dangerous",
                "feature_column": "perm__android_permission_read_sms",
            }
        ]
    ).to_csv(diag / "permission_feature_audit.csv", index=False)

    manifest = compose_dominant_family_robustness_report(run_root=run_root, run_id=run_id)
    assert manifest["report_status"] == "FINAL_FROM_COMPLETED_RUN"
    assert manifest["controls"]["no_database_access"] is True
    assert manifest["controls"]["leave_dominant_family_only"] is True
    out = Path(manifest["output_dir"])
    assert (out / f"banker_rat_dangerous_contrast_{run_id}.csv").is_file()
    text = (out / f"dominant_family_robustness_report_{run_id}.md").read_text(encoding="utf-8")
    assert "Banker vs RAT" in text
