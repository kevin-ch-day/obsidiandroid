"""Tests for immutable lock vs live cohort gap auditing."""

from __future__ import annotations

from pathlib import Path

import json
import pandas as pd

from obsidiandroid.governance.cohort_gap_audit import (
    CohortGatePolicy,
    build_cohort_gap_audit,
    write_cohort_gap_artifacts,
)


def test_locked_member_excluded_by_live_gates_is_reported(tmp_path: Path) -> None:
    policy = CohortGatePolicy(
        min_samples_per_family=2,
        require_mapped_family=True,
        require_sha256=True,
        allow_missing_package_name=True,
        exclude_unknown_type_slug=True,
        exclude_weak_label_kinds=False,
        exclude_family_label_conflicts=False,
        exclude_families=tuple(),
        time_window_start_utc="2020-01-01T00:00:00Z",
        time_window_end_utc="2026-01-01T00:00:00Z",
        require_effective_first_seen=True,
        type_slug_filter=None,
    )
    lock_members = pd.DataFrame({"sample_id": [1, 2, 3]})
    current = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a" * 64, "b" * 64],
            "family_canonical": ["FamA", "FamA"],
            "family_id": [11, 11],
            "type_slug": ["banker", "banker"],
            "source_batch_label": ["s1", "s1"],
            "effective_first_seen_at_utc": ["2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z"],
            "vt_first_submission_at_utc": ["2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z"],
        }
    )
    catalog = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "sha256": ["a" * 64, "b" * 64, "c" * 64, "d" * 64],
            "family_canonical": ["FamA", "FamA", "FamB", "FamC"],
            "family_id": [11, 11, 22, 33],
            "family_label": ["FamA", "FamA", "FamB", "FamC"],
            "type_slug": ["banker", "banker", "rat", "banker"],
            "sample_label_kind": ["family_or_common_name"] * 4,
            "source_batch_label": ["s1", "s1", "s2", "s3"],
            "android_package_name": ["pkg1", "pkg2", "pkg3", "pkg4"],
            "effective_first_seen_at_utc": [
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                "2026-02-01T00:00:00Z",
                "2024-03-01T00:00:00Z",
            ],
            "vt_first_submission_at_utc": [
                "2024-01-01T00:00:00Z",
                "2024-02-01T00:00:00Z",
                "2026-02-01T00:00:00Z",
                "2024-03-01T00:00:00Z",
            ],
        }
    )
    audit = build_cohort_gap_audit(
        lock_members_df=lock_members,
        current_governed_df=current,
        full_catalog_df=catalog,
        policy=policy,
        contract={
            "profile_id": "malicious_temporal_stability_locked",
            "contract_id": "contract1",
            "sample_id_lock": {"lock_version": "v1", "cohort_hash": "c1", "taxonomy_hash": "t1"},
        },
    )
    failing = audit["locked_rows_now_failing_current_gates"]
    assert failing["sample_id"].tolist() == [3]
    assert failing.iloc[0]["current_gate_reason"] == "outside_time_window"

    paths = write_cohort_gap_artifacts(output_dir=tmp_path, audit=audit)
    summary = json.loads(Path(paths["cohort_gap_summary"]).read_text(encoding="utf-8"))
    assert summary["locked_rows_now_failing_time_window_count"] == 1

