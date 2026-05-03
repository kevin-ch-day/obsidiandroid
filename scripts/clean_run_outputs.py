#!/usr/bin/env python3
"""Dry-run report for redundant/stale/unreferenced files under a run (no deletes)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, help="Path to output/runs/<run_id>")
    parser.add_argument(
        "--oversize-mb",
        type=float,
        default=50.0,
        help="Flag files larger than this threshold (default 50 MB).",
    )
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    manifest_path = run_root / "run_manifest.json"
    manifest_paths: set[str] = set()
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_list = payload.get("artifact_list")
            if isinstance(raw_list, list):
                manifest_paths = {str(x) for x in raw_list}
        except (OSError, json.JSONDecodeError):
            manifest_paths = set()

    duplicate_latest: list[str] = []
    oversize: list[dict[str, object]] = []
    debug_like: list[str] = []
    unreferenced: list[str] = []
    unexpected_roots: list[str] = []

    allowed_prefixes = ("diagnostics", "models", "logs", "bundles", "paper_exports", "paper2_pack", "conf_matrices")
    for path in sorted(run_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_root).as_posix()
        top = rel.split("/", 1)[0] if "/" in rel else rel
        if top not in allowed_prefixes and top not in {"run_manifest.json", "run_summary.json", "run_evidence_index.md"}:
            unexpected_roots.append(rel)

        name = path.name.lower()
        if ".latest." in name:
            duplicate_latest.append(rel)

        try:
            sz = path.stat().st_size
        except OSError:
            sz = 0
        if sz > args.oversize_mb * 1024 * 1024:
            oversize.append({"path": rel, "bytes": sz})

        if any(x in rel for x in ("vendor_parser_stress", "debug", "scratch")):
            debug_like.append(rel)

        resolved = str(path.resolve())
        if manifest_paths and resolved not in manifest_paths and rel not in {
            "run_evidence_index.md",
            "diagnostics/virtual_layout.json",
            "diagnostics/artifact_inventory.json",
            "diagnostics/artifact_inventory.md",
            "diagnostics/artifact_inventory.csv",
        }:
            unreferenced.append(rel)

    report = {
        "run_root": str(run_root),
        "mode": "dry_run",
        "duplicate_latest_inside_run": duplicate_latest,
        "oversize_files": oversize,
        "debug_like_paths": debug_like[:200],
        "possibly_unreferenced": unreferenced[:500],
        "unexpected_top_level_paths": unexpected_roots[:200],
        "notes": "No files were deleted. Review duplicate_latest_inside_run for hygiene policy.",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
