"""Inspect parser quality across vendor parsers using live DB-backed samples.

This script loads a taxonomy-filtered cohort, runs vendor parser evaluation,
and exports parser health diagnostics for quick regression checks.
"""

from __future__ import annotations

from pathlib import Path
import sys
import argparse
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = REPO_ROOT / "src"
for _p in (REPO_ROOT, _SRC):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from obsidiandroid.database import db_sample_metadata_queries
from analysis.evaluation.vendor_classification_parser import (
    parse_vendor_classifications,
)
from obsidiandroid.cli.ui import display as du


DEFAULT_OUTPUT_DIR = Path("output") / "diagnostics"
DEFAULT_CSV = DEFAULT_OUTPUT_DIR / "vendor_parser_health_latest.csv"
DEFAULT_TXT = DEFAULT_OUTPUT_DIR / "vendor_parser_health_latest.txt"


def _build_parser_health_table(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Build a stable subset of parser-health metrics for export and review."""
    cols = [
        "Vendor",
        "Samples Evaluated",
        "Family Match Accuracy (%)",
        "Unknown Parsed (%)",
        "Generic Family Ratio",
        "Detection Diversity",
        "Enrichment Score",
        "Final ML Score",
        "Vendor Category",
    ]
    available = [c for c in cols if c in summary_df.columns]
    health_df = summary_df[available].copy()
    sort_col = "Final ML Score" if "Final ML Score" in health_df.columns else available[0]
    return health_df.sort_values(sort_col, ascending=False).reset_index(drop=True)


def _write_text_summary(health_df: pd.DataFrame, txt_path: Path, cohort_size: int) -> None:
    """Write a human-readable diagnostic summary."""
    lines: list[str] = []
    lines.append("VENDOR PARSER HEALTH REPORT")
    lines.append("=" * 80)
    lines.append(f"Cohort Size: {cohort_size}")
    lines.append(f"Vendors: {len(health_df)}")
    lines.append("")

    if not health_df.empty:
        top = health_df.head(5)
        lines.append("Top Vendors")
        lines.append("-" * 80)
        for _, row in top.iterrows():
            vendor = row.get("Vendor", "unknown")
            score = row.get("Final ML Score", "n/a")
            unknown = row.get("Unknown Parsed (%)", "n/a")
            lines.append(f"{vendor:20s} score={score} unknown%={unknown}")
        lines.append("")

    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text("\n".join(lines), encoding="utf-8")


def run_parser_health_inspection(
    type_slug: str,
    limit: int | None,
    min_samples_per_family: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Execute parser-health inspection workflow for a cohort."""
    samples_df = db_sample_metadata_queries.load_samples_by_type(
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=True,
        require_sha256=True,
        allow_missing_package_name=True,
        limit=limit,
    )
    if samples_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    _, summary_df, _, _ = parse_vendor_classifications(
        samples_df=samples_df,
        engine_metadata={},
        verbose=False,
    )
    if summary_df.empty:
        return samples_df, pd.DataFrame()

    health_df = _build_parser_health_table(summary_df)
    return samples_df, health_df


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Inspect vendor parser health.")
    parser.add_argument("--type-slug", default="banker", help="Cohort type_slug.")
    parser.add_argument("--limit", type=int, default=None, help="Optional cohort limit.")
    parser.add_argument(
        "--min-samples-per-family",
        type=int,
        default=3,
        help="Minimum family support threshold.",
    )
    args = parser.parse_args()

    du.print_section("Vendor Parser Health Inspection")
    samples_df, health_df = run_parser_health_inspection(
        type_slug=args.type_slug,
        limit=args.limit,
        min_samples_per_family=args.min_samples_per_family,
    )

    if samples_df.empty or health_df.empty:
        du.print_warning("[HEALTH] No parser health data generated.")
        return 1

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    health_df.to_csv(DEFAULT_CSV, index=False)
    _write_text_summary(health_df, DEFAULT_TXT, len(samples_df))

    du.print_success(f"[HEALTH] Exported parser health CSV: {DEFAULT_CSV}")
    du.print_success(f"[HEALTH] Exported parser health TXT: {DEFAULT_TXT}")
    du.print_table(health_df.head(10), show_index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
