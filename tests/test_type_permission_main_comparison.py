"""Tests for main-type differential + headline strength tiers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.reporting.permission_governance_lanes import classify_headline_strength
from obsidiandroid.reporting.type_permission_main_comparison import (
    build_main_type_permission_diff,
    build_sw_fb_collapse_ledger,
    compose_main_type_permission_comparison,
)


def test_headline_strength_tiers() -> None:
    assert (
        classify_headline_strength(
            reportability_status="family_balanced_supported",
            family_balanced_prevalence=0.25,
        )
        == "strong"
    )
    assert (
        classify_headline_strength(
            reportability_status="family_balanced_supported",
            family_balanced_prevalence=0.12,
        )
        == "moderate"
    )
    assert (
        classify_headline_strength(
            reportability_status="family_balanced_supported",
            family_balanced_prevalence=0.07,
        )
        == "marginal"
    )
    assert (
        classify_headline_strength(
            reportability_status="single_family_dominated",
            family_balanced_prevalence=0.5,
        )
        == "not_headline"
    )


def test_collapse_ledger_and_diff() -> None:
    lane = pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "permission": "android.permission.read_sms",
                "protection_governance_lane": "aosp_dangerous",
                "prevalence_pct": 80.0,
                "family_balanced_prevalence_pct": 40.0,
                "odds_ratio": 3.0,
                "supporting_family_count": 10,
                "reportability_status": "descriptive_type_enriched",
                "largest_family_canonical": "Huge",
            },
            {
                "type_slug": "rat",
                "permission": "android.permission.read_sms",
                "protection_governance_lane": "aosp_dangerous",
                "prevalence_pct": 20.0,
                "family_balanced_prevalence_pct": 18.0,
                "odds_ratio": 0.5,
                "supporting_family_count": 8,
                "reportability_status": "descriptive_common",
                "largest_family_canonical": "R1",
            },
            {
                "type_slug": "spyware",
                "permission": "android.permission.read_sms",
                "protection_governance_lane": "aosp_dangerous",
                "prevalence_pct": 10.0,
                "family_balanced_prevalence_pct": 12.0,
                "odds_ratio": 0.4,
                "supporting_family_count": 5,
                "reportability_status": "descriptive_common",
                "largest_family_canonical": "S1",
            },
            {
                "type_slug": "adware",
                "permission": "android.permission.read_sms",
                "protection_governance_lane": "aosp_dangerous",
                "prevalence_pct": 5.0,
                "family_balanced_prevalence_pct": 5.0,
                "odds_ratio": 0.2,
                "supporting_family_count": 4,
                "reportability_status": "descriptive_common",
                "largest_family_canonical": "A1",
            },
        ]
    )
    collapse = build_sw_fb_collapse_ledger(lane)
    assert not collapse.empty
    assert float(collapse.iloc[0]["collapse_gap_pct"]) == 40.0
    diff = build_main_type_permission_diff(lane)
    assert not diff.empty
    assert float(diff.iloc[0]["fb_range_pct"]) == 35.0  # 40 - 5


def test_compose_main_comparison_fixture(tmp_path: Path) -> None:
    run_id = "main_cmp"
    run_root = tmp_path / "run"
    type_dir = run_root / "diagnostics" / "type_permission_pattern_report"
    pair_dir = run_root / "diagnostics" / "type_permission_pairwise"
    type_dir.mkdir(parents=True)
    pair_dir.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(json.dumps({"run_status": "complete"}), encoding="utf-8")
    pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "sample_count": 100,
                "active_families": 10,
                "largest_family_share": 0.3,
                "largest_family_canonical": "B1",
                "suppression_or_inclusion_reason": "included_in_main_comparison",
            },
            {
                "type_slug": "rat",
                "sample_count": 80,
                "active_families": 8,
                "largest_family_share": 0.25,
                "largest_family_canonical": "R1",
                "suppression_or_inclusion_reason": "included_in_main_comparison",
            },
        ]
    ).to_csv(type_dir / f"type_inventory_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {
                "type_slug": "banker",
                "permission": "android.permission.read_call_log",
                "protection_governance_lane": "aosp_dangerous",
                "prevalence_pct": 70.0,
                "family_balanced_prevalence_pct": 30.0,
                "odds_ratio": 5.0,
                "supporting_family_count": 6,
                "reportability_status": "family_balanced_supported",
                "largest_family_canonical": "B1",
            },
            {
                "type_slug": "rat",
                "permission": "android.permission.read_call_log",
                "protection_governance_lane": "aosp_dangerous",
                "prevalence_pct": 75.0,
                "family_balanced_prevalence_pct": 55.0,
                "odds_ratio": 20.0,
                "supporting_family_count": 7,
                "reportability_status": "family_balanced_supported",
                "largest_family_canonical": "R1",
            },
            {
                "type_slug": "spyware",
                "permission": "android.permission.read_call_log",
                "protection_governance_lane": "aosp_dangerous",
                "prevalence_pct": 20.0,
                "family_balanced_prevalence_pct": 22.0,
                "odds_ratio": 2.0,
                "supporting_family_count": 4,
                "reportability_status": "descriptive_type_enriched",
                "largest_family_canonical": "S1",
            },
            {
                "type_slug": "adware",
                "permission": "android.permission.read_call_log",
                "protection_governance_lane": "aosp_dangerous",
                "prevalence_pct": 5.0,
                "family_balanced_prevalence_pct": 5.0,
                "odds_ratio": 0.5,
                "supporting_family_count": 3,
                "reportability_status": "descriptive_common",
                "largest_family_canonical": "A1",
            },
        ]
    ).to_csv(type_dir / f"lane_stratified_type_permissions_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {
                "type_slug": "rat",
                "permission_a": "android.permission.internet",
                "permission_b": "android.permission.read_call_log",
                "permission_a_lane": "aosp_normal",
                "permission_b_lane": "aosp_dangerous",
                "lane_pair_class": "cross_lane",
                "family_balanced_prevalence": 0.42,
                "family_balanced_prevalence_pct": 42.0,
                "odds_ratio_type_vs_rest": 28.0,
                "reportability_status": "family_balanced_supported",
                "headline_strength": "strong",
            }
        ]
    ).to_csv(pair_dir / f"pairwise_all_{run_id}.csv", index=False)

    manifest = compose_main_type_permission_comparison(run_root=run_root, run_id=run_id)
    assert manifest["report_status"] == "FINAL_FROM_COMPLETED_RUN"
    assert manifest["controls"]["no_database_access"] is True
    assert manifest["controls"]["three_way_mining"] is False
    out = Path(manifest["output_dir"])
    assert (out / f"sw_fb_collapse_ledger_{run_id}.csv").is_file()
    assert (out / f"type_permission_main_comparison_{run_id}.md").is_file()
    text = (out / f"type_permission_main_comparison_{run_id}.md").read_text(encoding="utf-8")
    assert "discriminators" in text.lower() or "FB range" in text
