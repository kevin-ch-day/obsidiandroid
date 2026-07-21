#!/usr/bin/env python3
"""Generate protection-stratified type permission analysis (offline).

Example:
  python scripts/diagnostics/generate_type_permission_protection.py \\
    --run-root output/runs/allcurrent_diagnostic \\
    --run-id 20260721T142432Z__07f657
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.type_permission_protection import (
    assert_deterministic_scientific_outputs,
    compose_type_permission_protection,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="20260721T142432Z__07f657")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--pairwise-output-dir", default="")
    parser.add_argument("--check-determinism", action="store_true")
    parser.add_argument("--skip-aligned-features", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    run_root = Path(args.run_root).resolve()
    if args.check_determinism:
        result = assert_deterministic_scientific_outputs(
            run_root=run_root,
            run_id=str(args.run_id).strip(),
            repo_root=repo_root,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    manifest = compose_type_permission_protection(
        run_root=run_root,
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        pairwise_output_dir=Path(args.pairwise_output_dir) if args.pairwise_output_dir else None,
        repo_root=repo_root,
        load_aligned_features=not args.skip_aligned_features,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
