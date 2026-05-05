"""Smoke tests for headline score scope and split contamination helpers."""

from pathlib import Path

import pandas as pd

from obsidiandroid.reporting import high_score_skeptic_audits as hssa


def test_write_headline_score_scope(tmp_path: Path) -> None:
    q1 = {
        "governed_samples": 100,
        "aligned_supervised_samples": 100,
        "trainable_after_support_filter": 80,
        "families_represented": 10,
        "malware_types_represented": 3,
    }
    drop = [{"family": "A", "aligned_support": 1}, {"family": "B", "aligned_support": 2}]
    out = hssa.write_headline_score_scope(
        diagnostics_dir=tmp_path,
        run_id="r1",
        q1=q1,
        manifest_context={},
        drop_detail=drop,
    )
    assert out["governed_cohort"]["samples"] == 100
    assert (tmp_path / "headline_score_scope.json").is_file()
    assert (tmp_path / "headline_score_scope.md").is_file()


def test_split_contamination_package_overlap(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {"sample_id": 1, "sha256": "aa", "split_role": "train", "package_name": "com.foo.app", "family_canonical": "F1", "year": 2023},
            {"sample_id": 2, "sha256": "bb", "split_role": "test", "package_name": "com.foo.app", "family_canonical": "F2", "year": 2024},
            {"sample_id": 3, "sha256": "cc", "split_role": "train", "package_name": "com.other", "family_canonical": "F1", "year": 2023},
        ]
    )
    p = tmp_path / "split_freeze_headline_r2.csv"
    df.to_csv(p, index=False)
    payload = hssa.write_split_contamination_audit(
        diagnostics_dir=tmp_path,
        run_id="r2",
        samples_df=None,
    )
    assert payload["sha_overlap_train_test"] == 0
    assert payload["package_names_in_both_splits"] == 1
    assert (tmp_path / "train_test_package_overlap.csv").is_file()


def test_package_prefix_two_segments() -> None:
    assert hssa._package_prefix_two_segments("com.bad.app") == "com.bad"
    assert hssa._package_prefix_two_segments("single") == "single"
