#!/usr/bin/env python3
"""Generate live-corpus family context + dominant-family robustness (offline).

Example:
  python scripts/diagnostics/generate_live_corpus_family_context.py \\
    --run-root output/runs/allcurrent_diagnostic \\
    --run-id 20260721T142432Z__07f657
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.live_corpus_family_context import (
    compose_live_corpus_family_context,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    manifest = compose_live_corpus_family_context(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        repo_root=repo_root,
        top_n=int(args.top_n),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
