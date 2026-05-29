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

from obsidiandroid.database import authority_contracts
from obsidiandroid.database import db_engine
from scripts.diagnostics import export_label_authority_vendor_evidence as evidence_export


DEFAULT_INPUT = Path("output") / "diagnostics" / "label_authority_vendor_evidence_seed_latest.csv"
DEFAULT_SUMMARY = Path("output") / "diagnostics" / "label_authority_vendor_evidence_summary_latest.md"
DEFAULT_ALIAS_CANDIDATES = Path("output") / "diagnostics" / "label_authority_alias_candidates_latest.csv"
GENERIC_FAMILY_TOKENS = {"", "unknown", "generic", "agent", "malware", "trojan", "adware", "riskware", "pup", "pua"}
NON_FAMILY_ALIAS_TOKENS = {
    "android",
    "androidos",
    "backdoor",
    "banker",
    "dropper",
    "heur",
    "msil",
    "ransom",
    "ransomware",
    "riskware",
    "trojan",
    "virus",
    "win32",
    "worm",
}


def _load_evidence(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _table_has_column(table_name: str, column_name: str) -> bool:
    try:
        return authority_contracts.table_has_column(table_name, column_name)
    except Exception:
        return False


def _load_known_tokens() -> tuple[set[str], set[str]]:
    return authority_contracts.load_known_family_and_alias_tokens()


def _safe_load_alias_tokens() -> tuple[set[str], set[str]]:
    known_families, known_aliases = _load_known_tokens()
    return known_families, known_aliases


def _bootstrap_input(input_path: Path) -> bool:
    available_columns = evidence_export._fetch_vendor_columns()
    vendor_specs = evidence_export._select_vendor_columns(available_columns, None)
    if not vendor_specs:
        return False
    vendor_columns = [
        column_name
        for _, column_name, _ in vendor_specs
        if column_name not in evidence_export.VERDICT_METADATA_COLUMNS
    ]
    verdict_df = evidence_export._fetch_verdict_frame(vendor_columns, None)
    export_df = evidence_export.build_evidence_export(verdict_df, vendor_specs)
    if export_df.empty:
        return False
    input_path.parent.mkdir(parents=True, exist_ok=True)
    export_df.to_csv(input_path, index=False)
    return True


def _build_alias_candidates(df: pd.DataFrame, known_families: set[str], known_aliases: set[str]) -> pd.DataFrame:
    work = df.copy()
    work["parsed_family_token"] = work["parsed_family_token"].fillna("").astype(str).str.strip().str.lower()
    work = work[~work["parsed_family_token"].isin(GENERIC_FAMILY_TOKENS)]
    work = work[~work["parsed_family_token"].isin(NON_FAMILY_ALIAS_TOKENS)]
    work = work[~work["parsed_family_token"].str.endswith("_malformed", na=False)]
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
        bootstrapped = _bootstrap_input(args.input)
        if not bootstrapped:
            print(f"[WARN] Input not found and auto-bootstrap failed: {args.input}")
            return 1
        print(f"[INFO] Bootstrapped parser-enriched vendor evidence: {args.input}")
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
