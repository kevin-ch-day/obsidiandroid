#!/usr/bin/env python3
"""Generate Phase-2 pairwise permission co-occurrence report from a finished run.

Read-only. Does not query production databases.

Example:
  python scripts/diagnostics/generate_type_permission_pairwise_report.py \\
    --run-root output/runs/allcurrent_diagnostic \\
    --run-id 20260721T014651Z__61b4a7
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.cli.menu import run_locator as rl
from obsidiandroid.reporting.type_permission_pairwise import (
    compose_type_permission_pairwise_report,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_run_root(*, repo_root: Path, run_id: str = "", run_root_arg: str = "", latest: bool = False) -> tuple[Path, str]:
    if run_root_arg:
        root = Path(run_root_arg).resolve()
        if not run_id:
            snaps = sorted((root / "diagnostics").glob("analysis_snapshot_*.csv"))
            if snaps:
                run_id = snaps[-1].stem.replace("analysis_snapshot_", "")
            else:
                raise SystemExit("provide --run-id when --run-root has no analysis_snapshot_*.csv")
        return root, str(run_id).strip()
    if latest:
        latest_run_id = rl.read_latest_run_id()
        if not latest_run_id:
            raise SystemExit("could not resolve latest run id from manifests/pointers")
        run_id = latest_run_id
    if not run_id:
        raise SystemExit("provide --run-id, --run-root, or --latest")
    manifest_payload, manifest_path = rl.resolve_manifest_for_run_id(
        str(run_id).strip(),
        runs_dir=repo_root / "output" / "runs",
    )
    if not manifest_payload:
        raise SystemExit(f"run directory not found for run_id: {run_id}")
    root = rl.resolve_run_root_for_manifest(
        manifest_payload,
        run_id=str(run_id).strip(),
        manifest_path=manifest_path,
    )
    return root, str(run_id).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-root", default="")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--min-global-support", type=int, default=100)
    parser.add_argument("--min-sample-support", type=int, default=30)
    parser.add_argument("--min-family-support", type=int, default=3)
    parser.add_argument("--include-app-defined-lane", action="store_true")
    parser.add_argument("--max-pairs-per-type", type=int, default=5000)
    args = parser.parse_args()

    repo_root = _repo_root()
    run_root, run_id = _resolve_run_root(
        repo_root=repo_root,
        run_id=str(args.run_id or "").strip(),
        run_root_arg=str(args.run_root or "").strip(),
        latest=bool(args.latest),
    )
    manifest = compose_type_permission_pairwise_report(
        run_root=run_root,
        run_id=run_id,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        min_global_support=int(args.min_global_support),
        min_sample_support=int(args.min_sample_support),
        min_family_support=int(args.min_family_support),
        include_app_defined_lane=bool(args.include_app_defined_lane),
        max_pairs_per_type=int(args.max_pairs_per_type),
        repo_root=repo_root,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
