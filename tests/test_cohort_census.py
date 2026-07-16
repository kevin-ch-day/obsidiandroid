"""Tests for paper-facing cohort census and gate-matrix exports."""

from __future__ import annotations

from pathlib import Path

import json
import pandas as pd

from obsidiandroid.governance.cohort_census import (
    ProfileRuntimeSemantics,
    _build_profile_summary_row,
    _report_lines,
    write_cohort_census_exports,
)
from obsidiandroid.governance import cohort_census
from obsidiandroid.governance import cohort_gap_audit
from obsidiandroid.governance.cohort_gap_audit import (
    CohortGatePolicy,
    build_cohort_gap_audit,
    write_cohort_gap_artifacts,
)


def _locked_semantics(contract: dict[str, object]) -> ProfileRuntimeSemantics:
    return ProfileRuntimeSemantics(
        profile_id="malicious_temporal_stability_locked",
        canonical_profile_id="malicious_temporal_stability_locked",
        readiness_bucket="android_high_or_strong_vt_with_permission_obs",
        paper_locked=True,
        type_slug_filter=None,
        min_samples_per_family=20,
        require_mapped_family=True,
        require_sha256=True,
        allow_missing_package_name=True,
        exclude_unknown_type_slug=True,
        exclude_weak_label_kinds=False,
        exclude_family_label_conflicts=False,
        min_malicious_detections=1,
        family_cap=None,
        family_cap_seed=None,
        type_cap=None,
        type_cap_seed=None,
        type_cap_by_slug={},
        exclude_families=("devixor", "gigabud"),
        include_families=tuple(),
        time_window_start_utc="2020-01-01T00:00:00Z",
        time_window_end_utc="2026-01-01T00:00:00Z",
        require_effective_first_seen=True,
        dataset_filter_mode="malicious_only",
        exclude_unknown_from_main_results=True,
        contract=contract,
    )


def test_locked_profile_summary_prefers_manifest_counts_and_hashes(monkeypatch) -> None:
    monkeypatch.setattr(
        "obsidiandroid.governance.cohort_census._fetch_confidence_bucket_rows",
        lambda sample_ids: pd.DataFrame({"sample_id": sample_ids, "confidence_bucket": ["high"] * len(sample_ids)}),
    )
    contract = {
        "expected": {
            "sample_count": 1226,
            "family_count": 39,
            "type_count": 6,
            "time_window_semantics": "start_inclusive_end_exclusive",
        },
        "sample_id_lock": {
            "cohort_hash": "cohort-hash-1226",
            "taxonomy_hash": "taxonomy-hash-39-6",
            "member_list_path": "artifacts/baselines/20260504/lock.csv",
        },
    }
    semantics = _locked_semantics(contract)
    cohort_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_id": [11, 12],
            "family_canonical": ["FamA", "FamB"],
            "type_slug": ["banker", "rat"],
            "source_batch_label": ["batch_a", "batch_b"],
            "sha256": ["a" * 64, "b" * 64],
        }
    )
    permission_df = pd.DataFrame(
        {
            "sample_id": [1],
            "permission_obs_rows": [3],
            "permission_unique_count": [3],
            "permission_common_rows": [1],
        }
    )
    row = _build_profile_summary_row(
        semantics=semantics,
        cohort_df=cohort_df,
        broad_catalog_df=cohort_df,
        permission_aggregates_df=permission_df,
    )
    assert row["sample_count"] == 1226
    assert row["family_count"] == 39
    assert row["type_count"] == 6
    assert row["cohort_membership_hash"] == "cohort-hash-1226"
    assert row["taxonomy_hash"] == "taxonomy-hash-39-6"
    assert row["live_catalog_match_count"] == 2


