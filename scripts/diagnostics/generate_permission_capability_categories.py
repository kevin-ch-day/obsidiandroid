#!/usr/bin/env python3
"""Generate offline permission capability-category reports for a completed run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.permission_capability_categories import (
    compose_permission_capability_category_report,
)
from obsidiandroid.reporting.type_permission_protection import EXPECTED_RUN_ID


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--run-id", default=EXPECTED_RUN_ID)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--min-samples", type=int, default=30)
    args = parser.parse_args()
    manifest = compose_permission_capability_category_report(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
        repo_root=Path(__file__).resolve().parents[2],
        min_samples=int(args.min_samples),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
