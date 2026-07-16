#!/usr/bin/env python3
"""Emit feature-matrix gap lineage artifacts for a completed pipeline run.

Writes under ``<run-root>/diagnostics/``:

- ``feature_matrix_row_lineage.csv``
- ``feature_matrix_gap_detail.csv`` (when DB gap drill-down runs)
- ``feature_matrix_gap_summary.{json,md}``

Example::

    OBSIDIAN_DB_USER=root OBSIDIAN_DB_PASSWORD=... \\
      python scripts/diagnostics/report_feature_matrix_gap.py \\
      --run-root output/runs/20260503T051146Z__de2cdc

Use ``--skip-db`` for filesystem-only summary (no gap_detail CSV).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._bootstrap import prepare_script_runtime  # noqa: E402

prepare_script_runtime(__file__)

from obsidiandroid.diagnostics import feature_matrix_gap_lineage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
        help="Pipeline run directory containing diagnostics/",
    )
    parser.add_argument("--chunk-size", type=int, default=400, help="SQL IN (...) batch size.")
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Do not query DB or recompute AV/permission stage counts.",
    )
    args = parser.parse_args()

    lineage_df, gap_detail, summary = feature_matrix_gap_lineage.run_feature_matrix_gap_report(
        args.run_root,
        chunk_size=args.chunk_size,
        skip_db_recompute=args.skip_db,
    )
    diag = args.run_root / "diagnostics"
    print(f"[OK] Row lineage rows: {len(lineage_df)}")
    print(f"[OK] Gap detail rows: {len(gap_detail)}")
    print(f"[OK] Wrote {diag / 'feature_matrix_gap_summary.json'}")
    print(f"[OK] Wrote {diag / 'feature_matrix_gap_summary.md'}")
    print(f"[OK] Wrote {diag / 'feature_matrix_row_lineage.csv'}")
    if summary.get("gap_reason_breakdown"):
        print(f"[OK] Gap reasons: {summary['gap_reason_breakdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
