"""Inspect and export suppression-aware missing-primary label triage rows.

This report turns the active missing-primary debt surfaced by cohort readiness
into a repeatable operator worklist. It is intentionally read-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.database.db_cohort_readiness import fetch_missing_primary_label_triage_rows
from obsidiandroid.common.hash_utils import hash_payload, short_hash


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "missing_primary_label_triage_latest.csv"
PROPOSAL_CSV_OUT = OUTPUT_DIR / "missing_primary_label_authority_backfill_proposals_latest.csv"
REVIEW_TEMPLATE_CSV_OUT = OUTPUT_DIR / "missing_primary_label_authority_backfill_review_template_latest.csv"
SUMMARY_JSON_OUT = OUTPUT_DIR / "missing_primary_label_triage_summary_latest.json"
TRIAGE_SCHEMA_VERSION = 2
PROPOSAL_GROUP_COLUMNS = [
    "proposed_classification_primary",
    "authority_type_slug",
    "authority_parent_type_slug",
    "authority_family_slug",
    "confidence_bucket",
]
PROPOSAL_REVIEW_STATUS = "pending_human_review"
PROPOSAL_BASIS = (
    "authority_family_typed plus high/strong VT consensus; "
    "proposed primary is authority parent type when present, otherwise authority type"
)


def _clean_text(value: object) -> str:
    """Normalize scalar export values without treating missing values as strings."""
    return "" if pd.isna(value) else str(value).strip()


def build_authority_backfill_proposals(detail_rows: pd.DataFrame) -> pd.DataFrame:
    """Aggregate review-only primary-label proposals backed by governed authority.

    The export deliberately does not update the source catalog.  It groups only
    high/strong VT rows whose family and type are already governed, making the
    proposed primary label traceable to the authority view rather than inferred
    from a vendor label alone.
    """
    columns = [
        "proposal_id",
        "review_status",
        "review_basis",
        "proposed_classification_primary",
        "authority_type_slug",
        "authority_parent_type_slug",
        "authority_family_slug",
        "confidence_bucket",
        "sample_count",
        "sample_id_hash",
        "sample_ids",
    ]
    if detail_rows.empty:
        return pd.DataFrame(columns=columns)
    candidates = detail_rows.loc[
        detail_rows["residual_lane"].eq("authority_backed_primary_backfill_review")
    ].copy()
    if candidates.empty:
        return pd.DataFrame(columns=columns)
    group_columns = PROPOSAL_GROUP_COLUMNS
    candidates["sample_id"] = pd.to_numeric(candidates["sample_id"], errors="coerce")
    grouped = (
        candidates.groupby(group_columns, dropna=False)["sample_id"]
        .agg(
            sample_count="count",
            sample_ids=lambda values: ",".join(
                str(int(value)) for value in sorted(value for value in values if pd.notna(value))
            ),
        )
        .reset_index()
        .sort_values(
            ["sample_count", "proposed_classification_primary", "authority_family_slug"],
            ascending=[False, True, True],
        )
    )
    grouped["sample_id_hash"] = grouped["sample_ids"].map(
        lambda value: hash_payload(
            [int(token) for token in str(value).split(",") if str(token).strip()]
        )
    )
    grouped["proposal_id"] = grouped.apply(
        lambda row: "mpb_"
        + short_hash(
            hash_payload(
                {
                    "group": {column: _clean_text(row[column]) for column in group_columns},
                    "sample_id_hash": str(row["sample_id_hash"]),
                }
            ),
            size=16,
        ),
        axis=1,
    )
    grouped["review_status"] = PROPOSAL_REVIEW_STATUS
    grouped["review_basis"] = PROPOSAL_BASIS
    return grouped[columns]


def attach_proposal_review_fields(
    detail_rows: pd.DataFrame,
    proposals: pd.DataFrame,
) -> pd.DataFrame:
    """Attach stable proposal IDs to closure-ready detail rows without approving them.

    The detail export stays one row per catalog sample.  Only candidates in the
    authority-backed lane receive a proposal ID and ``pending_human_review``;
    every other residual row remains explicitly outside the automatic-backfill
    path.
    """
    out = detail_rows.copy()
    out["proposal_id"] = ""
    out["proposal_review_status"] = "not_closure_ready"
    if out.empty or proposals.empty:
        return out
    candidate_mask = out["residual_lane"].eq("authority_backed_primary_backfill_review")
    if not bool(candidate_mask.any()):
        return out
    proposal_lookup = proposals.set_index(PROPOSAL_GROUP_COLUMNS)["proposal_id"]
    candidate_index = pd.MultiIndex.from_frame(out.loc[candidate_mask, PROPOSAL_GROUP_COLUMNS])
    out.loc[candidate_mask, "proposal_id"] = candidate_index.map(proposal_lookup).fillna("").tolist()
    out.loc[candidate_mask, "proposal_review_status"] = PROPOSAL_REVIEW_STATUS
    return out


def build_review_template(proposals: pd.DataFrame) -> pd.DataFrame:
    """Build a separate, non-authoritative human-review ledger template.

    This file is intentionally not used to mutate the catalog.  A future
    apply command must validate a reviewer-approved copy against the current
    proposal ID and sample-membership hash before it can make any database
    change.
    """
    columns = [
        "proposal_id",
        "review_status",
        "decision",
        "reviewer",
        "reviewed_at_utc",
        "review_note",
        "proposed_classification_primary",
        "authority_type_slug",
        "authority_parent_type_slug",
        "authority_family_slug",
        "confidence_bucket",
        "sample_count",
        "sample_id_hash",
        "review_basis",
    ]
    if proposals.empty:
        return pd.DataFrame(columns=columns)
    template = proposals[
        [
            "proposal_id",
            "review_status",
            "proposed_classification_primary",
            "authority_type_slug",
            "authority_parent_type_slug",
            "authority_family_slug",
            "confidence_bucket",
            "sample_count",
            "sample_id_hash",
            "review_basis",
        ]
    ].copy()
    template.insert(2, "decision", "pending")
    template.insert(3, "reviewer", "")
    template.insert(4, "reviewed_at_utc", "")
    template.insert(5, "review_note", "")
    return template[columns]


def build_report(*, include_suppressed: bool = False) -> dict[str, pd.DataFrame]:
    """Collect the key missing-primary triage slices."""
    detail_rows = pd.DataFrame(fetch_missing_primary_label_triage_rows(include_suppressed=include_suppressed))
    proposals = build_authority_backfill_proposals(detail_rows)
    detail_rows = attach_proposal_review_fields(detail_rows, proposals)
    if detail_rows.empty:
        lane_counts = pd.DataFrame(columns=["residual_lane", "row_count"])
        action_counts = pd.DataFrame(columns=["recommended_triage_action", "row_count"])
    else:
        lane_counts = (
            detail_rows.groupby("residual_lane", dropna=False)
            .size()
            .reset_index(name="row_count")
            .sort_values(["row_count", "residual_lane"], ascending=[False, True])
        )
        action_counts = (
            detail_rows.groupby("recommended_triage_action", dropna=False)
            .size()
            .reset_index(name="row_count")
            .sort_values(["row_count", "recommended_triage_action"], ascending=[False, True])
        )
    return {
        "detail_rows": detail_rows,
        "lane_counts": lane_counts,
        "action_counts": action_counts,
        "proposals": proposals,
    }


def _compact_counts(df: pd.DataFrame, *, key_col: str, count_col: str = "row_count") -> str:
    if df.empty:
        return "none"
    parts: list[str] = []
    for _, row in df.head(5).iterrows():
        parts.append(f"{row.get(key_col, '')}={int(row.get(count_col, 0) or 0)}")
    return "; ".join(parts)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-suppressed",
        action="store_true",
        help="Include already-suppressed rows in the export (default: active residual only).",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(include_suppressed=bool(args.include_suppressed))
    detail_rows = report["detail_rows"]
    detail_rows.to_csv(CSV_OUT, index=False)
    proposals = report["proposals"]
    proposals.to_csv(PROPOSAL_CSV_OUT, index=False)
    review_template = build_review_template(proposals)
    review_template.to_csv(REVIEW_TEMPLATE_CSV_OUT, index=False)
    lane_counts = {
        str(row["residual_lane"]): int(row["row_count"])
        for _, row in report["lane_counts"].iterrows()
        if str(row.get("residual_lane", "")).strip()
    }
    closure_ready_count = int(
        lane_counts.get("authority_backed_primary_backfill_review", 0)
    )
    SUMMARY_JSON_OUT.write_text(
        json.dumps(
            {
                "schema_version": TRIAGE_SCHEMA_VERSION,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "include_suppressed": bool(args.include_suppressed),
                "detail_row_count": int(len(detail_rows)),
                "lane_counts": lane_counts,
                "closure_ready_row_count": closure_ready_count,
                "authority_backfill_proposal_group_count": int(len(proposals)),
                "authority_backfill_proposal_sample_count": int(
                    proposals["sample_count"].sum() if not proposals.empty else 0
                ),
                "authority_backfill_proposal_id_hash": hash_payload(
                    sorted(proposals["proposal_id"].astype(str).tolist()) if not proposals.empty else []
                ),
                "proposal_review_status": PROPOSAL_REVIEW_STATUS,
                "proposal_review_basis": PROPOSAL_BASIS,
                "detail_csv": CSV_OUT.name,
                "proposal_csv": PROPOSAL_CSV_OUT.name,
                "review_template_csv": REVIEW_TEMPLATE_CSV_OUT.name,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"[EXPORT] Missing-primary label triage: {CSV_OUT.as_posix()}")
    print(f"[EXPORT] Authority-backed primary-label proposals: {PROPOSAL_CSV_OUT.as_posix()}")
    print(f"[EXPORT] Human review template (does not apply updates): {REVIEW_TEMPLATE_CSV_OUT.as_posix()}")
    print(f"[EXPORT] Missing-primary triage summary: {SUMMARY_JSON_OUT.as_posix()}")
    print(f"Rows: {len(detail_rows)}")
    print(f"Authority-backed proposals: {int(proposals['sample_count'].sum()) if not proposals.empty else 0}")
    if detail_rows.empty:
        print("Status: no queued missing-primary review rows.")
        return 0

    print(f"Lane counts: {_compact_counts(report['lane_counts'], key_col='residual_lane')}")
    print(f"Action counts: {_compact_counts(report['action_counts'], key_col='recommended_triage_action')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
