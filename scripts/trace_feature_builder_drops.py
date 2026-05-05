#!/usr/bin/env python3
"""Trace ``unknown_feature_builder_drop`` samples through feature-building stages.

Example::

    python scripts/trace_feature_builder_drops.py \\
        --diagnostics-dir output/runs/20260503T044105Z__008d9d/diagnostics
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.repo_import_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.diagnostics import feature_builder_drop_trace  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-root",
        type=Path,
        default=None,
        help="Pipeline run directory (uses run-root/diagnostics).",
    )
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        default=None,
        help="Explicit diagnostics directory (overrides --run-root).",
    )
    args = parser.parse_args()
    trace_df, summary = feature_builder_drop_trace.run_feature_builder_drop_trace(
        run_root=args.run_root,
        diagnostics_dir=args.diagnostics_dir,
    )
    dom = summary.get("dominant_first_missing_stage", "")
    n = summary.get("dominant_count", 0)
    diag = trace_df.shape[0]
    if args.diagnostics_dir is not None:
        out = Path(args.diagnostics_dir)
    elif args.run_root is not None:
        out = Path(args.run_root) / "diagnostics"
    else:
        out = REPO_ROOT / "diagnostics"
    print(f"[OK] Traced {diag} gap rows; dominant first_missing_stage={dom!r} ({n}).")
    print(f"[OK] Wrote {out / 'feature_builder_drop_trace.csv'}")
    print(f"[OK] Wrote {out / 'feature_builder_drop_summary.json'}")
    print(f"[OK] Wrote {out / 'feature_builder_drop_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
