#!/usr/bin/env python3
"""Generate robust type-contrast package from joint sensitivity outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.robust_type_contrast import compose_robust_type_contrast


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--run-id", default="20260721T231415Z__e0c43b")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    manifest = compose_robust_type_contrast(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
        repo_root=Path(__file__).resolve().parents[2],
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
