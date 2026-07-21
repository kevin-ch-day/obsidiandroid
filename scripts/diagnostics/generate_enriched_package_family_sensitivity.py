#!/usr/bin/env python3
"""Generate joint enriched-lane × package-balance × leave-family sensitivity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.enriched_package_family_sensitivity import (
    compose_enriched_package_family_sensitivity,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--run-id", default="20260721T142432Z__07f657")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    manifest = compose_enriched_package_family_sensitivity(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
        repo_root=Path(__file__).resolve().parents[2],
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