def test_profile_summary_marks_permission_and_confidence_as_advisory(monkeypatch) -> None:
    monkeypatch.setattr(
        "obsidiandroid.governance.cohort_census._fetch_confidence_bucket_rows",
        lambda sample_ids: pd.DataFrame({"sample_id": sample_ids, "confidence_bucket": ["high"] * len(sample_ids)}),
    )
    contract = {"expected": {}, "sample_id_lock": {}}
    semantics = ProfileRuntimeSemantics(
        profile_id="malicious_temporal_stability",
        canonical_profile_id="malicious_temporal_stability",
        readiness_bucket="android_high_or_strong_vt_with_permission_obs",
        paper_locked=False,
        type_slug_filter=None,
        min_samples_per_family=20,
        require_mapped_family=True,
        require_sha256=True,
        allow_missing_package_name=True,
        exclude_unknown_type_slug=True,
        exclude_weak_label_kinds=False,
        exclude_family_label_conflicts=False,
        min_malicious_detections=1,
        family_cap=None,
        family_cap_seed=None,
        type_cap=None,
        type_cap_seed=None,
        type_cap_by_slug={},
        exclude_families=("devixor", "gigabud"),
        include_families=tuple(),
        time_window_start_utc="2020-01-01T00:00:00Z",
        time_window_end_utc="2026-01-01T00:00:00Z",
        require_effective_first_seen=True,
        dataset_filter_mode="malicious_only",
        exclude_unknown_from_main_results=True,
        contract=contract,
    )
    cohort_df = pd.DataFrame(
        {
            "sample_id": [1],
            "family_id": [11],
            "family_canonical": ["FamA"],
            "type_slug": ["banker"],
            "source_batch_label": ["batch_a"],
            "sha256": ["a" * 64],
        }
    )
    row = _build_profile_summary_row(
        semantics=semantics,
        cohort_df=cohort_df,
        broad_catalog_df=cohort_df,
        permission_aggregates_df=pd.DataFrame(columns=["sample_id", "permission_obs_rows"]),
    )
    assert row["permission_observation_requirement"] == "advisory_readiness_bucket"
    assert row["permission_observation_enforced"] is False
    assert row["confidence_bucket_rule"] == "advisory_high_or_strong_readiness_bucket"
    assert row["confidence_bucket_enforced"] is False


