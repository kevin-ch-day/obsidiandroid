#!/usr/bin/env python3
"""Emit feature-lineage audit artifacts (JSON + CSV) for a completed run.

Example::

    python scripts/diagnostics/report_feature_lineage.py \\
        --diagnostics-dir output/runs/RUNID/diagnostics

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

from obsidiandroid.diagnostics import feature_lineage_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build feature_lineage_summary.json and .csv from existing diagnostics exports."
    )
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        required=True,
        help="Path to .../output/runs/<run_id>/diagnostics (must contain feature_contract.json).",
    )
    args = parser.parse_args()
    j, c = feature_lineage_report.write_feature_lineage_artifacts(args.diagnostics_dir)
    print(f"[OK] Wrote {j}")
    print(f"[OK] Wrote {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
