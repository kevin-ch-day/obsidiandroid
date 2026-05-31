"""Export locked-vs-live cohort gap artifacts for a paper-locked profile."""

from __future__ import annotations

import argparse
from pathlib import Path

from obsidiandroid.cli.profile_manager import load_profile
from obsidiandroid.database import db_sample_metadata_queries
from obsidiandroid.governance import paper_cohort_contract
from obsidiandroid.governance.cohort_gap_audit import (
    build_cohort_gap_audit,
    policy_from_profile,
    write_cohort_gap_artifacts,
)
from obsidiandroid.governance.cohort_lock_manifest import read_member_list


def _current_governed_dataframe(profile: dict) -> object:
    policy = policy_from_profile(profile)
    return db_sample_metadata_queries.load_samples_by_type(
        type_slug=policy.type_slug_filter,
        min_samples_per_family=policy.min_samples_per_family,
        require_mapped_family=policy.require_mapped_family,
        require_sha256=policy.require_sha256,
        allow_missing_package_name=policy.allow_missing_package_name,
        exclude_unknown_type_slug=policy.exclude_unknown_type_slug,
        exclude_weak_label_kinds=policy.exclude_weak_label_kinds,
        exclude_family_label_conflicts=policy.exclude_family_label_conflicts,
        effective_time_start_utc=policy.time_window_start_utc or None,
        effective_time_end_utc=policy.time_window_end_utc or None,
        require_effective_first_seen=policy.require_effective_first_seen,
        exclude_family_canonical=policy.exclude_families,
    )


def _full_catalog_dataframe(profile: dict) -> object:
    policy = policy_from_profile(profile)
    return db_sample_metadata_queries.load_samples_by_type(
        type_slug=policy.type_slug_filter,
        min_samples_per_family=None,
        require_mapped_family=False,
        require_sha256=False,
        allow_missing_package_name=True,
        exclude_unknown_type_slug=False,
        exclude_weak_label_kinds=False,
        exclude_family_label_conflicts=False,
        effective_time_start_utc=None,
        effective_time_end_utc=None,
        require_effective_first_seen=False,
        exclude_family_canonical=tuple(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="malicious_temporal_stability_locked")
    parser.add_argument(
        "--output-dir",
        default="artifacts/paper/cohort_gap_audit",
        help="Directory for CSV/JSON/Markdown exports.",
    )
    args = parser.parse_args()

    profile = load_profile(args.profile)
    contract = paper_cohort_contract.build_declared_contract(profile)
    lock_path = str(contract.get("sample_id_lock", {}).get("path", "") or "").strip()
    if not lock_path:
        raise SystemExit(f"profile '{args.profile}' has no enforceable sample-id lock")

    locked = read_member_list(lock_path)
    current = _current_governed_dataframe(profile)
    catalog = _full_catalog_dataframe(profile)
    audit = build_cohort_gap_audit(
        lock_members_df=locked,
        current_governed_df=current,
        full_catalog_df=catalog,
        policy=policy_from_profile(profile),
        contract=contract,
    )
    out = write_cohort_gap_artifacts(output_dir=Path(args.output_dir), audit=audit)
    for key, value in out.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

