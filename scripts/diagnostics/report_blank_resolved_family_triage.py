"""Inspect and export blank-resolved family debt outside missing-resolution triage.

Some Android + Permission Intel rows have blank resolved-family slugs but are
classified into provenance/policy lanes that the missing-resolution view does
not queue. This report keeps that residue visible without conflating it with the
primary Android missing-resolution backlog.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.database.db_family_mapping_debt import (
    fetch_blank_resolved_family_lane_counts,
    fetch_blank_resolved_outside_missing_resolution_rows,
    fetch_blank_resolved_package_clusters,
)


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "blank_resolved_family_triage_latest.csv"


def build_report() -> dict[str, pd.DataFrame]:
    """Collect blank-resolved debt slices for operator review."""
    detail_rows = pd.DataFrame(fetch_blank_resolved_outside_missing_resolution_rows())
    bucket_rows = pd.DataFrame(fetch_blank_resolved_family_lane_counts())
    if detail_rows.empty:
        lane_counts = pd.DataFrame(columns=["review_lane", "row_count"])
    else:
        lane_counts = (
            detail_rows.groupby("review_lane", dropna=False)
            .size()
            .reset_index(name="row_count")
            .sort_values(["row_count", "review_lane"], ascending=[False, True])
        )
    return {
        "detail_rows": detail_rows,
        "lane_counts": lane_counts,
        "authority_bucket_counts": bucket_rows,
        "package_clusters": pd.DataFrame(fetch_blank_resolved_package_clusters()),
    }


def _compact_counts(df: pd.DataFrame, *, key_col: str, count_col: str = "row_count") -> str:
    if df.empty:
        return "none"
    parts: list[str] = []
    for _, row in df.head(5).iterrows():
        parts.append(f"{row.get(key_col, '')}={int(row.get(count_col, 0) or 0)}")
    return "; ".join(parts)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    detail_rows = report["detail_rows"]
    detail_rows.to_csv(CSV_OUT, index=False)

    print(f"[EXPORT] Blank-resolved family triage: {CSV_OUT.as_posix()}")
    print(f"Rows outside missing-resolution view: {len(detail_rows)}")
    if detail_rows.empty:
        print("Status: no supplemental blank-resolved review rows.")
        return 0

    blank_total = int(report["authority_bucket_counts"]["sample_count"].sum()) if not report["authority_bucket_counts"].empty else 0
    print(f"Live blank-resolved Android + PI rows: {blank_total}")
    print(f"Lane counts: {_compact_counts(report['lane_counts'], key_col='review_lane')}")
    package_clusters = report.get("package_clusters")
    if isinstance(package_clusters, pd.DataFrame) and not package_clusters.empty:
        parts: list[str] = []
        for _, row in package_clusters.head(5).iterrows():
            parts.append(
                f"{row.get('android_package_name', '')}={int(row.get('sample_count', 0) or 0)}"
            )
        print(f"Top package clusters: {'; '.join(parts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
