"""Confidence-sieving audit for family labels in prepared Android cohorts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh

_WEAK_LABEL_KINDS = {"filename", "hash_like", "opaque_string", "unclassified"}
_GENERIC_FAMILY_TOKENS = {"", "unknown", "generic", "unclassified", "unlabeled"}
_GENERIC_CANONICAL_TOKENS = {"", "unknown", "other", "unmapped", "none", "null"}
_GENERIC_PRIMARY_TOKENS = {"", "unknown", "none", "null", "nan", "n/a", "malware"}
_CANONICAL_TYPE_TOKENS = {
    "adware",
    "banker",
    "dropper",
    "rat",
    "sms-trojan",
    "spyware",
    "stealer",
}


def _norm_series(df: pd.DataFrame, column: str, *, generic_tokens: set[str] | None = None) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    blocked = generic_tokens if generic_tokens is not None else {""}
    series = df[column].fillna("").astype(str).str.strip().str.lower()
    return series.replace({token: "" for token in blocked})


def _infer_raw_type(primary: str, subtype: str) -> str:
    if subtype in _CANONICAL_TYPE_TOKENS:
        return subtype
    if primary in _CANONICAL_TYPE_TOKENS:
        return primary
    if primary == "trojan" and subtype in _CANONICAL_TYPE_TOKENS:
        return subtype
    return ""


def build_family_label_confidence_payload(
    samples_df: pd.DataFrame,
    *,
    min_support: int,
    top_n: int = 50,
) -> dict[str, Any]:
    """Rank suspicious sample/family label surfaces for cohort auditing."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return {
            "row_count": 0,
            "family_count": 0,
            "sample_rows": [],
            "family_rows": [],
        }

    frame = samples_df.copy()
    family = _norm_series(frame, "family_canonical", generic_tokens=_GENERIC_CANONICAL_TOKENS)
    family = family.replace("", "<blank>")
    family_raw = _norm_series(frame, "family_label_raw", generic_tokens=_GENERIC_FAMILY_TOKENS)
    label_kind = _norm_series(frame, "sample_label_kind")
    type_slug = _norm_series(frame, "type_slug", generic_tokens={"", "unknown", "none", "null"})
    primary = _norm_series(frame, "category_primary", generic_tokens=_GENERIC_PRIMARY_TOKENS)
    subtype = _norm_series(frame, "category_subtype", generic_tokens=_GENERIC_PRIMARY_TOKENS)
    vt_token = _norm_series(frame, "vt_family_token")

    frame["family_norm"] = family
    frame["type_slug_norm"] = type_slug.replace("", "unknown")
    frame["raw_type_inferred"] = [
        _infer_raw_type(p, s)
        for p, s in zip(primary.tolist(), subtype.tolist())
    ]
    frame["issue_weak_label"] = label_kind.isin(_WEAK_LABEL_KINDS)
    frame["issue_family_conflict"] = (
        ~family_raw.isin(_GENERIC_FAMILY_TOKENS)
        & ~family.isin(_GENERIC_CANONICAL_TOKENS)
        & family_raw.ne(family)
    )
    frame["issue_blank_family_with_vt_token"] = vt_token.ne("") & family_raw.isin(_GENERIC_FAMILY_TOKENS)
    frame["issue_type_mismatch"] = (
        frame["raw_type_inferred"].ne("")
        & frame["type_slug_norm"].ne("unknown")
        & frame["raw_type_inferred"].ne(frame["type_slug_norm"])
    )

    family_support = frame["family_norm"].value_counts().to_dict()
    frame["family_support_count"] = frame["family_norm"].map(lambda key: int(family_support.get(key, 0)))
    frame["issue_low_family_support"] = frame["family_support_count"] < int(max(1, min_support))

    sample_penalty = (
        frame["issue_family_conflict"].astype(int) * 35
        + frame["issue_type_mismatch"].astype(int) * 25
        + frame["issue_weak_label"].astype(int) * 18
        + frame["issue_blank_family_with_vt_token"].astype(int) * 14
        + frame["issue_low_family_support"].astype(int) * 8
    )
    frame["label_confidence_score"] = (100 - sample_penalty).clip(lower=0, upper=100)

    sample_ranked = frame.sort_values(
        by=[
            "label_confidence_score",
            "family_support_count",
            "sample_id",
        ],
        ascending=[True, True, True],
        kind="stable",
    ).head(top_n)

    sample_rows: list[dict[str, Any]] = []
    for _, row in sample_ranked.iterrows():
        reasons: list[str] = []
        if bool(row["issue_family_conflict"]):
            reasons.append("family_conflict")
        if bool(row["issue_type_mismatch"]):
            reasons.append("raw_type_mismatch")
        if bool(row["issue_weak_label"]):
            reasons.append("weak_label_kind")
        if bool(row["issue_blank_family_with_vt_token"]):
            reasons.append("blank_family_with_vt_token")
        if bool(row["issue_low_family_support"]):
            reasons.append("low_family_support")
        sample_rows.append(
            {
                "sample_id": int(row["sample_id"]) if pd.notna(row.get("sample_id")) else None,
                "family_canonical": str(row["family_norm"]),
                "type_slug": str(row["type_slug_norm"]),
                "category_primary": str(primary.loc[row.name]),
                "category_subtype": str(subtype.loc[row.name]),
                "raw_type_inferred": str(row["raw_type_inferred"]),
                "sample_label_kind": str(label_kind.loc[row.name]),
                "family_support_count": int(row["family_support_count"]),
                "label_confidence_score": int(row["label_confidence_score"]),
                "reasons": ",".join(reasons),
            }
        )

    grouped = (
        frame.groupby("family_norm", dropna=False)
        .agg(
            sample_count=("family_norm", "size"),
            type_slug=("type_slug_norm", lambda s: str(s.mode().iloc[0]) if not s.mode().empty else "unknown"),
            weak_label_rows=("issue_weak_label", "sum"),
            family_conflict_rows=("issue_family_conflict", "sum"),
            type_mismatch_rows=("issue_type_mismatch", "sum"),
            blank_family_with_vt_token_rows=("issue_blank_family_with_vt_token", "sum"),
            low_support_rows=("issue_low_family_support", "sum"),
            mean_label_confidence_score=("label_confidence_score", "mean"),
            min_label_confidence_score=("label_confidence_score", "min"),
        )
        .reset_index()
    )
    grouped["priority_score"] = (
        grouped["family_conflict_rows"] * 25
        + grouped["type_mismatch_rows"] * 18
        + grouped["weak_label_rows"] * 12
        + grouped["blank_family_with_vt_token_rows"] * 10
        + grouped["low_support_rows"] * 5
        + (grouped["sample_count"] >= 20).astype(int) * 4
    )
    grouped["priority_bucket"] = "monitor"
    grouped.loc[grouped["family_conflict_rows"] > 0, "priority_bucket"] = "family_conflict"
    grouped.loc[
        (grouped["family_conflict_rows"] == 0) & (grouped["type_mismatch_rows"] > 0),
        "priority_bucket",
    ] = "type_mismatch"
    grouped.loc[
        (grouped["family_conflict_rows"] == 0)
        & (grouped["type_mismatch_rows"] == 0)
        & (grouped["weak_label_rows"] > 0),
        "priority_bucket",
    ] = "weak_label"
    grouped = grouped.sort_values(
        by=["priority_score", "sample_count", "family_norm"],
        ascending=[False, False, True],
        kind="stable",
    ).head(top_n)

    family_rows = [
        {
            "family_canonical": str(row["family_norm"]),
            "type_slug": str(row["type_slug"]),
            "sample_count": int(row["sample_count"]),
            "weak_label_rows": int(row["weak_label_rows"]),
            "family_conflict_rows": int(row["family_conflict_rows"]),
            "type_mismatch_rows": int(row["type_mismatch_rows"]),
            "blank_family_with_vt_token_rows": int(row["blank_family_with_vt_token_rows"]),
            "low_support_rows": int(row["low_support_rows"]),
            "mean_label_confidence_score": round(float(row["mean_label_confidence_score"]), 4),
            "min_label_confidence_score": int(row["min_label_confidence_score"]),
            "priority_score": int(row["priority_score"]),
            "priority_bucket": str(row["priority_bucket"]),
        }
        for _, row in grouped.iterrows()
    ]

    return {
        "row_count": int(len(frame)),
        "family_count": int(frame["family_norm"].nunique()),
        "min_support": int(min_support),
        "sample_rows": sample_rows,
        "family_rows": family_rows,
    }


