#!/usr/bin/env python3
"""Generate offline temporal permission/capability trend reports for a completed run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.reporting.temporal_permission_trends import compose_temporal_permission_trends
from obsidiandroid.reporting.type_permission_protection import EXPECTED_RUN_ID


def _find_runs_root(run_root: Path) -> Path | None:
    for parent in [run_root, *run_root.parents]:
        if parent.name == "runs":
            return parent
        if parent.name == "_archived" and parent.parent.name == "runs":
            return parent.parent
    return None


def _default_output_dir(run_root: Path, run_id: str) -> Path | None:
    archived = (run_root / "ARCHIVE_RECEIPT.json").is_file() or (run_root / "ARCHIVE_SHA256SUMS.txt").is_file()
    archived = archived or "_archived" in run_root.resolve().parts
    if not archived:
        return None
    runs_root = _find_runs_root(run_root.resolve())
    if runs_root is None:
        return (run_root.parent / "_offline_reports" / run_id / "temporal_permission_trends").resolve()
    return (runs_root / "_offline_reports" / run_id / "temporal_permission_trends").resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--run-id", default=EXPECTED_RUN_ID)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--min-support", type=int, default=30)
    parser.add_argument(
        "--require-canonical-counts",
        action="store_true",
        help="Require frozen e0c43b cohort sizes (9716/9457).",
    )
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    run_id = str(args.run_id).strip()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(run_root, run_id)
    manifest = compose_temporal_permission_trends(
        run_root=run_root,
        run_id=run_id,
        output_dir=output_dir,
        repo_root=Path(__file__).resolve().parents[2],
        min_support=int(args.min_support),
        require_canonical_counts=bool(args.require_canonical_counts),
    )
    print(json.dumps({k: v for k, v in manifest.items() if k != "checksums"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
