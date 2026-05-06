"""Profile AV vendor verdict columns and rank parser expansion opportunities.

This diagnostic inspects all vendor verdict columns in
`virustotal_sample_vendor_engine_verdicts` and computes utility metrics:
- label coverage
- label diversity
- token richness
- canonical family-token hit rate
- parser coverage (already implemented vs missing)
- trusted/active vendor flags from `virustotal_vendor_engines`

Exports:
- output/diagnostics/vendor_column_opportunities_latest.csv
- output/diagnostics/vendor_column_opportunities_top_missing.txt
"""

from __future__ import annotations

from pathlib import Path
import argparse
import math
import re
from typing import Iterable
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.database import db_engine
from obsidiandroid.database import db_sample_metadata_queries
from obsidiandroid.vendors.vendor_parser_map import get_vendor_parser_map
from obsidiandroid.cli.ui import display as du


OUTPUT_DIR = Path("output") / "diagnostics"
CSV_OUT = OUTPUT_DIR / "vendor_column_opportunities_latest.csv"
TXT_OUT = OUTPUT_DIR / "vendor_column_opportunities_top_missing.txt"

EMPTY_LABELS = {"", "none", "null", "n/a", "undetected"}
TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _normalize(value: str) -> str:
    return str(value).strip().lower()


def _non_empty_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    mask = (
        series.notna()
        & (text != "")
        & (~text.str.lower().isin(EMPTY_LABELS))
    )
    return text[mask]


