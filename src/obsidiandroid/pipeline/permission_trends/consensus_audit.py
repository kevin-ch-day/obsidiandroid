"""Vendor consensus distribution and generic-definition audit helpers."""

from __future__ import annotations

from collections import Counter
from math import log
from typing import Any

import pandas as pd

from config import app_config


def extract_selected_vendors(feature_df: pd.DataFrame | None) -> list[str]:
    if not isinstance(feature_df, pd.DataFrame):
        return []
    selected = feature_df.attrs.get("selected_vendors", [])
    if not isinstance(selected, list):
        return []
    return [str(v).strip().lower() for v in selected if str(v).strip()]


def build_consensus_distribution(
    *,
    sample_core_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    selected_vendors: list[str],
    run_id: str,
) -> pd.DataFrame:
    base = sample_core_df[["sample_id", "sha256", "family_id", "family_canonical", "type_slug"]].copy()
    votes_df = build_vendor_votes(parsed_data)
    if votes_df.empty:
        base["run_id"] = run_id
        base["vendor_count"] = 0
        base["top1_vote_share"] = 0.0
        base["top2_vote_share"] = 0.0
        base["top1_minus_top2_gap"] = 0.0
        base["consensus_score_all_vendors"] = 0.0
        base["consensus_entropy_all_vendors"] = 0.0
        base["consensus_score_gated_vendors"] = 0.0
        base["consensus_entropy_gated_vendors"] = 0.0
        base["low_vendor_count_flag"] = 1
        return base

    all_consensus = compute_consensus_metrics(votes_df, prefix="all")
    if selected_vendors:
        gated_votes = votes_df[votes_df["vendor"].isin(set(selected_vendors))].copy()
    else:
        gated_votes = votes_df.copy()
    gated_consensus = compute_consensus_metrics(gated_votes, prefix="gated")

    merged = base.merge(all_consensus, on="sample_id", how="left")
    merged = merged.merge(gated_consensus, on="sample_id", how="left")
    numeric_cols = [
        "vendor_count_all",
        "top1_vote_share_all",
        "top2_vote_share_all",
        "top1_minus_top2_gap_all",
        "consensus_score_all_vendors",
        "consensus_entropy_all_vendors",
        "vendor_count_gated",
        "consensus_score_gated_vendors",
        "consensus_entropy_gated_vendors",
    ]
    for col in numeric_cols:
        merged[col] = pd.to_numeric(merged.get(col, 0), errors="coerce").fillna(0.0)

    merged["run_id"] = run_id
    merged["vendor_count"] = merged["vendor_count_all"].astype(int)
    merged["top1_vote_share"] = merged["top1_vote_share_all"]
    merged["top2_vote_share"] = merged["top2_vote_share_all"]
    merged["top1_minus_top2_gap"] = merged["top1_minus_top2_gap_all"]
    min_vendor_count = int(getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5))
    merged["low_vendor_count_flag"] = (merged["vendor_count"] < min_vendor_count).astype(int)
    keep_cols = [
        "run_id",
        "sample_id",
        "sha256",
        "family_id",
        "family_canonical",
        "type_slug",
        "vendor_count",
        "top1_vote_share",
        "top2_vote_share",
        "top1_minus_top2_gap",
        "consensus_score_all_vendors",
        "consensus_entropy_all_vendors",
        "consensus_score_gated_vendors",
        "consensus_entropy_gated_vendors",
        "low_vendor_count_flag",
    ]
    return merged[keep_cols].sort_values("sample_id").reset_index(drop=True)


def build_vendor_votes(parsed_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for vendor, frame in parsed_data.items():
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        if "sample_id" not in frame.columns:
            continue
        parsed_col = find_column(frame, "Parsed Family")
        if not parsed_col:
            continue
        subset = frame[["sample_id", parsed_col]].copy()
        subset["sample_id"] = pd.to_numeric(subset["sample_id"], errors="coerce")
        subset = subset.dropna(subset=["sample_id"])
        subset["sample_id"] = subset["sample_id"].astype(int)
        subset["parsed_family"] = subset[parsed_col].fillna("").astype(str).str.strip().str.lower()
        subset = subset[subset["parsed_family"] != ""]
        if subset.empty:
            continue
        subset["vendor"] = str(vendor).strip().lower()
        rows.extend(
            {
                "sample_id": int(sample_id),
                "vendor": str(vname),
                "parsed_family": str(pfamily),
            }
            for sample_id, vname, pfamily in subset[["sample_id", "vendor", "parsed_family"]].itertuples(index=False)
        )
    if not rows:
        return pd.DataFrame(columns=["sample_id", "vendor", "parsed_family"])
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["sample_id", "vendor"])
    return out


