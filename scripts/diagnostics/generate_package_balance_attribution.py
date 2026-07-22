#!/usr/bin/env python3
"""Generate offline package-balance attribution for a completed run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.package_balance_attribution import compose_package_balance_attribution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--run-id", default="20260721T231415Z__e0c43b")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    manifest = compose_package_balance_attribution(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
        repo_root=Path(__file__).resolve().parents[2],
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
