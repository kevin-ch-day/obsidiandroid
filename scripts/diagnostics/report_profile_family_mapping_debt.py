"""Inspect and export profile-scoped family-mapping debt breakdowns.

This report explains why governed SQL cohorts exclude rows for missing family_id:
blank resolved slugs, policy-held resolved slugs, and true catalog-lag slugs are
reported separately so operators do not treat governance residue as repair debt.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.database.db_family_mapping_debt import (
    fetch_profile_family_mapping_debt_rows,
    fetch_profile_family_mapping_debt_summary,
)


OUTPUT_DIR = Path("output") / "diagnostics"
JSON_OUT = OUTPUT_DIR / "profile_family_mapping_debt_latest.json"
CSV_OUT = OUTPUT_DIR / "profile_family_mapping_debt_latest.csv"
POLICY_HELD_WORKLIST_CSV_OUT = OUTPUT_DIR / "profile_policy_held_slug_worklist_latest.csv"

_DEFAULT_PROFILES = (
    "android_malware_all_current",
    "android_malware_major_families",
    "android_malware_expanded_families",
    "android_malware_type_taxonomy",
)


def build_report(*, profile_ids: tuple[str, ...]) -> dict[str, object]:
    """Collect profile family-mapping debt summaries and slug clusters."""
    summaries: list[dict[str, object]] = []
    detail_frames: list[pd.DataFrame] = []
    for profile_id in profile_ids:
        summary = fetch_profile_family_mapping_debt_summary(profile_id)
        summaries.append(summary)
        rows = fetch_profile_family_mapping_debt_rows(profile_id)
        frame = pd.DataFrame(rows)
        if not frame.empty:
            frame.insert(0, "profile_id", profile_id)
        detail_frames.append(frame)
    detail_rows = (
        pd.concat(detail_frames, ignore_index=True)
        if detail_frames
        else pd.DataFrame(
            columns=[
                "profile_id",
                "mapping_lane",
                "resolved_family_lc",
                "token_kind",
                "sample_count",
                "high_or_strong_sample_count",
                "known_locally",
                "recommended_next_action",
            ]
        )
    )
    return {
        "profiles": summaries,
        "detail_rows": detail_rows,
    }


def _compact_lane_counts(summary: dict[str, object]) -> str:
    lane_counts = summary.get("lane_counts", {})
    if not isinstance(lane_counts, dict) or not lane_counts:
        return "none"
    return "; ".join(
        f"{lane}={int(count or 0)}"
        for lane, count in sorted(
            lane_counts.items(),
            key=lambda item: (-int(item[1] or 0), str(item[0])),
        )
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-id",
        action="append",
        default=[],
        help="Profile to analyze (default: canonical profiles).",
    )
    args = parser.parse_args()
    profile_ids = tuple(args.profile_id or _DEFAULT_PROFILES)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(profile_ids=profile_ids)
    detail_rows = report["detail_rows"]
    detail_rows.to_csv(CSV_OUT, index=False)
    policy_held_rows = detail_rows[
        detail_rows["mapping_lane"].fillna("").astype(str).eq("policy_held_resolved_slug")
    ].copy()
    policy_held_rows.to_csv(POLICY_HELD_WORKLIST_CSV_OUT, index=False)
    JSON_OUT.write_text(
        json.dumps({"profiles": report["profiles"]}, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"[EXPORT] Profile family-mapping debt JSON: {JSON_OUT.as_posix()}")
    print(f"[EXPORT] Profile family-mapping debt CSV: {CSV_OUT.as_posix()}")
    print(f"[EXPORT] Profile policy-held slug worklist: {POLICY_HELD_WORKLIST_CSV_OUT.as_posix()}")
    print(f"Profiles: {len(report['profiles'])}")
    print(f"Policy-held slug clusters: {len(policy_held_rows)}")
    for summary in report["profiles"]:
        if not isinstance(summary, dict):
            continue
        print(
            f"- {summary.get('profile_id')}: governed={summary.get('governed_sql_rows')} "
            f"excluded_unmapped={summary.get('excluded_unmapped_family_rows')} "
            f"(blank={summary.get('blank_resolved_slug_rows')}, "
            f"policy_held={summary.get('policy_held_resolved_slug_rows')}, "
            f"true_unmapped={summary.get('true_unmapped_resolved_slug_rows')})"
        )
        print(f"  lanes: {_compact_lane_counts(summary)}")
    print(f"Slug clusters: {len(detail_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