def find_column(frame: pd.DataFrame, expected: str) -> str | None:
    lowered = {str(col).strip().lower(): str(col) for col in frame.columns}
    return lowered.get(expected.strip().lower())


def compute_consensus_metrics(votes_df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for sample_id, group in votes_df.groupby("sample_id", dropna=False):
        labels = group["parsed_family"].tolist()
        total = len(labels)
        if total <= 0:
            continue
        counts = Counter(labels)
        shares = sorted([count / total for count in counts.values()], reverse=True)
        top1 = float(shares[0]) if shares else 0.0
        top2 = float(shares[1]) if len(shares) > 1 else 0.0
        n_labels = len(counts)
        entropy = 0.0
        for share in shares:
            if share > 0:
                entropy += -(share * log(share))
        if n_labels > 1:
            entropy = float(entropy / log(n_labels))
        else:
            entropy = 0.0
        records.append(
            {
                "sample_id": int(sample_id),
                f"vendor_count_{prefix}": int(total),
                f"top1_vote_share_{prefix}": round(top1, 6),
                f"top2_vote_share_{prefix}": round(top2, 6),
                f"top1_minus_top2_gap_{prefix}": round(top1 - top2, 6),
                f"consensus_score_{'all_vendors' if prefix == 'all' else 'gated_vendors'}": round(top1, 6),
                f"consensus_entropy_{'all_vendors' if prefix == 'all' else 'gated_vendors'}": round(entropy, 6),
            }
        )
    return pd.DataFrame(records)


def build_generic_definition_audit(
    *,
    sample_core_df: pd.DataFrame,
    family_support_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    min_support = int(getattr(app_config, "GENERIC_MIN_SUPPORT", 30))
    support_map = family_support_df.set_index("family_id")["sample_count"].to_dict()
    merged = sample_core_df[["sample_id", "family_id", "type_slug"]].merge(
        consensus_df[["sample_id", "consensus_score_all_vendors", "consensus_entropy_all_vendors", "vendor_count"]],
        on="sample_id",
        how="left",
    )
    merged["family_support"] = merged["family_id"].map(support_map).fillna(0).astype(int)
    merged["is_low_support_family"] = (merged["family_support"] < min_support).astype(int)
    merged["is_generic_primary"] = ((merged["type_slug"] == "unknown") | (merged["family_id"] < 0)).astype(int)
    min_vendor_count = int(getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5))
    valid = merged[merged["vendor_count"] >= min_vendor_count]
    if valid.empty:
        low_consensus_threshold = 0.0
    else:
        low_consensus_threshold = float(valid["consensus_score_all_vendors"].quantile(0.10))
    merged["is_generic_low_consensus"] = (merged["consensus_score_all_vendors"].fillna(0.0) <= low_consensus_threshold).astype(
        int
    )
    merged["generic_low_support_overlap"] = (
        (merged["is_generic_primary"] == 1) & (merged["is_low_support_family"] == 1)
    ).astype(int)

    n = max(len(merged), 1)
    summary_rows = [
        {"run_id": run_id, "metric": "sample_count", "value": int(len(merged))},
        {"run_id": run_id, "metric": "generic_primary_count", "value": int(merged["is_generic_primary"].sum())},
        {
            "run_id": run_id,
            "metric": "generic_primary_pct",
            "value": round(float(merged["is_generic_primary"].sum()) / n, 6),
        },
        {"run_id": run_id, "metric": "low_support_family_count", "value": int(merged["is_low_support_family"].sum())},
        {
            "run_id": run_id,
            "metric": "low_support_family_pct",
            "value": round(float(merged["is_low_support_family"].sum()) / n, 6),
        },
        {
            "run_id": run_id,
            "metric": "generic_low_support_overlap_count",
            "value": int(merged["generic_low_support_overlap"].sum()),
        },
        {"run_id": run_id, "metric": "low_consensus_threshold_p10", "value": round(low_consensus_threshold, 6)},
        {
            "run_id": run_id,
            "metric": "generic_low_consensus_count",
            "value": int(merged["is_generic_low_consensus"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "generic_low_consensus_pct",
            "value": round(float(merged["is_generic_low_consensus"].sum()) / n, 6),
        },
    ]
    return pd.DataFrame(summary_rows)


__all__ = [
    "build_consensus_distribution",
    "build_generic_definition_audit",
    "compute_consensus_metrics",
    "extract_selected_vendors",
    "find_column",
    "build_vendor_votes",
]

