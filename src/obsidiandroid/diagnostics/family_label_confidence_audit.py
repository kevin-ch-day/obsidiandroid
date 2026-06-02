"""Confidence-sieving audit for family labels in prepared Android cohorts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.labeling.taxonomy import normalize_family_name

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

_PUBLIC_PACKAGE_FAMILY_CORROBORATION: dict[str, str] = {
    "cmf0.c3b5bm90zq.patch": "spynote",
    "com.android.tester": "spynote",
    "com.appser.verapp": "spynote",
    "good.bye.google": "spynote",
    "yps.eton.application": "spynote",
}

_PUBLIC_SHA256_FAMILY_CORROBORATION: dict[str, str] = {
    "0ef96f5ce66266f55d4e17f9985c4c929633a972e587ced8b000b3910ffb3303": "spynote",
    "115ee615a45d4645e805da20ba3ccb26c7383cc52f3df16506b522ca3a009235": "spynote",
    "46a3badfa5682d2d862618933155fa04cc64690d5588ea06089670e222ba36b4": "spynote",
    "72db4117f73c566a8a98fe27d00dc645e319a98217fa7fc5992138e70af8574a": "spynote",
    "7e5d28e9663fc6d2c5badc7a660058e2bf69b410791f01709177590c65944db1": "spynote",
    "ca310362727d0416ce6ec24a90409ad2c8d9cdaf95f6236a759ac31eb2a8cb0f": "spynote",
    "cea371b7bdd44271b20194248431c45f03bd66c4b7f7abad8404ca611a27565c": "spynote",
    "f815b1c1b51810bd331eb75d30fabbbad2237011c8cd242c5655bfca304c978a": "spynote",
}


def _norm_series(df: pd.DataFrame, column: str, *, generic_tokens: set[str] | None = None) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    blocked = generic_tokens if generic_tokens is not None else {""}
    series = df[column].fillna("").astype(str).str.strip().str.lower()
    return series.replace({token: "" for token in blocked})


def _norm_family_series(
    df: pd.DataFrame,
    column: str,
    *,
    generic_tokens: set[str],
    blank_token: str = "",
) -> pd.Series:
    """Normalize family labels through the shared taxonomy alias layer."""
    if column not in df.columns:
        return pd.Series([blank_token] * len(df), index=df.index, dtype="object")
    raw = df[column].fillna("").astype(str).str.strip()
    normalized = raw.map(normalize_family_name).astype(str).str.strip().str.lower()
    normalized = normalized.replace({token: "" for token in generic_tokens})
    if blank_token:
        normalized = normalized.replace("", blank_token)
    return normalized


def _infer_raw_type(primary: str, subtype: str) -> str:
    if subtype in _CANONICAL_TYPE_TOKENS:
        return subtype
    if primary in _CANONICAL_TYPE_TOKENS:
        return primary
    if primary == "trojan" and subtype in _CANONICAL_TYPE_TOKENS:
        return subtype
    return ""


def _build_public_package_family_evidence(frame: pd.DataFrame) -> pd.Series:
    """Map known public IOC package names to corroborating family tokens."""
    package_name = _norm_series(frame, "package_name")
    android_package_name = _norm_series(frame, "android_package_name")
    package_family = package_name.map(_PUBLIC_PACKAGE_FAMILY_CORROBORATION).fillna("")
    android_package_family = android_package_name.map(_PUBLIC_PACKAGE_FAMILY_CORROBORATION).fillna("")
    return package_family.where(package_family.ne(""), android_package_family)


def _build_public_hash_family_evidence(frame: pd.DataFrame) -> pd.Series:
    """Map published IOC hashes to corroborating family tokens."""
    sha256 = _norm_series(frame, "sha256")
    return sha256.map(_PUBLIC_SHA256_FAMILY_CORROBORATION).fillna("")


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
    family = _norm_family_series(
        frame,
        "family_canonical",
        generic_tokens=_GENERIC_CANONICAL_TOKENS,
        blank_token="<blank>",
    )
    family_raw = _norm_family_series(
        frame,
        "family_label_raw",
        generic_tokens=_GENERIC_FAMILY_TOKENS,
    )
    label_kind = _norm_series(frame, "sample_label_kind")
    type_slug = _norm_series(frame, "type_slug", generic_tokens={"", "unknown", "none", "null"})
    primary = _norm_series(frame, "category_primary", generic_tokens=_GENERIC_PRIMARY_TOKENS)
    subtype = _norm_series(frame, "category_subtype", generic_tokens=_GENERIC_PRIMARY_TOKENS)
    vt_token = _norm_series(frame, "vt_family_token")
    public_package_family = _build_public_package_family_evidence(frame)
    public_hash_family = _build_public_hash_family_evidence(frame)

    frame["family_norm"] = family
    frame["type_slug_norm"] = type_slug.replace("", "unknown")
    frame["raw_type_inferred"] = [
        _infer_raw_type(p, s)
        for p, s in zip(primary.tolist(), subtype.tolist())
    ]
    frame["issue_weak_label_kind"] = label_kind.isin(_WEAK_LABEL_KINDS)
    frame["issue_weak_label_corroborated"] = (
        frame["issue_weak_label_kind"]
        & (
            vt_token.eq(family)
            | public_package_family.eq(family)
            | public_hash_family.eq(family)
        )
    )
    frame["issue_weak_label"] = frame["issue_weak_label_kind"] & ~frame["issue_weak_label_corroborated"]
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
            weak_label_corroborated_rows=("issue_weak_label_corroborated", "sum"),
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
            "weak_label_corroborated_rows": int(row["weak_label_corroborated_rows"]),
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


def build_family_label_drift_remediation_rows(samples_df: pd.DataFrame) -> pd.DataFrame:
    """Return a row-level remediation ledger for weak-label and family-conflict drift."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame()

    frame = samples_df.copy()
    family = _norm_family_series(
        frame,
        "family_canonical",
        generic_tokens=_GENERIC_CANONICAL_TOKENS,
        blank_token="<blank>",
    )
    family_raw = _norm_family_series(
        frame,
        "family_label_raw",
        generic_tokens=_GENERIC_FAMILY_TOKENS,
    )
    label_kind = _norm_series(frame, "sample_label_kind")
    public_package_family = _build_public_package_family_evidence(frame)
    public_hash_family = _build_public_hash_family_evidence(frame)
    vt_token = _norm_series(frame, "vt_family_token")
    frame["issue_weak_label_kind"] = label_kind.isin(_WEAK_LABEL_KINDS)
    frame["issue_weak_label_corroborated"] = (
        frame["issue_weak_label_kind"]
        & (
            vt_token.eq(family)
            | public_package_family.eq(family)
            | public_hash_family.eq(family)
        )
    )
    frame["issue_weak_label"] = frame["issue_weak_label_kind"] & ~frame["issue_weak_label_corroborated"]
    frame["issue_family_conflict"] = (
        ~family_raw.isin(_GENERIC_FAMILY_TOKENS)
        & ~family.isin(_GENERIC_CANONICAL_TOKENS)
        & family_raw.ne(family)
    )
    issue_frame = frame[
        frame["issue_weak_label"] | frame["issue_weak_label_corroborated"] | frame["issue_family_conflict"]
    ].copy()
    if issue_frame.empty:
        return pd.DataFrame()

    if "source_batch_label" in issue_frame.columns:
        source_batch = issue_frame["source_batch_label"].fillna("").astype(str).str.strip().replace("", "<blank>")
    else:
        source_batch = pd.Series(["<blank>"] * len(issue_frame), index=issue_frame.index, dtype="object")

    issue_kind = issue_frame.apply(
        lambda row: (
            "family_conflict"
            if bool(row["issue_family_conflict"])
            else "weak_label_corroborated"
            if bool(row["issue_weak_label_corroborated"])
            else "weak_label"
        ),
        axis=1,
    )
    proposed_action = issue_kind.map(
        {
            "family_conflict": "repair_alias_mapping",
            "weak_label_corroborated": "accept_public_campaign_corroboration",
            "weak_label": "review_weak_label_evidence",
        }
    )

    out = pd.DataFrame(
        {
            "sample_id": issue_frame["sample_id"] if "sample_id" in issue_frame.columns else pd.Series(dtype="Int64"),
            "sha256": issue_frame["sha256"] if "sha256" in issue_frame.columns else "",
            "family_canonical": issue_frame["family_canonical"] if "family_canonical" in issue_frame.columns else "",
            "type_slug": issue_frame["type_slug"] if "type_slug" in issue_frame.columns else "",
            "sample_label_kind": issue_frame["sample_label_kind"] if "sample_label_kind" in issue_frame.columns else "",
            "family_label_raw": issue_frame["family_label_raw"] if "family_label_raw" in issue_frame.columns else "",
            "vt_family_token": issue_frame["vt_family_token"] if "vt_family_token" in issue_frame.columns else "",
            "source_batch_label": source_batch,
            "package_name": issue_frame["package_name"] if "package_name" in issue_frame.columns else "",
            "android_package_name": issue_frame["android_package_name"] if "android_package_name" in issue_frame.columns else "",
            "issue_kind": issue_kind,
            "proposed_action": proposed_action,
        }
    )
    return out.sort_values(
        by=["issue_kind", "family_canonical", "sample_id"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)


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
    remediation_csv_path = diagnostics_dir / f"family_label_drift_remediation_{run_id}.csv"
    md_path = diagnostics_dir / f"family_label_confidence_audit_{run_id}.md"
    remediation_md_path = diagnostics_dir / f"family_label_drift_remediation_{run_id}.md"

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

    remediation_df = build_family_label_drift_remediation_rows(samples_df)
    remediation_csv = remediation_df.to_csv(index=False)
    remediation_csv_path.write_text(remediation_csv, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=remediation_csv_path.name,
        csv_text=remediation_csv,
        global_latest_name="family_label_drift_remediation.latest.csv",
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

    remediation_lines = [
        "# Family Label Drift Remediation",
        "",
        f"Run ID: `{run_id}`",
        "",
        "This ledger is operational. It preserves weak-label and family-conflict rows for targeted repair.",
        "",
        "| sample_id | family | type | label_kind | raw_family | vt_family_token | source_batch | action |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if remediation_df.empty:
        remediation_lines.append("|  | _none_ |  |  |  |  |  |  |")
    else:
        for _, row in remediation_df.iterrows():
            remediation_lines.append(
                f"| {int(row['sample_id']) if pd.notna(row['sample_id']) else ''} | "
                f"`{row['family_canonical']}` | `{row['type_slug']}` | `{row['sample_label_kind']}` | "
                f"`{row['family_label_raw']}` | `{row['vt_family_token']}` | `{row['source_batch_label']}` | "
                f"`{row['proposed_action']}` |"
            )
    remediation_md_text = "\n".join(remediation_lines).strip() + "\n"
    remediation_md_path.write_text(remediation_md_text, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=remediation_md_path.name,
        text=remediation_md_text,
        global_latest_name="family_label_drift_remediation.latest.md",
    )
    return [
        str(json_path),
        str(family_csv_path),
        str(sample_csv_path),
        str(remediation_csv_path),
        str(md_path),
        str(remediation_md_path),
    ]


__all__ = [
    "build_family_label_confidence_payload",
    "build_family_label_drift_remediation_rows",
    "export_family_label_confidence_reports",
]
