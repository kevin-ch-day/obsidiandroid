"""Inspect and export policy-held Android family-token residue.

These rows are intentionally excluded from true unresolved-family repair
because the resolved token is generic, coarse, behavioral, or technical rather
than a governed malware family. This report keeps that debt visible without
encouraging unsafe family-authority promotion.
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
from obsidiandroid.database.db_config import PERMISSION_INTEL_DB_NAME


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "android_policy_held_token_risk_latest.csv"

_POLICY_HELD_BASE_CTE = """
WITH pi AS (
    SELECT DISTINCT sample_id
    FROM {permission_db}.android_permission_obs_sample
    WHERE sample_id IS NOT NULL
),
held AS (
    SELECT
        a.sample_id,
        a.resolved_family_lc AS policy_held_token,
        gt.token_kind,
        a.raw_classification_primary,
        a.raw_classification_subtype,
        a.android_package_name,
        COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
        COALESCE(vs.vt_malicious_count, 0) AS vt_malicious_count
    FROM v_android_sample_family_type_authority AS a
    JOIN vendor_label_generic_token_fact AS gt
      ON gt.normalized_token COLLATE utf8mb4_unicode_ci = a.resolved_family_lc COLLATE utf8mb4_unicode_ci
     AND gt.is_active = 1
    JOIN pi
      ON pi.sample_id = a.sample_id
    LEFT JOIN vt_sample_verdict_confidence_current AS vs
      ON vs.sample_id = a.sample_id
    WHERE LOWER(COALESCE(a.platform, '')) = 'android'
      AND a.authority_bucket IN ('resolved_but_no_authority_family', 'generic_label_candidate')
),
risk AS (
    SELECT
        h.*,
        CASE
            WHEN h.token_kind IN ('behavior_class_token')
                THEN 'class_label_not_family'
            WHEN h.token_kind IN ('packer_evasion_token', 'heuristic_token')
                THEN 'technical_signal_not_family'
            WHEN h.token_kind IN ('placeholder_token')
                THEN 'placeholder_or_source_artifact'
            WHEN h.token_kind IN ('campaign_actor_token')
                THEN 'campaign_or_actor_not_family'
            ELSE 'generic_family_token_review'
        END AS policy_hold_lane,
        CASE
            WHEN h.token_kind = 'behavior_class_token'
                THEN 'Keep out of family authority. Use raw primary/subtype or type_slug surfaces for coarse behavior claims.'
            WHEN h.token_kind IN ('packer_evasion_token', 'heuristic_token')
                THEN 'Keep out of family authority. This is a technical detection/evasion signal, not a malware family.'
            WHEN h.token_kind = 'placeholder_token'
                THEN 'Keep out of family authority. Review package/source provenance before any canonical mapping.'
            WHEN h.token_kind = 'campaign_actor_token'
                THEN 'Keep out of family authority unless a governed family/campaign model is added.'
            ELSE 'Manual review. Promote only with external family evidence and stable local support.'
        END AS recommended_next_action
    FROM held AS h
)
""".format(permission_db=PERMISSION_INTEL_DB_NAME)


def _fetch_dataframe(query: str) -> pd.DataFrame:
    """Run ``query`` against the primary DB and return a DataFrame."""
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def build_report() -> dict[str, pd.DataFrame]:
    """Collect the key policy-held token-risk slices."""
    detail_rows = _fetch_dataframe(
        _POLICY_HELD_BASE_CTE
        + """
            SELECT
                sample_id,
                policy_held_token,
                token_kind,
                policy_hold_lane,
                confidence_bucket,
                vt_malicious_count,
                raw_classification_primary,
                raw_classification_subtype,
                android_package_name,
                recommended_next_action
            FROM risk
            ORDER BY
                CASE
                    WHEN policy_hold_lane = 'generic_family_token_review' THEN 0
                    WHEN policy_hold_lane = 'placeholder_or_source_artifact' THEN 1
                    WHEN policy_hold_lane = 'campaign_or_actor_not_family' THEN 2
                    WHEN policy_hold_lane = 'technical_signal_not_family' THEN 3
                    ELSE 4
                END,
                vt_malicious_count DESC,
                policy_held_token,
                sample_id
            """
    )
    if detail_rows.empty:
        return {
            "lane_counts": pd.DataFrame(),
            "token_counts": pd.DataFrame(),
            "detail_rows": detail_rows,
        }

    high_strong = detail_rows["confidence_bucket"].isin(["high", "strong"])
    enriched = detail_rows.assign(_high_or_strong=high_strong.astype(int))
    lane_counts = (
        enriched.groupby(["policy_hold_lane", "token_kind"], dropna=False)
        .agg(
            row_count=("sample_id", "size"),
            token_count=("policy_held_token", "nunique"),
            high_or_strong_rows=("_high_or_strong", "sum"),
        )
        .reset_index()
        .sort_values(["row_count", "high_or_strong_rows", "token_kind"], ascending=[False, False, True])
    )

    def _joined_unique(series: pd.Series) -> str:
        values = sorted({str(value).strip() or "<blank>" for value in series.fillna("")})
        return ",".join(values)

    token_counts = (
        enriched.groupby(
            ["policy_held_token", "token_kind", "policy_hold_lane", "recommended_next_action"],
            dropna=False,
        )
        .agg(
            row_count=("sample_id", "size"),
            high_or_strong_rows=("_high_or_strong", "sum"),
            primary_labels=("raw_classification_primary", _joined_unique),
            subtype_labels=("raw_classification_subtype", _joined_unique),
            package_examples=("android_package_name", _joined_unique),
        )
        .reset_index()
        .sort_values(["row_count", "high_or_strong_rows", "policy_held_token"], ascending=[False, False, True])
        .head(100)
    )
    return {
        "lane_counts": lane_counts,
        "token_counts": token_counts,
        "detail_rows": detail_rows,
    }


def main() -> int:
    """Write the report to disk and print a compact operator summary."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    detail_rows = report["detail_rows"]
    detail_rows.to_csv(CSV_OUT, index=False)

    print(f"[OK] Exported: {CSV_OUT}")
    for key in ("lane_counts", "token_counts"):
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