def export_family_label_confidence_reports(
    *,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame,
    min_support: int,
) -> list[str]:
    """Write confidence-sieving artifacts for family labels."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_family_label_confidence_payload(
        samples_df,
        min_support=min_support,
    )

    json_path = diagnostics_dir / f"family_label_confidence_audit_{run_id}.json"
    family_csv_path = diagnostics_dir / f"family_label_confidence_families_{run_id}.csv"
    sample_csv_path = diagnostics_dir / f"family_label_confidence_samples_{run_id}.csv"
    md_path = diagnostics_dir / f"family_label_confidence_audit_{run_id}.md"

    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=json_path.name,
        payload=payload,
        global_latest_name="family_label_confidence_audit.latest.json",
    )

    family_df = pd.DataFrame(payload.get("family_rows", []))
    family_csv = family_df.to_csv(index=False)
    family_csv_path.write_text(family_csv, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=family_csv_path.name,
        csv_text=family_csv,
        global_latest_name="family_label_confidence_families.latest.csv",
    )

    sample_df = pd.DataFrame(payload.get("sample_rows", []))
    sample_csv = sample_df.to_csv(index=False)
    sample_csv_path.write_text(sample_csv, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=sample_csv_path.name,
        csv_text=sample_csv,
        global_latest_name="family_label_confidence_samples.latest.csv",
    )

    lines = [
        "# Family Label Confidence Audit",
        "",
        f"Run ID: `{run_id}`",
        f"Cohort rows: **{int(payload.get('row_count', 0))}**",
        f"Families: **{int(payload.get('family_count', 0))}**",
        f"Min support floor: **{int(payload.get('min_support', 0))}**",
        "",
        "## Family priorities",
        "",
    ]
    if family_df.empty:
        lines.append("No family confidence issues ranked.")
    else:
        lines.extend(
            [
                "| family | type | n | weak | family_conflict | type_mismatch | blank+vt | low_support | mean_conf | min_conf | bucket |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for _, row in family_df.iterrows():
            lines.append(
                f"| `{row['family_canonical']}` | `{row['type_slug']}` | {int(row['sample_count'])} | "
                f"{int(row['weak_label_rows'])} | {int(row['family_conflict_rows'])} | "
                f"{int(row['type_mismatch_rows'])} | {int(row['blank_family_with_vt_token_rows'])} | "
                f"{int(row['low_support_rows'])} | {float(row['mean_label_confidence_score']):.2f} | "
                f"{int(row['min_label_confidence_score'])} | `{row['priority_bucket']}` |"
            )
        lines.append("")
    if not sample_df.empty:
        lines.extend(
            [
                "## Lowest-confidence sample rows",
                "",
                "| sample_id | family | type | raw_type | label_kind | family_support | confidence | reasons |",
                "| --- | --- | --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for _, row in sample_df.head(20).iterrows():
            lines.append(
                f"| `{row['sample_id']}` | `{row['family_canonical']}` | `{row['type_slug']}` | "
                f"`{row['raw_type_inferred']}` | `{row['sample_label_kind']}` | "
                f"{int(row['family_support_count'])} | {int(row['label_confidence_score'])} | `{row['reasons']}` |"
            )
    md_text = "\n".join(lines).strip() + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="family_label_confidence_audit.latest.md",
    )
    return [str(json_path), str(family_csv_path), str(sample_csv_path), str(md_path)]


__all__ = [
    "build_family_label_confidence_payload",
    "export_family_label_confidence_reports",
]
