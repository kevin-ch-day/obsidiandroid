#!/usr/bin/env python3
"""CLI: diagnose why unmatched label sample IDs lack feature-matrix rows.

Example::

    python scripts/diagnostics/diagnose_alignment_gap.py \\
        --run-root output/runs/20260503T044105Z__008d9d

Compatibility wrapper retained at ``scripts/diagnose_alignment_gap.py``.
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

from obsidiandroid.diagnostics import alignment_gap_diagnostics  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Alignment gap diagnostics (label ids without feature rows).")
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
        help="Pipeline run directory (expects diagnostics/unmatched_label_ids.csv).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=400,
        help="Batch size for IN (...) queries (default 400).",
    )
    args = parser.parse_args()

    detail, summary = alignment_gap_diagnostics.run_alignment_gap_diagnosis(
        args.run_root, chunk_size=args.chunk_size
    )
    print(f"[OK] Diagnosed {len(detail)} unmatched label sample_id(s).")
    print(f"[OK] Top reasons: {summary.get('reason_counts', {})}")
    diag = Path(args.run_root) / "diagnostics"
    print(f"[OK] Wrote {diag / 'alignment_gap_diagnostics.csv'}")
    print(f"[OK] Wrote {diag / 'alignment_gap_summary.json'}")
    print(f"[OK] Wrote {diag / 'alignment_gap_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
