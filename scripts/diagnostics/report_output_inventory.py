#!/usr/bin/env python3
"""Emit artifact classification inventory for a finished run directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._bootstrap import prepare_script_runtime  # noqa: E402

prepare_script_runtime(__file__)

from obsidiandroid.diagnostics import output_inventory  # noqa: E402
from obsidiandroid.cli.menu import run_locator as rl  # noqa: E402


def _resolve_run_id(run_root: Path) -> str:
    """Resolve canonical run instance ID from manifest when available."""
    manifest_payload = rl.read_json_object(run_root / "run_manifest.json")
    manifest_run_id = str(manifest_payload.get("run_id", "")).strip()
    return manifest_run_id or str(run_root.name or "").strip()


def _resolve_run_root(*, repo_root: Path, run_root_arg: str, run_id: str, latest: bool) -> Path:
    """Resolve canonical run root from explicit path, run_id, or latest manifest."""
    output_root = repo_root / "output"
    if run_root_arg:
        return Path(run_root_arg).resolve()
    if latest:
        latest_run_id = rl.read_latest_run_id()
        if not latest_run_id:
            raise SystemExit("could not resolve latest run id from manifests/pointers")
        run_id = latest_run_id
    if not run_id:
        raise SystemExit("provide --run-root, --run-id, or --latest")
    manifest_payload, manifest_path = rl.resolve_manifest_for_run_id(
        str(run_id).strip(),
        runs_dir=output_root / "runs",
    )
    if not manifest_payload:
        raise SystemExit(f"run directory not found for run_id: {run_id}")
    return rl.resolve_run_root_for_manifest(
        manifest_payload,
        run_id=str(run_id).strip(),
        manifest_path=manifest_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--run-root",
        default="",
        help="Explicit canonical run root path.",
    )
    selection.add_argument(
        "--run-id",
        default="",
        help="Run ID resolved through manifest-backed lookup.",
    )
    selection.add_argument(
        "--latest",
        action="store_true",
        help="Use the latest manifest-backed run.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional directory for CSV/JSON/MD (default: <run-root>/diagnostics).",
    )
    args = parser.parse_args()
    run_root = _resolve_run_root(
        repo_root=ROOT,
        run_root_arg=args.run_root,
        run_id=args.run_id,
        latest=bool(args.latest),
    )
    out_dir = Path(args.output_dir).resolve() if args.output_dir else (run_root / "diagnostics")
    run_id = _resolve_run_id(run_root)

    output_inventory.write_virtual_layout(run_root)
    paths, summary = output_inventory.write_artifact_inventory_bundle(
        run_root=run_root,
        diagnostics_dir=out_dir,
        run_id=run_id,
        manifest_paths=[],
        extra_summary={"source": "report_output_inventory_cli"},
    )
    print(json.dumps({"summary": summary, "written": paths}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