def _fetch_vendor_columns() -> list[str]:
    """Return verdict-table vendor columns except non-engine fields."""
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'virustotal_sample_vendor_engine_verdicts'
          AND column_name NOT IN ('sample_id', 'updated_at')
        ORDER BY ordinal_position
    """
    df = db_engine.execute_query(query, fetch=True, as_dataframe=True)
    if df is None or df.empty:
        return []
    return df["column_name"].astype(str).tolist()


def _fetch_vendor_engine_flags() -> pd.DataFrame:
    """Return active/trusted flags keyed by vendor_key."""
    query = """
        SELECT
            LOWER(TRIM(vendor_key)) AS vendor_key,
            is_engine_active,
            is_trusted_vendor
        FROM virustotal_vendor_engines
    """
    df = db_engine.execute_query(query, fetch=True, as_dataframe=True)
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _fetch_family_tokens() -> set[str]:
    """Build normalized family-token set for token-hit estimates."""
    query = """
        SELECT DISTINCT LOWER(TRIM(family_name)) AS family_name
        FROM android_malware_family
        WHERE is_active = 1
          AND family_name IS NOT NULL
          AND TRIM(family_name) <> ''
    """
    df = db_engine.execute_query(query, fetch=True, as_dataframe=True)
    if df is None or df.empty:
        return set()

    tokens: set[str] = set()
    for family in df["family_name"].astype(str):
        clean = _normalize(family)
        if not clean:
            continue
        tokens.add(clean)
        for token in TOKEN_SPLIT_RE.split(clean):
            if len(token) >= 3:
                tokens.add(token)
    return tokens


def _load_samples(type_slug: str | None, limit: int | None) -> pd.DataFrame:
    """Load sample IDs for cohort profiling."""
    if type_slug:
        return db_sample_metadata_queries.load_samples_by_type(
            type_slug=type_slug,
            min_samples_per_family=None,
            require_mapped_family=False,
            require_sha256=True,
            allow_missing_package_name=True,
            limit=limit,
        )

    query = """
        SELECT sample_id
        FROM malware_sample_catalog
        WHERE platform = 'android'
          AND file_extension = 'apk'
          AND sample_id IS NOT NULL
    """
    if limit and limit > 0:
        query += f" LIMIT {int(limit)}"
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def _fetch_verdict_df(sample_ids: Iterable[int], vendor_cols: list[str]) -> pd.DataFrame:
    """Fetch verdict values for selected samples and vendor columns."""
    ids = [int(x) for x in sample_ids if pd.notna(x)]
    if not ids or not vendor_cols:
        return pd.DataFrame()

    select_cols = ", ".join([f"`{c}`" for c in vendor_cols])
    chunk_size = 1000
    parts: list[pd.DataFrame] = []
    for start in range(0, len(ids), chunk_size):
        chunk = ids[start : start + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        query = (
            f"SELECT sample_id, {select_cols} "
            f"FROM virustotal_sample_vendor_engine_verdicts "
            f"WHERE sample_id IN ({placeholders})"
        )
        part = db_engine.execute_query(
            query,
            params=tuple(chunk),
            fetch=True,
            as_dataframe=True,
        )
        if isinstance(part, pd.DataFrame) and not part.empty:
            parts.append(part)

    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def _token_count(label: str) -> int:
    tokens = [t for t in TOKEN_SPLIT_RE.split(_normalize(label)) if t]
    return len(tokens)


def _family_token_hit_rate(labels: pd.Series, family_tokens: set[str]) -> float:
    if labels.empty or not family_tokens:
        return 0.0
    hits = 0
    for label in labels.astype(str):
        text = _normalize(label)
        tokens = {t for t in TOKEN_SPLIT_RE.split(text) if len(t) >= 3}
        if text in family_tokens or bool(tokens & family_tokens):
            hits += 1
    return hits / max(1, len(labels))


def build_opportunity_table(
    samples_df: pd.DataFrame,
    verdict_df: pd.DataFrame,
    vendor_flags_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per-vendor opportunity metrics and rank score."""
    vendor_cols = [c for c in verdict_df.columns if c != "sample_id"]
    if not vendor_cols:
        return pd.DataFrame()

    parser_map = get_vendor_parser_map()
    parser_keys = {_normalize(k) for k in parser_map.keys()}
    family_tokens = _fetch_family_tokens()

    flag_map = {}
    if not vendor_flags_df.empty:
        for _, row in vendor_flags_df.iterrows():
            flag_map[_normalize(row["vendor_key"])] = {
                "is_engine_active": int(row.get("is_engine_active", 0)),
                "is_trusted_vendor": int(row.get("is_trusted_vendor", 0)),
            }

    n_samples = max(1, len(samples_df))
    rows: list[dict] = []
    for col in vendor_cols:
        non_empty = _non_empty_series(verdict_df[col])
        coverage = len(non_empty) / n_samples
        distinct = int(non_empty.nunique())
        avg_len = float(non_empty.str.len().mean()) if not non_empty.empty else 0.0
        avg_tokens = (
            float(non_empty.map(_token_count).mean()) if not non_empty.empty else 0.0
        )
        family_hit_rate = _family_token_hit_rate(non_empty, family_tokens)

        normalized_col = _normalize(col)
        flags = flag_map.get(normalized_col, {})
        trusted = int(flags.get("is_trusted_vendor", 0))
        active = int(flags.get("is_engine_active", 0))
        has_parser = int(normalized_col in parser_keys)

        diversity_score = math.log1p(distinct)
        opportunity_score = (
            (coverage * 45.0)
            + (diversity_score * 8.0)
            + (avg_tokens * 5.0)
            + (family_hit_rate * 30.0)
            + (trusted * 6.0)
            + ((1 - has_parser) * 10.0)
        )

        rows.append(
            {
                "vendor_column": col,
                "samples_total": n_samples,
                "non_empty_count": int(len(non_empty)),
                "coverage_pct": round(coverage * 100.0, 2),
                "distinct_labels": distinct,
                "avg_label_len": round(avg_len, 2),
                "avg_token_count": round(avg_tokens, 2),
                "family_token_hit_rate_pct": round(family_hit_rate * 100.0, 2),
                "has_parser": has_parser,
                "is_trusted_vendor": trusted,
                "is_engine_active": active,
                "opportunity_score": round(opportunity_score, 3),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("opportunity_score", ascending=False).reset_index(drop=True)


def _write_missing_parser_summary(df: pd.DataFrame, cohort_name: str) -> None:
    """Write concise recommendation list for top missing parsers."""
    missing = df[df["has_parser"] == 0].copy()
    top = missing.head(20)

    lines: list[str] = []
    lines.append("VENDOR PARSER EXPANSION CANDIDATES")
    lines.append("=" * 80)
    lines.append(f"Cohort: {cohort_name}")
    lines.append(f"Candidates listed: {len(top)}")
    lines.append("")
    for _, row in top.iterrows():
        lines.append(
            (
                f"{row['vendor_column']:24s} "
                f"score={row['opportunity_score']:7.3f} "
                f"coverage={row['coverage_pct']:6.2f}% "
                f"distinct={int(row['distinct_labels']):5d} "
                f"family-hit={row['family_token_hit_rate_pct']:6.2f}% "
                f"trusted={int(row['is_trusted_vendor'])}"
            )
        )
    lines.append("")
    lines.append("Heuristic: prioritize high score + high coverage + high family-hit first.")

    TXT_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Inspect vendor verdict columns for parser opportunities.",
    )
    parser.add_argument(
        "--type-slug",
        default="banker",
        help="Cohort type_slug. Use empty string for all android APK samples.",
    )
    parser.add_argument(
        "--all-android-apk",
        action="store_true",
        help="Ignore type_slug and profile all android APK samples.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional sample limit for fast profiling.",
    )
    args = parser.parse_args()

    type_slug = "" if args.all_android_apk else (args.type_slug.strip() if args.type_slug else "")
    cohort_name = type_slug or "android_apk_all"

    du.print_section("Vendor Column Opportunity Inspection")
    samples_df = _load_samples(type_slug=type_slug or None, limit=args.limit)
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        du.print_warning("[OPPORTUNITY] No cohort samples loaded.")
        return 1

    vendor_cols = _fetch_vendor_columns()
    if not vendor_cols:
        du.print_warning("[OPPORTUNITY] No vendor columns found in verdict table.")
        return 1

    verdict_df = _fetch_verdict_df(samples_df["sample_id"].tolist(), vendor_cols)
    if verdict_df.empty:
        du.print_warning("[OPPORTUNITY] No verdict data fetched for cohort.")
        return 1

    flags_df = _fetch_vendor_engine_flags()
    report_df = build_opportunity_table(samples_df, verdict_df, flags_df)
    if report_df.empty:
        du.print_warning("[OPPORTUNITY] Report is empty after profiling.")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_df.to_csv(CSV_OUT, index=False)
    _write_missing_parser_summary(report_df, cohort_name=cohort_name)

    du.print_success(f"[OPPORTUNITY] Exported CSV: {CSV_OUT}")
    du.print_success(f"[OPPORTUNITY] Exported TXT: {TXT_OUT}")
    du.print_info(
        f"[OPPORTUNITY] Vendors total={len(report_df)} | "
        f"with_parser={(report_df['has_parser'] == 1).sum()} | "
        f"missing_parser={(report_df['has_parser'] == 0).sum()}"
    )
    du.print_table(report_df.head(15), show_index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
