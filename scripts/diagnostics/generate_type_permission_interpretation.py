#!/usr/bin/env python3
"""Generate evidence-qualified type-permission interpretation for a completed run.

Read-only. Requires prior type-permission and pairwise diagnostic outputs.

Example:
  python scripts/diagnostics/generate_type_permission_interpretation.py \\
    --run-root output/runs/allcurrent_diagnostic \\
    --run-id 20260721T231415Z__e0c43b
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.type_permission_interpretation import (
    compose_type_permission_interpretation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    manifest = compose_type_permission_interpretation(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        repo_root=repo_root,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
