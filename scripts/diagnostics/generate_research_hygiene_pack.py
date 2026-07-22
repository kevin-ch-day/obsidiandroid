#!/usr/bin/env python3
"""Generate holdout calibration + Core Results artifact map for a finished run.

Read-only. No database / Core / Erebus writes.

Example:
  python scripts/diagnostics/generate_research_hygiene_pack.py \\
    --run-root output/runs/allcurrent_diagnostic \\
    --run-id 20260721T231415Z__e0c43b
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.cli.menu import run_locator as rl
from obsidiandroid.diagnostics.core_results_artifact_map import compose_core_results_artifact_map
from obsidiandroid.reporting.holdout_calibration_report import compose_holdout_calibration_report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve(repo_root: Path, run_id: str, run_root_arg: str, latest: bool) -> tuple[Path, str]:
    if run_root_arg:
        root = Path(run_root_arg).resolve()
        if not run_id:
            preds = sorted((root / "diagnostics").glob("headline_test_predictions_*.csv"))
            if not preds:
                raise SystemExit("provide --run-id")
            run_id = preds[-1].stem.replace("headline_test_predictions_", "")
        return root, run_id
    if latest or not run_id:
        run_id = str(rl.read_latest_run_id() or "").strip()
    if not run_id:
        raise SystemExit("provide --run-id, --run-root, or --latest")
    manifest_payload, manifest_path = rl.resolve_manifest_for_run_id(
        run_id, runs_dir=repo_root / "output" / "runs"
    )
    if not manifest_payload:
        raise SystemExit(f"run not found: {run_id}")
    root = rl.resolve_run_root_for_manifest(
        manifest_payload, run_id=run_id, manifest_path=manifest_path
    )
    return root, run_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-root", default="")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--skip-calibration", action="store_true")
    parser.add_argument("--skip-core-map", action="store_true")
    args = parser.parse_args()
    repo_root = _repo_root()
    run_root, run_id = _resolve(
        repo_root,
        str(args.run_id or "").strip(),
        str(args.run_root or "").strip(),
        bool(args.latest),
    )
    out: dict[str, object] = {"run_id": run_id, "run_root": str(run_root)}
    if not args.skip_calibration:
        out["holdout_calibration"] = compose_holdout_calibration_report(
            run_root=run_root, run_id=run_id, repo_root=repo_root
        )
    if not args.skip_core_map:
        out["core_results_artifact_map"] = compose_core_results_artifact_map(
            run_root=run_root, run_id=run_id, repo_root=repo_root
        )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
