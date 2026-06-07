"""Inspect and export suppression-aware missing-primary label triage rows.

This report turns the active missing-primary debt surfaced by cohort readiness
into a repeatable operator worklist. It is intentionally read-only.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.database.db_cohort_readiness import fetch_missing_primary_label_triage_rows


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "missing_primary_label_triage_latest.csv"


def build_report(*, include_suppressed: bool = False) -> dict[str, pd.DataFrame]:
    """Collect the key missing-primary triage slices."""
    detail_rows = pd.DataFrame(fetch_missing_primary_label_triage_rows(include_suppressed=include_suppressed))
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

    print(f"[EXPORT] Missing-primary label triage: {CSV_OUT.as_posix()}")
    print(f"Rows: {len(detail_rows)}")
    if detail_rows.empty:
        print("Status: no queued missing-primary review rows.")
        return 0

    print(f"Lane counts: {_compact_counts(report['lane_counts'], key_col='residual_lane')}")
    print(f"Action counts: {_compact_counts(report['action_counts'], key_col='recommended_triage_action')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
