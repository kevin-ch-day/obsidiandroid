#!/usr/bin/env python3
"""Generate Phase-2 pairwise permission co-occurrence report from a finished run.

Read-only. Does not query production databases.

Example:
  python scripts/diagnostics/generate_type_permission_pairwise_report.py \\
    --run-root output/runs/allcurrent_diagnostic \\
    --run-id 20260721T231415Z__e0c43b
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_CHECKOUT_ROOT = Path(__file__).resolve().parents[2]
if str(_CHECKOUT_ROOT) not in sys.path:
    sys.path.insert(0, str(_CHECKOUT_ROOT))

from scripts._bootstrap import prepare_script_runtime  # noqa: E402

prepare_script_runtime(__file__)

from obsidiandroid.cli.menu import run_locator as rl
from obsidiandroid.reporting.type_permission_pairwise import (
    compose_type_permission_pairwise_report,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-root", default="")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--min-global-support", type=int, default=100)
    parser.add_argument("--min-sample-support", type=int, default=30)
    parser.add_argument("--min-family-support", type=int, default=3)
    parser.add_argument("--include-app-defined-lane", action="store_true")
    parser.add_argument("--max-pairs-per-type", type=int, default=5000)
    args = parser.parse_args()

    repo_root = _repo_root()
    run_root, run_id = rl.resolve_report_run(
        repo_root=repo_root,
        run_id=str(args.run_id or "").strip(),
        run_root_arg=str(args.run_root or "").strip(),
        latest=bool(args.latest),
    )
    manifest = compose_type_permission_pairwise_report(
        run_root=run_root,
        run_id=run_id,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        min_global_support=int(args.min_global_support),
        min_sample_support=int(args.min_sample_support),
        min_family_support=int(args.min_family_support),
        include_app_defined_lane=bool(args.include_app_defined_lane),
        max_pairs_per_type=int(args.max_pairs_per_type),
        repo_root=repo_root,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
