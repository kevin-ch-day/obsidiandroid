#!/usr/bin/env python3
"""Post-run read-only Permission Intel authority enrichment + enriched protection analysis.

Example:
  python scripts/diagnostics/generate_permission_authority_enrichment.py \\
    --run-root output/runs/allcurrent_diagnostic \\
    --run-id 20260721T231415Z__e0c43b
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.permission_authority_enrichment import (
    compose_permission_authority_enrichment,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="20260721T231415Z__e0c43b")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--enriched-protection-dir", default="")
    parser.add_argument("--enriched-pairwise-dir", default="")
    parser.add_argument("--skip-enriched-compose", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    manifest = compose_permission_authority_enrichment(
        run_root=Path(args.run_root).resolve(),
        run_id=str(args.run_id).strip(),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        enriched_protection_dir=Path(args.enriched_protection_dir) if args.enriched_protection_dir else None,
        enriched_pairwise_dir=Path(args.enriched_pairwise_dir) if args.enriched_pairwise_dir else None,
        repo_root=repo_root,
        skip_enriched_compose=bool(args.skip_enriched_compose),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
