"""Inspect and export the Android missing-resolution triage surface.

This script turns the concentrated ``missing_resolved_family`` Android/APK
backlog into a repeatable operator report. It is intentionally read-only.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.database import db_engine


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "android_missing_resolution_triage_latest.csv"


def _fetch_dataframe(query: str) -> pd.DataFrame:
    """Run ``query`` against the primary DB and return a DataFrame."""
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def build_report() -> dict[str, pd.DataFrame]:
    """Collect the key Android missing-resolution triage slices."""
    return {
        "lane_counts": _fetch_dataframe(
            """
            SELECT review_lane, COUNT(*) AS row_count
            FROM v_android_missing_resolution_triage
            GROUP BY review_lane
            ORDER BY row_count DESC, review_lane
            """
        ),
        "action_counts": _fetch_dataframe(
            """
            SELECT recommended_action, COUNT(*) AS row_count
            FROM v_android_missing_resolution_triage
            GROUP BY recommended_action
            ORDER BY row_count DESC, recommended_action
            """
        ),
        "top_clusters": _fetch_dataframe(
            """
            SELECT
              package_cluster_key,
              package_cluster_size,
              COUNT(*) AS row_count,
              MIN(sample_id) AS first_sample_id,
              MAX(sample_id) AS last_sample_id
            FROM v_android_missing_resolution_triage
            GROUP BY package_cluster_key, package_cluster_size
            ORDER BY package_cluster_size DESC, package_cluster_key
            LIMIT 25
            """
        ),
        "vt_tail_rows": _fetch_dataframe(
            """
            SELECT
              sample_id,
              sha256,
              platform,
              source_batch_label,
              android_package_name,
              package_cluster_key,
              package_cluster_size,
              package_cluster_rank,
              vt_family_token,
              vt_suggested_threat_label,
              review_lane,
              recommended_action,
              authority_gap_reason
            FROM v_android_missing_resolution_triage
            WHERE review_lane = 'vt_tail_review'
            ORDER BY sample_id
            """
        ),
        "detail_rows": _fetch_dataframe(
            """
            SELECT
              sample_id,
              sha256,
              platform,
              file_extension,
              analysis_lane,
              source_batch_label,
              android_package_name,
              vt_first_submission_at_utc,
              vt_first_seen_itw_date,
              effective_first_seen_at_utc,
              family_raw,
              family_lc,
              resolved_family_lc,
              raw_classification_primary,
              raw_classification_subtype,
              vt_family_token,
              vt_suggested_threat_label,
              authority_bucket,
              authority_gap_reason,
              raw_vs_authority_status,
              package_cluster_key,
              package_cluster_size,
              package_cluster_rank,
              review_lane,
              recommended_action
            FROM v_android_missing_resolution_triage
            ORDER BY
              CASE WHEN review_lane = 'vt_tail_review' THEN 0 ELSE 1 END,
              package_cluster_size DESC,
              sample_id
            """
        ),
    }


def main() -> int:
    """Write the report to disk and print a compact operator summary."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    detail_rows = report["detail_rows"]
    detail_rows.to_csv(CSV_OUT, index=False)

    print(f"[OK] Exported: {CSV_OUT}")
    for key in ("lane_counts", "action_counts", "top_clusters", "vt_tail_rows"):
        df = report[key]
        print(f"\n== {key} ==")
        if df.empty:
            print("[empty]")
        else:
            print(df.to_string(index=False))
    print(f"\n[OK] detail_rows={len(detail_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
