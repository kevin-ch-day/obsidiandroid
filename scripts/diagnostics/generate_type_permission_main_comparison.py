#!/usr/bin/env python3
"""Generate main-type permission differential for a completed run (offline).

Example:
  python scripts/diagnostics/generate_type_permission_main_comparison.py \\
    --run-root output/runs/allcurrent_diagnostic \\
    --run-id 20260721T014651Z__61b4a7
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.type_permission_main_comparison import (
    compose_main_type_permission_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    manifest = compose_main_type_permission_comparison(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        repo_root=repo_root,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
