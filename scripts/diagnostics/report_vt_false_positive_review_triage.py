"""Inspect and export the suppression-aware VT false-positive triage surface.

This script turns the remaining review residue into explicit analyst lanes
based on the suppression-aware effective view. It is intentionally read-only.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.database import db_engine


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "vt_false_positive_review_triage_latest.csv"


def _fetch_dataframe(query: str) -> pd.DataFrame:
    """Run ``query`` against the primary DB and return a DataFrame."""
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def build_report() -> dict[str, pd.DataFrame]:
    """Collect the key false-positive triage slices."""
    return {
        "lane_counts": _fetch_dataframe(
            """
            SELECT review_lane, COUNT(*) AS row_count
            FROM v_vt_false_positive_review_candidates_triage
            GROUP BY review_lane
            ORDER BY row_count DESC, review_lane
            """
        ),
        "action_counts": _fetch_dataframe(
            """
            SELECT recommended_triage_action, COUNT(*) AS row_count
            FROM v_vt_false_positive_review_candidates_triage
            GROUP BY recommended_triage_action
            ORDER BY row_count DESC, recommended_triage_action
            """
        ),
        "global_policy_counts": _fetch_dataframe(
            """
            SELECT global_policy_bucket, COUNT(*) AS row_count
            FROM v_vt_false_positive_review_candidates_triage
            GROUP BY global_policy_bucket
            ORDER BY row_count DESC, global_policy_bucket
            """
        ),
        "top_labels": _fetch_dataframe(
            """
            SELECT
              sample_label,
              COUNT(*) AS row_count,
              MIN(vt_malicious_count) AS min_malicious,
              MAX(vt_malicious_count) AS max_malicious
            FROM v_vt_false_positive_review_candidates_triage
            GROUP BY sample_label
            ORDER BY row_count DESC, max_malicious DESC, sample_label
            LIMIT 25
            """
        ),
        "real_malware_rows": _fetch_dataframe(
            """
            SELECT
              sample_id,
              sha256,
              sample_label,
              family_label,
              platform,
              android_package_name,
              vt_malicious_count,
              vt_suspicious_count,
              vt_harmless_count,
              vt_total_engines,
              raw_detection_ratio,
              confidence_score,
              confidence_bucket,
              review_lane,
              recommended_triage_action
            FROM v_vt_false_positive_review_candidates_triage
            WHERE review_lane = 'real_malware_family_or_class_review'
            ORDER BY vt_malicious_count DESC, sample_id DESC
            """
        ),
        "detail_rows": _fetch_dataframe(
            """
            SELECT
              sample_id,
              sha256,
              sample_label,
              family_label,
              platform,
              android_package_name,
              vt_malicious_count,
              vt_suspicious_count,
              vt_harmless_count,
              vt_total_engines,
              raw_detection_ratio,
              confidence_score,
              confidence_bucket,
              global_policy_bucket,
              global_policy_weight,
              recommended_action,
              review_reason,
              review_lane,
              recommended_triage_action
            FROM v_vt_false_positive_review_candidates_triage
            ORDER BY
              CASE
                WHEN review_lane = 'real_malware_family_or_class_review' THEN 0
                WHEN global_policy_bucket = 'single_vendor_low_context_review' THEN 1
                WHEN global_policy_bucket = 'low_consensus_high_harmless_review' THEN 2
                WHEN review_lane = 'generic_placeholder_review' THEN 3
                WHEN review_lane = 'legit_software_or_installer_review' THEN 4
                WHEN review_lane = 'hash_artifact_review' THEN 5
                WHEN review_lane = 'file_artifact_review' THEN 6
                ELSE 7
              END,
              global_policy_weight ASC,
              vt_malicious_count DESC,
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
    for key in ("lane_counts", "action_counts", "global_policy_counts", "top_labels", "real_malware_rows"):
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
