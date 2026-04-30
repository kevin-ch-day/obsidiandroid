"""Inspect `engine_score_input_matrix.xlsx` for feature quality and redundancy.

This utility helps answer:
- Which engine columns are near-constant (low-information)?
- Which engine columns are exact duplicates (redundant)?
- Which engines carry the highest binary entropy?

Exports:
- output/diagnostics/engine_score_matrix_profile_latest.csv
- output/diagnostics/engine_score_matrix_duplicates_latest.csv
- output/diagnostics/engine_score_matrix_profile_latest.txt
"""

from __future__ import annotations

from pathlib import Path
import argparse
import math
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils import display_utils as du


DEFAULT_INPUT = Path("output") / "engine_score_input_matrix.xlsx"
OUTPUT_DIR = Path("output") / "diagnostics"
PROFILE_CSV = OUTPUT_DIR / "engine_score_matrix_profile_latest.csv"
DUPES_CSV = OUTPUT_DIR / "engine_score_matrix_duplicates_latest.csv"
SUMMARY_TXT = OUTPUT_DIR / "engine_score_matrix_profile_latest.txt"


def _binary_entropy(p: float) -> float:
    p = min(max(float(p), 0.0), 1.0)
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def _coerce_binary(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return (numeric > 0).astype(int)


def build_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-engine feature-quality profile."""
    engine_cols = [c for c in df.columns if c != "sample_id"]
    rows: list[dict] = []
    n = max(1, len(df))

    for col in engine_cols:
        binary = _coerce_binary(df[col])
        prevalence = float(binary.mean())
        variance = float(binary.var(ddof=0))
        entropy = _binary_entropy(prevalence)
        non_zero = int(binary.sum())
        rows.append(
            {
                "engine": col,
                "samples": n,
                "positive_count": non_zero,
                "prevalence_pct": round(prevalence * 100.0, 2),
                "variance": round(variance, 6),
                "entropy_bits": round(entropy, 6),
                "low_information_flag": int(entropy < 0.05 or variance < 0.005),
            }
        )

    profile_df = pd.DataFrame(rows)
    if profile_df.empty:
        return profile_df
    return profile_df.sort_values(
        ["low_information_flag", "entropy_bits", "variance"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def find_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Detect exact duplicate binary engine columns."""
    engine_cols = [c for c in df.columns if c != "sample_id"]
    if not engine_cols:
        return pd.DataFrame(columns=["engine_a", "engine_b", "match_type"])

    binary_df = pd.DataFrame({c: _coerce_binary(df[c]) for c in engine_cols})
    seen_signatures: dict[tuple[int, ...], str] = {}
    duplicates: list[dict] = []

    for col in binary_df.columns:
        signature = tuple(binary_df[col].tolist())
        if signature in seen_signatures:
            duplicates.append(
                {
                    "engine_a": seen_signatures[signature],
                    "engine_b": col,
                    "match_type": "exact_binary_duplicate",
                }
            )
        else:
            seen_signatures[signature] = col

    return pd.DataFrame(duplicates)


def _write_summary(profile_df: pd.DataFrame, dupes_df: pd.DataFrame, n_samples: int) -> None:
    """Write human-readable matrix summary."""
    lines: list[str] = []
    lines.append("ENGINE SCORE MATRIX PROFILE")
    lines.append("=" * 80)
    lines.append(f"Samples: {n_samples}")
    lines.append(f"Engines: {len(profile_df)}")
    lines.append(f"Low-information engines: {int(profile_df['low_information_flag'].sum())}")
    lines.append(f"Exact duplicate pairs: {len(dupes_df)}")
    lines.append("")

    lines.append("Top Entropy Engines")
    lines.append("-" * 80)
    for _, row in profile_df.sort_values("entropy_bits", ascending=False).head(10).iterrows():
        lines.append(
            f"{row['engine']:24s} entropy={row['entropy_bits']:.4f} "
            f"prevalence={row['prevalence_pct']:.2f}%"
        )

    lines.append("")
    lines.append("Most Low-Information Engines")
    lines.append("-" * 80)
    low = profile_df[profile_df["low_information_flag"] == 1].sort_values("entropy_bits", ascending=True).head(15)
    for _, row in low.iterrows():
        lines.append(
            f"{row['engine']:24s} entropy={row['entropy_bits']:.4f} "
            f"prevalence={row['prevalence_pct']:.2f}%"
        )

    if not dupes_df.empty:
        lines.append("")
        lines.append("Duplicate Binary Columns")
        lines.append("-" * 80)
        for _, row in dupes_df.head(20).iterrows():
            lines.append(f"{row['engine_a']} == {row['engine_b']}")

    SUMMARY_TXT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Inspect engine score input matrix quality.")
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="Path to engine_score_input_matrix.xlsx",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        du.print_error(f"[MATRIX] File not found: {input_path}")
        return 1

    df = pd.read_excel(input_path)
    if df.empty or "sample_id" not in df.columns:
        du.print_error("[MATRIX] Input matrix is empty or missing sample_id.")
        return 1

    profile_df = build_profile(df)
    dupes_df = find_duplicate_columns(df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    profile_df.to_csv(PROFILE_CSV, index=False)
    dupes_df.to_csv(DUPES_CSV, index=False)
    _write_summary(profile_df, dupes_df, n_samples=len(df))

    du.print_success(f"[MATRIX] Profile exported: {PROFILE_CSV}")
    du.print_success(f"[MATRIX] Duplicates exported: {DUPES_CSV}")
    du.print_success(f"[MATRIX] Summary exported: {SUMMARY_TXT}")
    du.print_table(profile_df.head(15), show_index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
