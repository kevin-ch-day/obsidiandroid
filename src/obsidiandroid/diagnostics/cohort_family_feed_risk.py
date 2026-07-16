"""Prepared-cohort family feed-risk diagnostics for samples entering modeling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.governance.family_tier_authority import normalize_family_identity_token

_GENERIC_FAMILY_TOKENS = {"", "unknown", "generic", "unclassified", "unlabeled", "none", "null", "nan", "n/a"}
_GENERIC_CANONICAL_TOKENS = {"", "unknown", "other", "unmapped", "none", "null", "nan", "n/a"}
_WEAK_LABEL_KINDS = {"filename", "hash_like", "opaque_string", "unclassified"}


def _norm_series(frame: pd.DataFrame, column: str, *, lower: bool = False) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")
    series = frame[column].fillna("").astype(str).str.strip()
    if lower:
        series = series.str.lower()
    return series


def build_family_feed_risk_payload(
    samples_df: pd.DataFrame,
    *,
    top_n: int = 25,
) -> dict[str, Any]:
    """Rank prepared-cohort families by concentration and label-authority risk."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty or "family_canonical" not in samples_df.columns:
        return {
            "total_rows": 0,
            "family_count": 0,
            "ranked_families": [],
        }

    frame = samples_df.copy()
    total_rows = int(len(frame))

    family_display = _norm_series(frame, "family_canonical")
    family_identity = family_display.map(normalize_family_identity_token)
    family = family_display.where(family_identity.ne(""), "<blank>")
    label_kind = _norm_series(frame, "sample_label_kind", lower=True)
    family_raw = _norm_series(frame, "family_label_raw").map(normalize_family_identity_token)
    vt_token = _norm_series(frame, "vt_family_token")
    type_slug = _norm_series(frame, "type_slug")

    frame["family_canonical"] = family
    frame["issue_weak_label"] = label_kind.isin(_WEAK_LABEL_KINDS) & family_identity.ne("")
    frame["issue_family_conflict"] = (
        ~family_raw.isin(_GENERIC_FAMILY_TOKENS)
        & family_identity.ne("")
        & (family_raw != family_identity)
    )
    frame["issue_opaque_label"] = label_kind.eq("opaque_string")
    frame["issue_blank_family_with_token"] = (vt_token != "") & family_raw.isin(_GENERIC_FAMILY_TOKENS)
    frame["has_vt_family_token"] = vt_token != ""
    frame["type_slug_norm"] = type_slug.replace("", "<blank>")

    grouped = (
        frame.groupby("family_canonical", dropna=False)
        .agg(
            sample_count=("family_canonical", "size"),
            weak_label_rows=("issue_weak_label", "sum"),
            family_conflict_rows=("issue_family_conflict", "sum"),
            opaque_label_rows=("issue_opaque_label", "sum"),
            blank_family_with_token_rows=("issue_blank_family_with_token", "sum"),
            vt_family_token_rows=("has_vt_family_token", "sum"),
            represented_type_count=("type_slug_norm", "nunique"),
        )
        .reset_index()
    )

    dominant_type = (
        frame.groupby(["family_canonical", "type_slug_norm"], dropna=False)
        .size()
        .reset_index(name="type_rows")
        .sort_values(
            by=["family_canonical", "type_rows", "type_slug_norm"],
            ascending=[True, False, True],
            kind="stable",
        )
        .drop_duplicates(subset=["family_canonical"], keep="first")
        .rename(columns={"type_slug_norm": "dominant_type_slug"})
    )
    grouped = grouped.merge(
        dominant_type[["family_canonical", "dominant_type_slug"]],
        on="family_canonical",
        how="left",
    )
    grouped["sample_share_pct"] = grouped["sample_count"].astype(float) / float(max(total_rows, 1)) * 100.0
    grouped["issue_rows"] = (
        grouped["weak_label_rows"]
        + grouped["family_conflict_rows"]
        + grouped["opaque_label_rows"]
        + grouped["blank_family_with_token_rows"]
    )
    grouped["risk_score"] = (
        grouped["family_conflict_rows"] * 25
        + grouped["weak_label_rows"] * 12
        + grouped["opaque_label_rows"] * 10
        + grouped["blank_family_with_token_rows"] * 10
        + grouped["represented_type_count"].clip(lower=1) * 2
        + (grouped["sample_share_pct"] >= 5.0).astype(int) * 10
        + (grouped["sample_share_pct"] >= 10.0).astype(int) * 15
    )
    grouped["priority_bucket"] = "monitor"
    grouped.loc[grouped["family_conflict_rows"] > 0, "priority_bucket"] = "family_conflict"
    grouped.loc[
        (grouped["family_conflict_rows"] == 0) & (grouped["weak_label_rows"] > 0),
        "priority_bucket",
    ] = "weak_label"
    grouped.loc[
        (grouped["family_conflict_rows"] == 0)
        & (grouped["weak_label_rows"] == 0)
        & (grouped["sample_share_pct"] >= 10.0),
        "priority_bucket",
    ] = "concentration"

    grouped = grouped.sort_values(
        by=[
            "risk_score",
            "issue_rows",
            "sample_count",
            "family_canonical",
        ],
        ascending=[False, False, False, True],
        kind="stable",
    ).head(top_n)

    ranked_rows: list[dict[str, Any]] = []
    for _, row in grouped.iterrows():
        ranked_rows.append(
            {
                "family_canonical": str(row["family_canonical"]),
                "dominant_type_slug": str(row.get("dominant_type_slug", "") or "<blank>"),
                "sample_count": int(row["sample_count"]),
                "sample_share_pct": round(float(row["sample_share_pct"]), 4),
                "represented_type_count": int(row["represented_type_count"]),
                "weak_label_rows": int(row["weak_label_rows"]),
                "family_conflict_rows": int(row["family_conflict_rows"]),
                "opaque_label_rows": int(row["opaque_label_rows"]),
                "blank_family_with_token_rows": int(row["blank_family_with_token_rows"]),
                "vt_family_token_rows": int(row["vt_family_token_rows"]),
                "issue_rows": int(row["issue_rows"]),
                "risk_score": int(row["risk_score"]),
                "priority_bucket": str(row["priority_bucket"]),
            }
        )

    return {
        "total_rows": total_rows,
        "family_count": int(frame.loc[frame["family_canonical"].ne("<blank>"), "family_canonical"].nunique()),
        "ranked_families": ranked_rows,
    }


