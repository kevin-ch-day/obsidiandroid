#!/usr/bin/env python3
"""Generate offline package-balanced permission analysis for a completed run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.package_balanced_permission_analysis import (
    compose_package_balanced_permission_analysis,
)


def main() -> int:
    """Parse CLI arguments and compose the read-only diagnostic package."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--run-id", default="20260721T231415Z__e0c43b")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--skip-aligned-features", action="store_true")
    args = parser.parse_args()
    manifest = compose_package_balanced_permission_analysis(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
        repo_root=Path(__file__).resolve().parents[2],
        load_features=not args.skip_aligned_features,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