def test_write_cohort_census_exports_writes_required_files(tmp_path: Path) -> None:
    bundle = {
        "profile_rows": [
            {
                "profile_id": "malicious_temporal_stability_locked",
                "canonical_profile_id": "malicious_temporal_stability_locked",
                "paper_locked": True,
                "sample_count": 1226,
                "family_count": 39,
                "type_count": 6,
                "type_slugs": ["banker", "rat"],
                "permission_observation_requirement": "advisory_readiness_bucket",
                "permission_observation_enforced": False,
                "confidence_bucket_rule": "advisory_high_or_strong_readiness_bucket",
                "confidence_bucket_enforced": False,
                "cohort_membership_hash": "hash1",
                "taxonomy_hash": "hash2",
                "label_snapshot_hash": "hash3",
                "support_floor": 20,
                "malicious_detection_threshold": 1,
                "suspicious_handling": {"dataset_filter_mode": "malicious_only"},
                "family_exclusions": ["devixor", "gigabud"],
                "family_cap": None,
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
                "source_snapshot_or_lock_file": "lock.csv",
                "top_families": {"FamA": 10},
                "top_malware_types": {"banker": 10},
                "source_batch_label_distribution": {"Zimperium IOC": 10},
                "permission_coverage": {"rows_with_permission_obs": 10, "rows_total": 20, "coverage_pct": 0.5},
                "confidence_bucket_distribution": {"high": 10},
                "top_family_share": 0.1,
                "live_catalog_match_count": 1226,
                "live_catalog_family_count": 39,
                "live_catalog_type_count": 6,
                "broad_catalog_family_count": 100,
                "readiness_bucket": "android_high_or_strong_vt_with_permission_obs",
            }
        ],
        "locked_vs_current_overlap_csv": pd.DataFrame(
            {
                "sample_id": [1],
                "in_locked_membership": [True],
                "in_current_governed": [False],
                "current_gate_reason": ["outside_time_window"],
            }
        ),
        "locked_vs_current_overlap_json": [{"sample_id": 1, "in_locked_membership": True}],
        "cohort_exclusion_reasons": pd.DataFrame(
            {"profile_id": ["malicious_temporal_stability"], "canonical_profile_id": ["malicious_temporal_stability"], "exclusion_reason": ["outside_time_window"], "rows": [39]}
        ),
        "cohort_expansion_candidates_by_family": pd.DataFrame(
            {"profile_id": ["malicious_temporal_stability"], "canonical_profile_id": ["malicious_temporal_stability"], "family_canonical": ["ArsinkRAT"], "rows": [482]}
        ),
        "cohort_expansion_candidates_by_type": pd.DataFrame(
            {"profile_id": ["malicious_temporal_stability"], "canonical_profile_id": ["malicious_temporal_stability"], "type_slug": ["spyware"], "rows": [482]}
        ),
        "cohort_source_batch_distribution": pd.DataFrame(
            {"profile_id": ["malicious_temporal_stability"], "canonical_profile_id": ["malicious_temporal_stability"], "distribution_scope": ["cohort_membership"], "source_batch_label": ["Zimperium IOC"], "rows": [482], "share": [0.3]}
        ),
        "support_floor_reference": [{"support_floor": 20, "sample_count": 1602, "family_count": 40, "type_count": 6}],
        "devixor_gigabud_counterfactual": {"cohort_size_if_included": 2000, "Devixor": {"rows": 100, "share": 0.05}, "Gigabud": {"rows": 50, "share": 0.025}, "combined_share": 0.075},
        "strict_export_status": {"paper_constants_present": False, "missing_required_sources": ["paper_constants.json"], "passes": False},
        "archived_lock_concepts": [{"path": "artifacts/baselines/20260526T021235Z__8b6966/MANIFEST.txt", "summary": "run_id=20260526T021235Z__8b6966", "body": "run_id=20260526T021235Z__8b6966"}],
        "expansion_recommendation": {"best_candidate_profile_id": "malicious_temporal_stability_expanded", "rationale": "support floor 10", "defensible_today": False},
        "locked_profile_row": {"sample_count": 1226},
    }
    paths = write_cohort_census_exports(output_dir=tmp_path, bundle=bundle)
    expected = {
        "cohort_census_gate_matrix_csv",
        "cohort_census_gate_matrix_json",
        "locked_vs_current_overlap_csv",
        "locked_vs_current_overlap_json",
        "cohort_exclusion_reasons_csv",
        "cohort_expansion_candidates_by_family_csv",
        "cohort_expansion_candidates_by_type_csv",
        "cohort_source_batch_distribution_csv",
        "cohort_census_report_md",
    }
    assert set(paths) == expected
    for path in paths.values():
        assert Path(path).exists()
    payload = json.loads((tmp_path / "cohort_census_gate_matrix.json").read_text(encoding="utf-8"))
    assert payload["profiles"][0]["sample_count"] == 1226
    report = (tmp_path / "cohort_census_report.md").read_text(encoding="utf-8")
    assert "1226 / 39 / 6" in report
    assert "1187 / 35 / 3" in report
    assert "Strict export gates fail today" in report


