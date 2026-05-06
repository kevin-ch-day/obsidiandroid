#!/usr/bin/env python3
"""Emit feature-lineage audit artifacts (JSON + CSV) for a completed run.

Example::

    python scripts/report_feature_lineage.py --diagnostics-dir output/runs/RUNID/diagnostics
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

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
