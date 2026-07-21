#!/usr/bin/env python3
"""Audit type-guard family suppressions for a finished run (read-only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsidiandroid.cli.menu import run_locator as rl
from obsidiandroid.reporting.type_guard_suppression_audit import (
    compose_type_guard_suppression_audit,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-root", default="")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    repo_root = _repo_root()
    run_id = str(args.run_id or "").strip()
    if args.run_root:
        run_root = Path(args.run_root).resolve()
        if not run_id:
            snaps = sorted((run_root / "diagnostics").glob("prediction_errors_*.csv"))
            if not snaps:
                raise SystemExit("provide --run-id")
            run_id = snaps[-1].stem.replace("prediction_errors_", "")
    else:
        if args.latest or not run_id:
            run_id = str(rl.read_latest_run_id() or "").strip()
        if not run_id:
            raise SystemExit("provide --run-id, --run-root, or --latest")
        manifest_payload, manifest_path = rl.resolve_manifest_for_run_id(
            run_id, runs_dir=repo_root / "output" / "runs"
        )
        if not manifest_payload:
            raise SystemExit(f"run not found: {run_id}")
        run_root = rl.resolve_run_root_for_manifest(
            manifest_payload, run_id=run_id, manifest_path=manifest_path
        )
    payload = compose_type_guard_suppression_audit(
        run_root=run_root,
        run_id=run_id,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        repo_root=repo_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