def test_report_lines_call_out_active_and_archived_lock_concepts() -> None:
    lines = _report_lines(
        {
            "profile_rows": [
                {
                    "profile_id": "malicious_temporal_stability_locked",
                    "canonical_profile_id": "malicious_temporal_stability_locked",
                    "sample_count": 1226,
                    "family_count": 39,
                    "type_count": 6,
                    "permission_observation_requirement": "advisory_readiness_bucket",
                    "confidence_bucket_rule": "advisory_high_or_strong_readiness_bucket",
                },
                {
                    "profile_id": "malicious_temporal_stability",
                    "canonical_profile_id": "malicious_temporal_stability",
                    "sample_count": 1602,
                    "family_count": 40,
                    "type_count": 6,
                    "top_family_share": 0.2,
                    "permission_observation_requirement": "advisory_readiness_bucket",
                    "confidence_bucket_rule": "advisory_high_or_strong_readiness_bucket",
                },
                {
                    "profile_id": "malicious_temporal_stability_expanded",
                    "canonical_profile_id": "malicious_temporal_stability_expanded",
                    "sample_count": 1800,
                    "family_count": 55,
                    "type_count": 6,
                    "top_family_share": 0.21,
                },
                {
                    "profile_id": "malicious_temporal_stability_long_tail",
                    "canonical_profile_id": "malicious_temporal_stability_long_tail",
                    "sample_count": 1900,
                    "family_count": 70,
                    "type_count": 6,
                },
                {
                    "profile_id": "malicious_temporal_consensus10",
                    "canonical_profile_id": "malicious_temporal_consensus10",
                    "sample_count": 900,
                    "family_count": 20,
                    "type_count": 6,
                },
                {
                    "profile_id": "malicious_temporal_family300",
                    "canonical_profile_id": "malicious_temporal_family300",
                    "sample_count": 1500,
                    "family_count": 38,
                    "type_count": 6,
                },
            ],
            "support_floor_reference": [{"support_floor": 20, "sample_count": 1602, "family_count": 40, "type_count": 6}],
            "strict_export_status": {"paper_constants_present": False, "missing_required_sources": ["paper_constants.json"], "passes": False},
            "expansion_recommendation": {"best_candidate_profile_id": "malicious_temporal_stability_expanded", "rationale": "support floor 10", "defensible_today": False},
            "archived_lock_concepts": [{"path": "artifacts/baselines/20260526T021235Z__8b6966/MANIFEST.txt"}],
            "locked_vs_current_overlap_csv": pd.DataFrame(
                {
                    "sample_id": [1, 2],
                    "in_locked_membership": [True, True],
                    "in_current_governed": [False, True],
                    "current_gate_reason": ["outside_time_window", "eligible_current_profile"],
                }
            ),
            "devixor_gigabud_counterfactual": {"Devixor": {"rows": 100, "share": 0.05}, "Gigabud": {"rows": 50, "share": 0.025}, "combined_share": 0.075},
        }
    )
    text = "\n".join(lines)
    assert "reviewed ZIP is stale" in text
    assert "1226 / 39 / 6" in text
    assert "1187 / 35 / 3" in text
    assert "Multiple lock concepts: **yes**" in text


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


def test_known_family_aliases_are_not_reported_as_family_label_conflicts() -> None:
    """Alias drift is curation context, not contradictory family evidence."""
    frame = pd.DataFrame(
        {
            "family_label": ["Wroba", "BlackLoan", "WrongFamily"],
            "family_canonical": ["RoamingMantis", "SpyLoan", "SpyLoan"],
        }
    )

    expected = [False, False, True]
    assert cohort_census._family_label_conflict_mask(frame).tolist() == expected  # pylint: disable=protected-access
    assert cohort_gap_audit._family_label_conflict_mask(frame).tolist() == expected  # pylint: disable=protected-access


def test_textual_null_or_identifier_shaped_family_values_are_not_mapped() -> None:
    """Readiness and gap reports must match the target-surface eligibility guard."""
    frame = pd.DataFrame(
        {
            "family_id": [1, 2, 3],
            "family_canonical": ["nan", "family_id=2", "NamedFamily"],
            "type_slug": ["banker", "banker", "banker"],
        }
    )

    expected = [False, False, True]
    assert cohort_census._mapped_family_mask(frame).tolist() == expected  # pylint: disable=protected-access
    assert cohort_gap_audit._mapped_family_mask(frame).tolist() == expected  # pylint: disable=protected-access
