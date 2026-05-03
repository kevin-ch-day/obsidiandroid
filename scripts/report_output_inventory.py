#!/usr/bin/env python3
"""Emit artifact classification inventory for a finished run directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-root",
        required=True,
        help="Path to output/runs/<run_id> (run-scoped root).",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional directory for CSV/JSON/MD (default: <run-root>/diagnostics).",
    )
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    out_dir = Path(args.output_dir).resolve() if args.output_dir else (run_root / "diagnostics")
    run_id = run_root.name

    from analysis.diagnostics.output_inventory import (
        build_inventory_rows,
        write_artifact_inventory_bundle,
        write_virtual_layout,
    )

    write_virtual_layout(run_root)
    paths, summary = write_artifact_inventory_bundle(
        run_root=run_root,
        diagnostics_dir=out_dir,
        run_id=run_id,
        manifest_paths=[],
        extra_summary={"source": "report_output_inventory_cli"},
    )
    print(json.dumps({"summary": summary, "written": paths}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
