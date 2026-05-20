"""Summarize parser-enriched vendor-label evidence and flag alias candidates."""

from __future__ import annotations

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
DEFAULT_SUMMARY = Path("output") / "diagnostics" / "label_authority_vendor_evidence_summary_latest.md"
DEFAULT_ALIAS_CANDIDATES = Path("output") / "diagnostics" / "label_authority_alias_candidates_latest.csv"
GENERIC_FAMILY_TOKENS = {"", "unknown", "generic", "agent", "malware", "trojan", "adware", "riskware", "pup", "pua"}


def _load_evidence(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _load_known_tokens() -> tuple[set[str], set[str]]:
    families_df = db_engine.execute_query(
        """
        SELECT LOWER(TRIM(family_slug)) AS token
        FROM android_malware_family
        WHERE is_active = 1
          AND family_slug IS NOT NULL
          AND TRIM(family_slug) <> ''
        UNION
        SELECT LOWER(TRIM(family_name)) AS token
        FROM android_malware_family
        WHERE is_active = 1
          AND family_name IS NOT NULL
          AND TRIM(family_name) <> ''
        """,
        fetch=True,
        as_dataframe=True,
    )
    known_families = set(families_df["token"].dropna().astype(str).str.strip().str.lower()) if isinstance(families_df, pd.DataFrame) and not families_df.empty else set()

    table_df = db_engine.execute_query(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = 'malware_family_alias_fact'
        """,
        fetch=True,
        as_dataframe=True,
    )
    has_alias_table = bool(
        isinstance(table_df, pd.DataFrame)
        and not table_df.empty
        and int(table_df.iloc[0]["n"]) > 0
    )
    known_aliases: set[str] = set()
    if has_alias_table:
        alias_df = db_engine.execute_query(
            """
            SELECT LOWER(TRIM(alias_token)) AS token
            FROM malware_family_alias_fact
            WHERE is_active = 1
              AND alias_token IS NOT NULL
              AND TRIM(alias_token) <> ''
            """,
            fetch=True,
            as_dataframe=True,
        )
        known_aliases = set(alias_df["token"].dropna().astype(str).str.strip().str.lower()) if isinstance(alias_df, pd.DataFrame) and not alias_df.empty else set()
    return known_families, known_aliases


def _safe_load_alias_tokens() -> tuple[set[str], set[str]]:
    known_families, known_aliases = _load_known_tokens()
    return known_families, known_aliases


def _build_alias_candidates(df: pd.DataFrame, known_families: set[str], known_aliases: set[str]) -> pd.DataFrame:
    work = df.copy()
    work["parsed_family_token"] = work["parsed_family_token"].fillna("").astype(str).str.strip().str.lower()
    work = work[~work["parsed_family_token"].isin(GENERIC_FAMILY_TOKENS)]
    work = work[~work["parsed_family_token"].isin(known_families | known_aliases)]
    if work.empty:
        return pd.DataFrame(
            columns=[
                "parsed_family_token",
                "support_rows",
                "distinct_vendors",
                "generic_pct",
                "example_raw_label",
                "suggested_action",
            ]
        )

    grouped = (
        work.groupby("parsed_family_token")
        .agg(
            support_rows=("sample_id", "count"),
            distinct_vendors=("vendor_key", "nunique"),
            generic_pct=("generic_token_flag", lambda s: round(float(s.mean()) * 100.0, 2)),
            example_raw_label=("raw_vendor_label", "first"),
        )
        .reset_index()
        .sort_values(["support_rows", "distinct_vendors", "parsed_family_token"], ascending=[False, False, True])
    )
    grouped["suggested_action"] = "review_for_alias_or_new_family"
    return grouped


def _write_summary(df: pd.DataFrame, alias_df: pd.DataFrame, out_path: Path) -> None:
    total_rows = len(df)
    generic_pct = round(float(df["generic_token_flag"].mean()) * 100.0, 2) if total_rows else 0.0
    family_cov = round(
        float(
            (~df["parsed_family_token"].fillna("").astype(str).str.strip().str.lower().isin(GENERIC_FAMILY_TOKENS)).mean()
        ) * 100.0,
        2,
    ) if total_rows else 0.0
    vendor_summary = (
        df.groupby("vendor_key")
        .agg(
            rows=("sample_id", "count"),
            generic_pct=("generic_token_flag", lambda s: round(float(s.mean()) * 100.0, 2)),
            distinct_family_tokens=("parsed_family_token", lambda s: s.fillna("").astype(str).str.strip().str.lower().nunique()),
        )
        .reset_index()
        .sort_values(["rows", "vendor_key"], ascending=[False, True])
    )
    top_family = (
        df["parsed_family_token"]
        .fillna("<null>")
        .astype(str)
        .str.strip()
        .str.lower()
        .value_counts()
        .head(15)
    )

    lines = [
        "# Label Authority Vendor Evidence Summary",
        "",
        "## Headline",
        f"- Total evidence rows: `{total_rows}`",
        f"- Generic-flag rate: `{generic_pct}%`",
        f"- Non-generic parsed-family coverage: `{family_cov}%`",
        f"- Alias candidates requiring review: `{len(alias_df)}`",
        "",
        "## Top Parsed Family Tokens",
        "",
        "| token | rows |",
        "|---|---:|",
    ]
    for token, count in top_family.items():
        lines.append(f"| `{token}` | {int(count)} |")

    lines.extend(
        [
            "",
            "## Vendor Summary",
            "",
            "| vendor | rows | generic_pct | distinct_family_tokens |",
            "|---|---:|---:|---:|",
        ]
    )
    for _, row in vendor_summary.head(20).iterrows():
        lines.append(
            f"| `{row['vendor_key']}` | {int(row['rows'])} | {row['generic_pct']:.2f} | {int(row['distinct_family_tokens'])} |"
        )

    if not alias_df.empty:
        lines.extend(
            [
                "",
                "## Top Alias Candidates",
                "",
                "| parsed_family_token | support_rows | distinct_vendors | generic_pct | example_raw_label |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for _, row in alias_df.head(20).iterrows():
            lines.append(
                f"| `{row['parsed_family_token']}` | {int(row['support_rows'])} | {int(row['distinct_vendors'])} | {row['generic_pct']:.2f} | `{str(row['example_raw_label'])[:80]}` |"
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input CSV from export_label_authority_vendor_evidence.py")
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY, help="Markdown summary output path")
    parser.add_argument("--alias-out", type=Path, default=DEFAULT_ALIAS_CANDIDATES, help="CSV alias-candidate output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"[WARN] Input not found: {args.input}")
        return 1
    evidence_df = _load_evidence(args.input)
    known_families, known_aliases = _safe_load_alias_tokens()
    alias_df = _build_alias_candidates(evidence_df, known_families, known_aliases)
    args.alias_out.parent.mkdir(parents=True, exist_ok=True)
    alias_df.to_csv(args.alias_out, index=False)
    _write_summary(evidence_df, alias_df, args.summary_out)
    print(f"[OK] Wrote summary: {args.summary_out}")
    print(f"[OK] Wrote alias candidates: {args.alias_out}")
    print(f"[INFO] Alias candidates: {len(alias_df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
