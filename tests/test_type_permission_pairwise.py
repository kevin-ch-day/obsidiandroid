"""Tests for Phase-2 type permission pairwise co-occurrence."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from obsidiandroid.reporting.type_permission_pairwise import (
    PAIRWISE_COMPOSER_VERSION,
    classify_pair_reportability,
    compose_type_permission_pairwise_report,
    compute_type_pairwise_table,
)


def test_classify_pair_reportability() -> None:
    assert (
        classify_pair_reportability(
            type_slug="banker",
            positive_samples=10,
            families_with_pair=5,
            families_used=5,
            largest_family_share_of_positives=0.2,
            q_value=0.01,
            effect_odds_ratio=3.0,
            min_sample_support=30,
            min_family_support=3,
            no_headline_types=frozenset({"dropper"}),
        )
        == "insufficient_sample_support"
    )
    assert (
        classify_pair_reportability(
            type_slug="dropper",
            positive_samples=40,
            families_with_pair=1,
            families_used=2,
            largest_family_share_of_positives=0.9,
            q_value=0.01,
            effect_odds_ratio=5.0,
            min_sample_support=30,
            min_family_support=3,
            no_headline_types=frozenset({"dropper"}),
        )
        == "insufficient_family_support"
    )
    assert (
        classify_pair_reportability(
            type_slug="banker",
            positive_samples=100,
            families_with_pair=8,
            families_used=10,
            largest_family_share_of_positives=0.2,
            q_value=0.01,
            effect_odds_ratio=2.5,
            min_sample_support=30,
            min_family_support=3,
            no_headline_types=frozenset({"dropper"}),
        )
        == "family_balanced_supported"
    )


def test_compute_type_pairwise_table_basic() -> None:
    # 6 samples, 3 permissions; type A has a+b co-occurrence across 2 families.
    permission_names = ["android.permission.a", "android.permission.b", "android.permission.c"]
    matrix = np.array(
        [
            [1, 1, 0],
            [1, 1, 0],
            [1, 1, 0],
            [1, 1, 0],
            [0, 0, 1],
            [0, 0, 1],
        ],
        dtype=float,
    )
    type_slugs = np.array(["banker", "banker", "banker", "banker", "rat", "rat"])
    families = np.array(["F1", "F1", "F2", "F2", "R1", "R1"])
    vocab = pd.DataFrame(
        {
            "permission_string": permission_names,
            "pi_bucket_source": ["AOSP", "AOSP", "AOSP"],
            "dangerous_bucket": ["dangerous", "dangerous", "normal"],
        }
    )
    out = compute_type_pairwise_table(
        matrix=matrix,
        permission_names=permission_names,
        type_slugs=type_slugs,
        family_labels=families,
        vocab_meta=vocab,
        min_sample_support=2,
        min_family_support=2,
        min_family_size=2,
        no_headline_types=frozenset(),
    )
    assert not out.empty
    pair = out[(out.permission_a == "android.permission.a") & (out.permission_b == "android.permission.b")]
    assert len(pair) >= 1
    banker = pair[pair.type_slug == "banker"].iloc[0]
    assert int(banker.positive_sample_count) == 4
    assert int(banker.families_with_pair) == 2
    assert "reportability_status" in out.columns
    assert "q_value_fdr" in out.columns


def test_compose_pairwise_fixture(tmp_path: Path) -> None:
    run_id = "pair_fix"
    run_root = tmp_path / "run"
    diag = run_root / "diagnostics"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    diag.mkdir(parents=True)
    tables.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(json.dumps({"run_status": "complete"}), encoding="utf-8")

    # Feature matrix
    rows = []
    for i in range(40):
        rows.append(
            {
                "sample_id": i,
                "perm__android_permission_read_sms": 1 if i < 30 else 0,
                "perm__android_permission_receive_sms": 1 if i < 28 else 0,
                "perm__android_permission_internet": 1,
            }
        )
    pd.DataFrame(rows).to_csv(diag / f"aligned_features_{run_id}.csv.gz", index=False, compression="gzip")
    labels = []
    for i in range(40):
        labels.append(
            {
                "sample_id": i,
                "type_slug": "banker" if i < 30 else "rat",
                "family_canonical": ("B1" if i < 15 else "B2") if i < 30 else ("R1" if i < 35 else "R2"),
            }
        )
    pd.DataFrame(labels).to_csv(diag / f"aligned_labels_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {
                "dangerous_bucket": "dangerous",
                "feature_column": "perm__android_permission_read_sms",
                "permission_string": "android.permission.read_sms",
                "pi_bucket_source": "AOSP",
                "global_support": 30,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "dangerous",
                "feature_column": "perm__android_permission_receive_sms",
                "permission_string": "android.permission.receive_sms",
                "pi_bucket_source": "AOSP",
                "global_support": 28,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "normal",
                "feature_column": "perm__android_permission_internet",
                "permission_string": "android.permission.internet",
                "pi_bucket_source": "AOSP",
                "global_support": 40,
                "retained_after_pruning": "yes",
            },
            {
                "dangerous_bucket": "unknown",
                "feature_column": "perm__weird",
                "permission_string": "weird.token",
                "pi_bucket_source": "UNKNOWN",
                "global_support": 2,
                "retained_after_pruning": "no",
            },
        ]
    ).to_csv(diag / "permission_feature_audit.csv", index=False)
    pd.DataFrame(
        [{"sample_count": 40, "samples_with_permission_rows": 40, "pct_with_permission_rows": 1.0}]
    ).to_csv(tables / f"permission_coverage_report_{run_id}.csv", index=False)

    manifest = compose_type_permission_pairwise_report(
        run_root=run_root,
        run_id=run_id,
        min_global_support=20,
        min_sample_support=10,
        min_family_support=2,
        min_family_size=2,
    )
    assert manifest["composer_version"] == PAIRWISE_COMPOSER_VERSION
    assert manifest["report_status"] == "FINAL_FROM_COMPLETED_RUN"
    assert manifest["controls"]["no_database_access"] is True
    assert manifest["controls"]["three_way_mining"] is False
    assert manifest["pair_count_total"] >= 1
    assert "suppression_summary" in manifest
    out = Path(manifest["output_dir"])
    assert (out / f"pairwise_all_{run_id}.csv").is_file()
    assert (out / f"type_permission_pairwise_report_{run_id}.md").is_file()
    text = (out / f"type_permission_pairwise_report_{run_id}.md").read_text(encoding="utf-8")
    assert "Suppression summary" in text
    assert "Three-way mining: **disabled**" in text
    assert "permission_a_lane" in pd.read_csv(out / f"pairwise_all_{run_id}.csv").columns
    assert "lane_pair_class" in pd.read_csv(out / f"pairwise_all_{run_id}.csv").columns
    assert "protection_lane_contract_version" in manifest


def test_within_cross_lane_pairs_and_unresolved_gate() -> None:
    permission_names = [
        "android.permission.internet",
        "android.permission.read_sms",
        "android.permission.write_settings",
    ]
    matrix = np.array(
        [
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, 0],
            [1, 1, 0],
            [1, 0, 1],
            [1, 0, 1],
        ],
        dtype=float,
    )
    vocab = pd.DataFrame(
        {
            "permission_string": permission_names,
            "pi_bucket_source": ["AOSP", "AOSP", "AOSP"],
            "dangerous_bucket": ["normal", "dangerous", "unknown"],
        }
    )
    out = compute_type_pairwise_table(
        matrix=matrix,
        permission_names=permission_names,
        type_slugs=np.array(["banker"] * 6),
        family_labels=np.array(["F1", "F1", "F2", "F2", "F3", "F3"]),
        vocab_meta=vocab,
        min_sample_support=2,
        min_family_support=2,
        min_family_size=2,
        no_headline_types=frozenset(),
    )
    assert "permission_a_lane" in out.columns
    assert set(out["lane_pair_class"]).issubset({"within_lane", "cross_lane"})
    unresolved = out[
        (out.permission_a_lane == "unknown_unresolved")
        | (out.permission_b_lane == "unknown_unresolved")
    ]
    if not unresolved.empty:
        assert (unresolved.reportability_status == "protection_level_unresolved").all()


def test_pair_reportability_fdr_and_lane_gates() -> None:
    assert (
        classify_pair_reportability(
            type_slug="banker",
            positive_samples=100,
            families_with_pair=5,
            families_used=5,
            largest_family_share_of_positives=0.2,
            q_value=0.2,
            effect_odds_ratio=3.0,
            min_sample_support=30,
            min_family_support=3,
            no_headline_types=frozenset(),
            lane_a="aosp_dangerous",
            lane_b="aosp_dangerous",
            family_balanced_prevalence=0.2,
        )
        == "not_significant_after_fdr"
    )
    assert (
        classify_pair_reportability(
            type_slug="banker",
            positive_samples=100,
            families_with_pair=5,
            families_used=5,
            largest_family_share_of_positives=0.2,
            q_value=0.01,
            effect_odds_ratio=3.0,
            min_sample_support=30,
            min_family_support=3,
            no_headline_types=frozenset(),
            lane_a="unknown_unresolved",
            lane_b="aosp_dangerous",
            family_balanced_prevalence=0.2,
        )
        == "protection_level_unresolved"
    )


def test_interpretation_composer_no_db(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    (run_root / "diagnostics" / "type_permission_pattern_report").mkdir(parents=True)
    (run_root / "diagnostics" / "type_permission_pairwise").mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(json.dumps({"run_status": "complete"}), encoding="utf-8")
    from obsidiandroid.reporting.type_permission_interpretation import (
        compose_type_permission_interpretation,
    )

    manifest = compose_type_permission_interpretation(run_root=run_root, run_id="x")
    assert manifest["report_status"] == "FINAL_FROM_COMPLETED_RUN"
    assert manifest["controls"]["no_database_access"] is True
    assert manifest["controls"]["no_core_connection"] is True
