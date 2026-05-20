"""Read-only label-noise candidate report from parser-enriched vendor evidence.

This diagnostic is intentionally conservative. It does not relabel samples or
change training behavior. It combines signals inspired by the literature and the
current ObsidianDroid data model:

- generic-label dominance
- low non-generic family consensus across vendors
- disagreement between vendor family evidence and current governed family truth

Inputs:
- parser-enriched evidence CSV from `export_label_authority_vendor_evidence.py`

Outputs:
- sample-level candidate CSV
- markdown summary
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.database import db_engine


DEFAULT_INPUT = Path("output") / "diagnostics" / "label_authority_vendor_evidence_seed_latest.csv"
DEFAULT_CSV = Path("output") / "diagnostics" / "label_noise_candidates_latest.csv"
DEFAULT_MD = Path("output") / "diagnostics" / "label_noise_candidates_summary_latest.md"
GENERIC_FAMILY_TOKENS = {"", "unknown", "generic", "agent", "malware", "trojan", "adware", "riskware", "pua", "pup"}


def _normalize(value: object) -> str:
    return str(value).strip().lower() if value is not None else ""


def _alias_table_present() -> bool:
    df = db_engine.execute_query(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = 'malware_family_alias_fact'
        """,
        fetch=True,
        as_dataframe=True,
    )
    return bool(isinstance(df, pd.DataFrame) and not df.empty and int(df.iloc[0]["n"]) > 0)


def _load_alias_map() -> dict[str, str]:
    if not _alias_table_present():
        return {}
    df = db_engine.execute_query(
        """
        SELECT
            LOWER(TRIM(alias_token)) AS alias_token,
            LOWER(TRIM(canonical_family_slug)) AS canonical_family_slug
        FROM malware_family_alias_fact
        WHERE is_active = 1
          AND alias_token IS NOT NULL
          AND canonical_family_slug IS NOT NULL
          AND TRIM(alias_token) <> ''
          AND TRIM(canonical_family_slug) <> ''
        """,
        fetch=True,
        as_dataframe=True,
    )
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    return {
        _normalize(row["alias_token"]): _normalize(row["canonical_family_slug"])
        for _, row in df.iterrows()
        if _normalize(row["alias_token"]) and _normalize(row["canonical_family_slug"])
    }