def export_family_feed_risk_reports(
    *,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame,
) -> list[str]:
    """Write prepared-cohort family feed-risk diagnostics under ``diagnostics_dir``."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_family_feed_risk_payload(samples_df)

    json_path = diagnostics_dir / f"cohort_family_feed_risk_{run_id}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    ranked = pd.DataFrame(payload.get("ranked_families") or [])
    csv_path = diagnostics_dir / f"cohort_family_feed_risk_{run_id}.csv"
    ranked.to_csv(csv_path, index=False)

    md_lines = [
        "# Cohort Family Feed Risk",
        "",
        f"- run_id: `{run_id}`",
        f"- total_rows: {int(payload.get('total_rows', 0))}",
        f"- family_count: {int(payload.get('family_count', 0))}",
        "",
    ]
    if ranked.empty:
        md_lines.extend(["No ranked family feed risks detected.", ""])
    else:
        md_lines.extend(
            [
                "| family_canonical | dominant_type_slug | sample_count | sample_share_pct | weak_label_rows | family_conflict_rows | opaque_label_rows | issue_rows | risk_score | priority_bucket |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for _, row in ranked.iterrows():
            md_lines.append(
                f"| `{row['family_canonical']}` | `{row['dominant_type_slug']}` | "
                f"{int(row['sample_count'])} | {float(row['sample_share_pct']):.2f} | "
                f"{int(row['weak_label_rows'])} | {int(row['family_conflict_rows'])} | "
                f"{int(row['opaque_label_rows'])} | {int(row['issue_rows'])} | "
                f"{int(row['risk_score'])} | `{row['priority_bucket']}` |"
            )
        md_lines.append("")

    md_path = diagnostics_dir / f"cohort_family_feed_risk_{run_id}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return [str(json_path), str(csv_path), str(md_path)]


__all__ = [
    "build_family_feed_risk_payload",
    "export_family_feed_risk_reports",
]