def _fetch_authority_map(sample_ids: list[int]) -> pd.DataFrame:
    if not sample_ids:
        return pd.DataFrame(columns=["sample_id", "authority_family_slug", "authority_family_name", "authority_type_slug"])

    parts: list[pd.DataFrame] = []
    chunk_size = 1000
    for start in range(0, len(sample_ids), chunk_size):
        chunk = sample_ids[start : start + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        query = f"""
            SELECT
                msc.sample_id,
                LOWER(TRIM(COALESCE(fam.family_slug, ''))) AS authority_family_slug,
                LOWER(TRIM(COALESCE(fam.family_name, ''))) AS authority_family_name,
                LOWER(TRIM(COALESCE(typ.type_slug, ''))) AS authority_type_slug
            FROM malware_sample_catalog AS msc
            LEFT JOIN (
                SELECT sample_id, resolved_family_lc
                FROM (
                    SELECT
                        v0.sample_id,
                        v0.resolved_family_lc,
                        ROW_NUMBER() OVER (
                            PARTITION BY v0.sample_id
                            ORDER BY COALESCE(v0.resolved_family_lc, '') ASC, v0.sample_id ASC
                        ) AS rn
                    FROM v_android_apk_family_resolved AS v0
                ) AS ranked_family
                WHERE rn = 1
            ) AS fam_res
                ON fam_res.sample_id = msc.sample_id
            LEFT JOIN android_malware_family AS fam
                ON LOWER(TRIM(fam.family_slug)) = fam_res.resolved_family_lc
            LEFT JOIN android_malware_type AS typ
                ON typ.type_id = fam.primary_type_id
            WHERE msc.sample_id IN ({placeholders})
        """
        part = db_engine.execute_query(query, params=chunk, fetch=True, as_dataframe=True)
        if isinstance(part, pd.DataFrame) and not part.empty:
            parts.append(part)
    if not parts:
        return pd.DataFrame(columns=["sample_id", "authority_family_slug", "authority_family_name", "authority_type_slug"])
    out = pd.concat(parts, ignore_index=True)
    out["sample_id"] = out["sample_id"].astype(int)
    return out


def _canonicalize_family_token(token: str, alias_map: dict[str, str]) -> str:
    token = _normalize(token)
    if not token:
        return ""
    return alias_map.get(token, token)


def _build_sample_candidates(evidence_df: pd.DataFrame, authority_df: pd.DataFrame, alias_map: dict[str, str]) -> pd.DataFrame:
    if evidence_df.empty:
        return pd.DataFrame()

    work = evidence_df.copy()
    work["parsed_family_token"] = work["parsed_family_token"].fillna("").astype(str).str.strip().str.lower()
    work["canonical_vendor_family"] = work["parsed_family_token"].map(lambda x: _canonicalize_family_token(x, alias_map))
    authority_map = authority_df.set_index("sample_id").to_dict("index") if not authority_df.empty else {}

    rows: list[dict] = []
    for sample_id, grp in work.groupby("sample_id"):
        authority = authority_map.get(int(sample_id), {})
        authority_family_slug = _normalize(authority.get("authority_family_slug"))
        authority_family_name = _normalize(authority.get("authority_family_name"))
        authority_type_slug = _normalize(authority.get("authority_type_slug"))

        vendor_rows = int(len(grp))
        generic_rows = int(grp["generic_token_flag"].fillna(0).astype(int).sum())
        generic_pct = round((generic_rows / max(vendor_rows, 1)) * 100.0, 2)

        non_generic = grp[~grp["canonical_vendor_family"].isin(GENERIC_FAMILY_TOKENS)].copy()
        non_generic_rows = int(len(non_generic))
        family_counter = Counter(non_generic["canonical_vendor_family"].tolist())
        top_family = ""
        top_votes = 0
        top_pct = 0.0
        distinct_non_generic = len(family_counter)
        if family_counter:
            top_family, top_votes = family_counter.most_common(1)[0]
            top_pct = round((top_votes / max(non_generic_rows, 1)) * 100.0, 2)

        authority_matches_top = int(
            bool(top_family)
            and top_family in {authority_family_slug, authority_family_name}
        )
        authority_missing_flag = int(not bool(authority_family_slug))
        authority_conflict_flag = int(
            bool(top_family)
            and bool(authority_family_slug)
            and top_family != authority_family_slug
            and top_votes >= 2
        )
        low_consensus_flag = int(non_generic_rows >= 3 and top_pct < 60.0)
        generic_dominance_flag = int(generic_pct >= 75.0)
        family_dispersion_flag = int(distinct_non_generic >= 3)

        risk_score = round(
            (0.35 if generic_dominance_flag else 0.0)
            + (0.25 if low_consensus_flag else 0.0)
            + (0.25 if authority_conflict_flag else 0.0)
            + (0.10 if authority_missing_flag else 0.0)
            + (0.15 if family_dispersion_flag else 0.0),
            4,
        )
        reasons: list[str] = []
        if authority_missing_flag:
            reasons.append("authority_missing")
        if generic_dominance_flag:
            reasons.append("generic_dominance")
        if low_consensus_flag:
            reasons.append("low_family_consensus")
        if authority_conflict_flag:
            reasons.append("authority_conflict")
        if family_dispersion_flag:
            reasons.append("family_dispersion")
        if not reasons and non_generic_rows == 0:
            reasons.append("no_non_generic_family_signal")

        rows.append(
            {
                "sample_id": int(sample_id),
                "authority_family_slug": authority_family_slug or None,
                "authority_family_name": authority_family_name or None,
                "authority_type_slug": authority_type_slug or None,
                "vendor_rows": vendor_rows,
                "generic_rows": generic_rows,
                "generic_pct": generic_pct,
                "non_generic_rows": non_generic_rows,
                "distinct_non_generic_family_tokens": distinct_non_generic,
                "top_vendor_family": top_family or None,
                "top_vendor_family_votes": top_votes,
                "top_vendor_family_pct": top_pct,
                "authority_matches_top_vendor_family": authority_matches_top,
                "authority_missing_flag": authority_missing_flag,
                "authority_conflict_flag": authority_conflict_flag,
                "low_consensus_flag": low_consensus_flag,
                "generic_dominance_flag": generic_dominance_flag,
                "family_dispersion_flag": family_dispersion_flag,
                "label_noise_risk_score": risk_score,
                "risk_reasons": "|".join(reasons),
            }
        )

    out = pd.DataFrame(rows)
    return out.sort_values(
        by=[
            "label_noise_risk_score",
            "authority_conflict_flag",
            "generic_pct",
            "distinct_non_generic_family_tokens",
            "sample_id",
        ],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)


def _write_summary(candidates_df: pd.DataFrame, out_path: Path) -> None:
    if candidates_df.empty:
        lines = ["# Label Noise Candidate Summary", "", "- No candidates generated."]
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    high_risk = candidates_df[candidates_df["label_noise_risk_score"] >= 0.50]
    authority_conflicts = candidates_df[candidates_df["authority_conflict_flag"] == 1]
    authority_missing = candidates_df[candidates_df["authority_missing_flag"] == 1]
    reason_counts = (
        candidates_df["risk_reasons"]
        .str.split("|")
        .explode()
        .fillna("")
        .replace("", pd.NA)
        .dropna()
        .value_counts()
    )

    lines = [
        "# Label Noise Candidate Summary",
        "",
        "## Headline",
        f"- Samples scored: `{len(candidates_df)}`",
        f"- High-risk candidates (`score >= 0.50`): `{len(high_risk)}`",
        f"- Authority-conflict candidates: `{len(authority_conflicts)}`",
        f"- Missing-authority candidates: `{len(authority_missing)}`",
        "",
        "## Risk Reason Counts",
        "",
        "| reason | count |",
        "|---|---:|",
    ]
    for reason, count in reason_counts.items():
        lines.append(f"| `{reason}` | {int(count)} |")

    lines.extend(
        [
            "",
            "## Top High-Risk Samples",
            "",
            "| sample_id | score | authority_family | top_vendor_family | generic_pct | top_vendor_family_pct | reasons |",
            "|---:|---:|---|---|---:|---:|---|",
        ]
    )
    for _, row in high_risk.head(25).iterrows():
        authority_family = "" if pd.isna(row.get("authority_family_slug")) else str(row.get("authority_family_slug") or "")
        top_vendor_family = "" if pd.isna(row.get("top_vendor_family")) else str(row.get("top_vendor_family") or "")
        lines.append(
            f"| {int(row['sample_id'])} | {row['label_noise_risk_score']:.2f} | "
            f"`{authority_family}` | `{top_vendor_family}` | "
            f"{row['generic_pct']:.2f} | {row['top_vendor_family_pct']:.2f} | `{row['risk_reasons']}` |"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input parser-enriched evidence CSV")
    parser.add_argument("--csv-out", type=Path, default=DEFAULT_CSV, help="Sample-level candidate CSV output")
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD, help="Markdown summary output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"[WARN] Input not found: {args.input}")
        return 1
    evidence_df = pd.read_csv(args.input)
    sample_ids = sorted({int(x) for x in evidence_df["sample_id"].dropna().tolist()})
    authority_df = _fetch_authority_map(sample_ids)
    alias_map = _load_alias_map()
    candidates_df = _build_sample_candidates(evidence_df, authority_df, alias_map)
    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    candidates_df.to_csv(args.csv_out, index=False)
    _write_summary(candidates_df, args.md_out)
    print(f"[OK] Wrote candidate CSV: {args.csv_out}")
    print(f"[OK] Wrote summary: {args.md_out}")
    if not candidates_df.empty:
        high_risk = int((candidates_df['label_noise_risk_score'] >= 0.50).sum())
        conflicts = int(candidates_df['authority_conflict_flag'].sum())
        print(f"[INFO] High-risk candidates: {high_risk}")
        print(f"[INFO] Authority-conflict candidates: {conflicts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
